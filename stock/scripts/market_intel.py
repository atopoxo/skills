"""
A-share market intelligence engine.

Multi-source financial news aggregation + sentiment analysis + trade recommendations
for held stocks. Data sources: 财联社 (CLS), 东方财富 (East Money), 金十数据 (Jin10),
新浪财经 (Sina Finance).

Architecture:
  1. Fetch market-wide news from 3 Chinese sources, normalize to standard format
  2. Build macro signals (ETF proxies for growth/defensive/safe-haven)
  3. Build ETF flow snapshot (price × volume flow_score + share change monitor)
  4. For each held stock, score relevance and sentiment
  5. Send all data to LLM (deepseek-v4-pro) for structured trade recommendation
  6. Fall back to algorithmic analysis if LLM is unavailable
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import urllib.request
from collections import Counter
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_NEWS_FETCH_TIMEOUT = 8
_KLINE_FETCH_TIMEOUT = 5

# ── LLM config (loaded from config.json) ────────────────────────────────

_LLM_CONFIG: dict = {}

def _load_llm_config():
    global _LLM_CONFIG
    try:
        from config import _CONFIG_PATH
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        _LLM_CONFIG = cfg.get("llm", {})
    except Exception:
        _LLM_CONFIG = {}

_load_llm_config()

# ── Sentiment keyword dictionaries ───────────────────────────────────────

_BULLISH_KEYWORDS = [
    "涨停", "大涨", "暴涨", "拉升", "突破", "利好", "增持", "回购",
    "业绩预增", "超预期", "中标", "签约", "获批", "创新高", "量价齐升",
    "资金流入", "主力净流入", "北向资金增持", "机构看好", "评级上调",
    "政策利好", "补贴", "扶持", "放量上攻", "强势封板", "连板",
    "扭亏为盈", "业绩大增", "分红", "高送转", "订单饱满", "产能释放",
    "技术突破", "新品发布", "获得资质", "国产替代", "需求旺盛",
]

_BEARISH_KEYWORDS = [
    "跌停", "大跌", "暴跌", "跳水", "破位", "利空", "减持", "抛售",
    "业绩预降", "不及预期", "违规", "处罚", "调查", "立案", "退市风险",
    "资金流出", "主力净流出", "北向资金减持", "评级下调", "机构看空",
    "质押风险", "商誉减值", "计提", "重组失败", "终止上市",
    "业绩变脸", "亏损", "债务违约", "解禁", "限售股上市",
    "产能过剩", "价格战", "竞争加剧", "需求疲软", "成本上升",
]

_SECTOR_KEYWORDS = {
    "AI硬件": ["芯片", "半导体", "算力", "GPU", "CPU", "AI芯片", "光模块", "服务器",
              "存储", "HBM", "先进封装", "EDA", "晶圆", "光刻", "集成电路"],
    "AI应用": ["大模型", "AI应用", "人工智能", "ChatGPT", "AIGC", "智能体",
              "机器人", "自动驾驶", "智能驾驶", "AI+", "应用落地"],
    "商业航天": ["卫星", "航天", "火箭", "低轨", "太空", "星链", "北斗",
                "遥感", "SpaceX", "发射", "星座"],
    "黄金": ["黄金", "金价", "贵金属", "避险", "美联储", "降息", "通胀",
            "COMEX", "央行购金"],
    "战争金属": ["锑", "钨", "锗", "镓", "稀土", "稀有金属", "战略金属",
                "出口管制", "反制", "小金属"],
    "新能源": ["光伏", "锂电", "储能", "风电", "新能源", "电动车", "充电桩",
              "氢能", "固态电池", "钠离子"],
    "消费": ["消费", "白酒", "食品", "家电", "旅游", "免税", "医美", "零售"],
    "医药": ["医药", "创新药", "医疗器械", "CXO", "中药", "疫苗", "生物药"],
    "金融": ["银行", "券商", "保险", "金融科技", "数字货币"],
}

_TOPIC_KEYWORDS = {
    "货币政策": ["降息", "降准", "加息", "LPR", "MLF", "逆回购", "流动性",
               "存款准备金", "央行", "货币政策", "利率", "信贷"],
    "产业政策": ["补贴", "扶持", "产业政策", "国产替代", "自主可控", "信创",
               "十四五", "专项债", "新基建", "碳中和"],
    "国际贸易": ["关税", "贸易战", "出口管制", "制裁", "实体清单", "WTO",
               "反倾销", "中美", "脱钩"],
    "地缘政治": ["冲突", "制裁", "地缘", "台海", "南海", "朝鲜", "俄乌", "中东"],
    "公司治理": ["减持", "增持", "回购", "分红", "股权激励", "定增", "重组",
               "并购", "IPO", "退市"],
    "财报业绩": ["业绩预告", "年报", "季报", "中报", "营收", "净利润", "扣非",
               "毛利率"],
    "资金流向": ["北向资金", "南向资金", "主力资金", "融资融券", "外资", "ETF"],
}

MACRO_ETF_SYMBOLS = {
    "broad": "sh510300",      # 沪深300ETF
    "growth": "sz159915",     # 创业板ETF
    "defensive": "sh510880",  # 红利ETF
    "safe_haven": "sh518880", # 黄金ETF
}

ETF_FLOW_SYMBOLS = [
    "sh510300",   # 沪深300ETF (国家队重仓)
    "sh510050",   # 上证50ETF (国家队重仓)
    "sh510500",   # 中证500ETF
    "sz159919",   # 沪深300ETF深交所
    "sh588000",   # 科创50ETF
    "sz159915",   # 创业板ETF
    "sh510880",   # 红利ETF
    "sh512100",   # 中证1000ETF
    "sh510310",   # 沪深300ETF易方达
]

ETF_FLOW_LOOKBACK_DAYS = 1
ETF_FLOW_BASELINE_VOLUME_DAYS = 5
MACRO_SIGNAL_LOOKBACK_DAYS = 20

# ── Shared state ─────────────────────────────────────────────────────────

_hotspot_data: dict[str, dict] = {}
_hotspot_lock = threading.Lock()
_macro_signals_cache: dict = {}
_macro_signals_time: float = 0.0
_etf_flow_cache: dict = {}
_etf_flow_time: float = 0.0
_news_summary_cache: dict = {}
_news_summary_time: float = 0.0

MACRO_CACHE_TTL = 300
ETF_FLOW_CACHE_TTL = 300
NEWS_SUMMARY_CACHE_TTL = 60


# ═══════════════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════════

def _extract_json_from_html(html: str) -> dict:
    try:
        return json.loads(html)
    except (json.JSONDecodeError, ValueError):
        pass
    m = re.search(r'\{.*\}', html, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def _fetch_json(url: str, headers: dict | None = None,
                timeout: int = _NEWS_FETCH_TIMEOUT) -> dict:
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    if headers:
        default_headers.update(headers)
    req = urllib.request.Request(url, headers=default_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return _extract_json_from_html(raw)
    except Exception:
        return {}


def _raw_code(sina_code: str) -> str:
    for prefix in ("rt_hk", "sh", "sz"):
        if sina_code.startswith(prefix):
            return sina_code[len(prefix):]
    return sina_code


def _try_parse_timestamp(value) -> str:
    """Try to parse various timestamp formats to ISO 8601 string."""
    if not value:
        return ""
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value)).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OSError):
            pass
    value = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return value


# ═══════════════════════════════════════════════════════════════════════════
# Daily K-line Fetcher (Sina Finance API)
# ═══════════════════════════════════════════════════════════════════════════

def fetch_daily_kline(sina_code: str, count: int = 60) -> list[dict]:
    """Fetch daily K-line data from Sina Finance.

    Returns list of {date, open, high, low, close, volume} sorted newest-first.
    """
    url = (
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"CN_MarketData.getKLineData?symbol={sina_code}&scale=240&ma=no&datalen={count}"
    )
    data = _fetch_json(url, timeout=_KLINE_FETCH_TIMEOUT)
    if not isinstance(data, list):
        return []
    rows = []
    for candle in data:
        if not isinstance(candle, dict):
            continue
        try:
            rows.append({
                "date": candle.get("day", ""),
                "open": float(candle.get("open", 0) or 0),
                "high": float(candle.get("high", 0) or 0),
                "low": float(candle.get("low", 0) or 0),
                "close": float(candle.get("close", 0) or 0),
                "volume": int(float(candle.get("volume", 0) or 0)),
            })
        except (ValueError, TypeError):
            continue
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def _calc_return_pct(series: list[dict], lookback_days: int) -> float | None:
    if len(series) <= lookback_days:
        return None
    latest = series[0]["close"]
    previous = series[lookback_days]["close"]
    if previous == 0:
        return None
    return ((latest / previous) - 1.0) * 100.0


def _calc_average_volume(series: list[dict], start: int, count: int) -> float | None:
    window = [float(r.get("volume", 0)) for r in series[start:start + count]
              if float(r.get("volume", 0)) > 0]
    if not window:
        return None
    return sum(window) / len(window)


def _calc_sma(series: list[dict], window: int) -> float | None:
    closes = [float(r["close"]) for r in series[:window]]
    if len(closes) < window:
        return _calc_return_pct(series, window)  # unused internally, kept for API completeness
    return sum(closes) / window


# ═══════════════════════════════════════════════════════════════════════════
# Data Source 1: 财联社 (CLS) Telegraph
# ═══════════════════════════════════════════════════════════════════════════

def fetch_cls_telegraph(count: int = 60) -> list[dict]:
    url = (
        "https://www.cls.cn/nodeapi/updateTelegraphList"
        "?app=CailianpressWeb&os=web&sv=8.4.6"
        f"&rn={count}&type=telegraph"
    )
    data = _fetch_json(url)
    items = []
    for entry in data.get("data", {}).get("roll_data", []) or []:
        title = (entry.get("title") or "").strip()
        content = (entry.get("content") or entry.get("brief") or "").strip()
        content = re.sub(r'^财联社\d+月\d+日电[，,]?\s*', '', content)
        if not title and content:
            title = content[:80] + ("..." if len(content) > 80 else "")
        if not title and not content:
            continue
        ctime = entry.get("ctime", 0)
        time_published = _try_parse_timestamp(ctime)
        item_id = str(entry.get("id", ""))
        url = f"https://www.cls.cn/detail/{item_id}" if item_id else ""
        items.append({
            "title": title,
            "url": url,
            "source": "财联社",
            "summary": content[:200] if content else title[:200],
            "time_published": time_published,
            "raw_id": item_id,
            "raw_content": content,
            "level": entry.get("level", 0),
        })
    return items


# ═══════════════════════════════════════════════════════════════════════════
# Data Source 2: 东方财富 (East Money) Stock News
# ═══════════════════════════════════════════════════════════════════════════

def fetch_eastmoney_stock_news(stock_code: str, count: int = 10) -> list[dict]:
    url = (
        "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
        f"?client=web&columnCode=stockNews&stockCode={stock_code}"
        f"&pageIndex=1&pageSize={count}"
    )
    headers = {"Referer": "https://quote.eastmoney.com/",
               "Origin": "https://quote.eastmoney.com"}
    data = _fetch_json(url, headers=headers)
    items = []
    raw_items = (data.get("data") or {}).get("list", []) or []
    if not raw_items and isinstance(data.get("data"), list):
        raw_items = data["data"]

    for entry in raw_items:
        title = (entry.get("title") or entry.get("Title") or "").strip()
        if not title:
            continue
        show_time = str(entry.get("showTime") or entry.get("ShowTime") or entry.get("date") or "")
        items.append({
            "title": title,
            "url": entry.get("url") or entry.get("Url") or "",
            "source": "东方财富",
            "summary": (entry.get("digest") or entry.get("Digest") or "").strip(),
            "time_published": show_time,
            "raw_content": title,
            "level": 0,
        })
    return items


# ═══════════════════════════════════════════════════════════════════════════
# Data Source 3: 金十数据 (Jin10) Flash
# ═══════════════════════════════════════════════════════════════════════════

def fetch_jin10_flash(count: int = 50) -> list[dict]:
    ts = int(time.time() * 1000)
    url = (
        f"https://flash-api.jin10.com/get_flash_list"
        f"?channel=-8200&vip=1&max_time=&_={ts}"
    )
    headers = {
        "Referer": "https://www.jin10.com/",
        "Origin": "https://www.jin10.com",
        "x-app-id": "bVBF4FyRTn5NJF5n",
        "x-version": "1.0.0",
    }
    data = _fetch_json(url, headers=headers)
    items = []
    raw_data = data.get("data", []) or []
    if isinstance(raw_data, dict):
        raw_data = list(raw_data.values())

    for entry in raw_data[:count]:
        if not isinstance(entry, dict):
            continue
        content = (entry.get("content") or entry.get("data", {}).get("content") or "").strip()
        if not content:
            continue
        content = re.sub(r'<[^>]+>', '', content)
        pub_time = entry.get("time") or entry.get("pub_time") or ""
        item_id = str(entry.get("id", ""))
        items.append({
            "title": content[:80] + ("..." if len(content) > 80 else ""),
            "url": f"https://www.jin10.com/detail/{item_id}" if item_id else "",
            "source": "金十数据",
            "summary": content[:200],
            "time_published": str(pub_time),
            "raw_id": item_id,
            "raw_content": content,
            "importance": entry.get("importance", 0),
            "level": entry.get("importance", 0),
        })
    return items


# ═══════════════════════════════════════════════════════════════════════════
# News Normalization & Dedup  (Requirement 1 & 2)
# ═══════════════════════════════════════════════════════════════════════════

def _score_sentiment(text: str) -> tuple[int, int, list[str]]:
    bullish = 0
    bearish = 0
    matched: list[str] = []
    for kw in _BULLISH_KEYWORDS:
        if kw in text:
            bullish += 1
            matched.append(f"+{kw}")
    for kw in _BEARISH_KEYWORDS:
        if kw in text:
            bearish += 1
            matched.append(f"-{kw}")
    return bullish, bearish, matched


def _extract_topics(text: str) -> list[dict]:
    """Extract topic tags from news text using Chinese keyword matching."""
    topics = []
    for topic, keywords in _TOPIC_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in text:
                score += 1
        if score > 0:
            topics.append({"topic": topic, "relevance_score": min(score, 5)})
    topics.sort(key=lambda t: t["relevance_score"], reverse=True)
    return topics[:3]


def _compute_ticker_sentiment(text: str, stock_name: str, stock_code: str) -> dict | None:
    """Compute ticker-level sentiment for a specific stock from news text."""
    bull, bear, _ = _score_sentiment(text)
    relevance = _score_stock_relevance(text, stock_name, stock_code, None)
    if relevance < 2 and bull + bear == 0:
        return None
    net = bull - bear
    if net > 0:
        label = "Bullish"
    elif net < 0:
        label = "Bearish"
    else:
        label = "Neutral"
    return {
        "ticker": _raw_code(stock_code),
        "relevance_score": float(relevance),
        "sentiment_score": float(net),
        "sentiment_label": label,
    }


def _normalize_news_item(item: dict) -> dict | None:
    """Normalize a raw news item from any source to the standard format.

    Required fields: title, url, source, summary, time_published,
                     overall_sentiment_score, overall_sentiment_label,
                     ticker_sentiment, topics
    """
    title = (item.get("title") or "").strip()
    if not title:
        return None

    url = (item.get("url") or "").strip()
    source = (item.get("source") or "Unknown").strip()
    summary = (item.get("summary") or item.get("raw_content") or title)[:300]
    time_published = item.get("time_published", "")

    # Compute overall sentiment from title + summary
    text = f"{title} {summary}"
    bull, bear, _ = _score_sentiment(text)
    net = bull - bear
    if net > 0:
        sentiment_label = "Bullish"
    elif net < 0:
        sentiment_label = "Bearish"
    else:
        sentiment_label = "Neutral"

    # Extract topic tags
    topics = _extract_topics(text)

    return {
        "title": title,
        "url": url,
        "source": source,
        "summary": summary,
        "time_published": time_published,
        "overall_sentiment_score": float(net),
        "overall_sentiment_label": sentiment_label,
        "ticker_sentiment": [],
        "topics": topics,
    }


def _dedupe_news_items(items: list[dict]) -> list[dict]:
    """Deduplicate by URL (fallback: title + source), sort by time newest-first."""
    seen: set[str] = set()
    deduped: list[dict] = []
    # Sort by time descending (newest first), items with empty time go last
    for item in sorted(items, key=lambda r: r.get("time_published", ""), reverse=True):
        key = item.get("url", "")
        if not key:
            key = f'{item.get("title", "")}::{item.get("source", "")}'
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def _score_stock_relevance(text: str, stock_name: str, stock_code: str,
                           category: str | None) -> int:
    score = 0
    raw = _raw_code(stock_code)
    if stock_name in text:
        score += 5
    if raw in text:
        score += 4
    if stock_code in text:
        score += 4
    if category and category in _SECTOR_KEYWORDS:
        for sector_kw in _SECTOR_KEYWORDS[category]:
            if sector_kw in text:
                score += 1
                break
    short_name = stock_name[:2] if len(stock_name) >= 2 else stock_name
    if short_name in text and short_name not in ("股份", "集团", "有限", "科技"):
        score += 1
    return score


# ═══════════════════════════════════════════════════════════════════════════
# News Summary Builder (Requirement 3)
# ═══════════════════════════════════════════════════════════════════════════

def _build_news_summary(items: list[dict]) -> dict:
    """Build aggregate summary from normalized news items.

    Returns: {item_count, activity_level, top_source, highlight_symbols,
              sentiment_breakdown, latest_headline, latest_item_time}
    """
    if not items:
        return {
            "item_count": 0,
            "activity_level": "quiet",
            "top_source": None,
            "highlight_symbols": [],
            "sentiment_breakdown": {},
            "latest_headline": None,
            "latest_item_time": None,
        }

    source_counter = Counter(item["source"] for item in items if item.get("source"))
    sentiment_counter = Counter(
        (item.get("overall_sentiment_label") or "neutral").lower()
        for item in items
    )
    symbol_counter: Counter[str] = Counter()
    for item in items:
        for ts in item.get("ticker_sentiment", []) or []:
            t = ts.get("ticker")
            if t:
                symbol_counter[t] += 1

    count = len(items)
    if count >= 16:
        activity_level = "elevated"
    elif count >= 8:
        activity_level = "active"
    elif count > 0:
        activity_level = "calm"
    else:
        activity_level = "quiet"

    return {
        "item_count": count,
        "activity_level": activity_level,
        "top_source": source_counter.most_common(1)[0][0] if source_counter else None,
        "source_breakdown": dict(source_counter.most_common(5)),
        "highlight_symbols": [s for s, _ in symbol_counter.most_common(5)],
        "sentiment_breakdown": dict(sentiment_counter),
        "latest_headline": items[0]["title"],
        "latest_item_time": items[0].get("time_published"),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Macro Signals Builder (Requirement 4)
# ═══════════════════════════════════════════════════════════════════════════

def _build_macro_signals() -> tuple[list[dict], dict]:
    """Build A-share macro regime signals using ETF proxies.

    Signals:
      - broad_trend: 沪深300ETF 20-day return
      - growth_vs_defensive: 创业板ETF vs 红利ETF spread
      - safe_haven_pressure: 黄金ETF return
      - Sector rotation via news sentiment

    Returns (signals_list, meta_dict)
    """
    series_broad = fetch_daily_kline(MACRO_ETF_SYMBOLS["broad"], 30)
    series_growth = fetch_daily_kline(MACRO_ETF_SYMBOLS["growth"], 30)
    series_defensive = fetch_daily_kline(MACRO_ETF_SYMBOLS["defensive"], 30)
    series_safe = fetch_daily_kline(MACRO_ETF_SYMBOLS["safe_haven"], 30)

    broad_return = _calc_return_pct(series_broad, MACRO_SIGNAL_LOOKBACK_DAYS)
    growth_return = _calc_return_pct(series_growth, MACRO_SIGNAL_LOOKBACK_DAYS)
    defensive_return = _calc_return_pct(series_defensive, MACRO_SIGNAL_LOOKBACK_DAYS)
    safe_return = _calc_return_pct(series_safe, MACRO_SIGNAL_LOOKBACK_DAYS)

    signals: list[dict] = []

    # Signal 1: Broad market trend (沪深300)
    if broad_return is not None:
        if broad_return >= 5:
            status, expl, expl_zh = "bullish", "沪深300近20日趋势向上，市场整体偏强", "沪深300近20日趋势向上，市场整体偏强"
        elif broad_return <= -5:
            status, expl, expl_zh = "defensive", "沪深300近20日明显走弱，市场整体防御", "沪深300近20日明显走弱，市场整体防御"
        else:
            status, expl, expl_zh = "neutral", "沪深300近20日走势震荡，方向不明", "沪深300近20日走势震荡，方向不明"
        signals.append({
            "id": "broad_trend",
            "label": "Broad Trend",
            "label_zh": "大盘趋势",
            "status": status,
            "value": round(broad_return, 2),
            "unit": "%",
            "lookback_days": MACRO_SIGNAL_LOOKBACK_DAYS,
            "explanation": expl,
            "explanation_zh": expl_zh,
            "source": "sina_daily_kline",
            "as_of": series_broad[0]["date"] if series_broad else None,
        })

    # Signal 2: Growth vs Defensive spread
    if growth_return is not None and defensive_return is not None:
        spread = growth_return - defensive_return
        if spread >= 5:
            status, expl, expl_zh = "bullish", "成长风格显著跑赢红利，风险偏好上升", "成长风格显著跑赢红利，风险偏好上升"
        elif spread <= -5:
            status, expl, expl_zh = "defensive", "红利风格跑赢成长，市场偏向防御", "红利风格跑赢成长，市场偏向防御"
        else:
            status, expl, expl_zh = "neutral", "成长与防御风格相对均衡", "成长与防御风格相对均衡"
        signals.append({
            "id": "growth_vs_defensive",
            "label": "Growth vs Defensive",
            "label_zh": "成长 vs 防御",
            "status": status,
            "value": round(spread, 2),
            "unit": "spread_pct",
            "lookback_days": MACRO_SIGNAL_LOOKBACK_DAYS,
            "explanation": expl,
            "explanation_zh": expl_zh,
            "source": "sina_daily_kline",
            "as_of": series_growth[0]["date"] if series_growth else None,
        })

    # Signal 3: Safe-haven pressure (黄金ETF)
    if safe_return is not None:
        if safe_return >= 5:
            status, expl, expl_zh = "defensive", "黄金ETF近期走强，避险需求上升", "黄金ETF近期走强，避险需求上升"
        elif safe_return <= 0:
            status, expl, expl_zh = "bullish", "黄金ETF走平或回落，避险需求偏低", "黄金ETF走平或回落，避险需求偏低"
        else:
            status, expl, expl_zh = "neutral", "黄金ETF温和上涨，避险需求存在但不极端", "黄金ETF温和上涨，避险需求存在但不极端"
        signals.append({
            "id": "safe_haven_pressure",
            "label": "Safe-haven Pressure",
            "label_zh": "避险压力",
            "status": status,
            "value": round(safe_return, 2),
            "unit": "%",
            "lookback_days": MACRO_SIGNAL_LOOKBACK_DAYS,
            "explanation": expl,
            "explanation_zh": expl_zh,
            "source": "sina_daily_kline",
            "as_of": series_safe[0]["date"] if series_safe else None,
        })

    # Signal 4: News macro tone
    macro_news_tone = _build_macro_news_tone()
    signals.append(macro_news_tone)

    # Aggregate verdict
    bullish_count = sum(1 for s in signals if s.get("status") == "bullish")
    defensive_count = sum(1 for s in signals if s.get("status") == "defensive")
    total = len(signals)

    if bullish_count >= defensive_count + 2:
        verdict = "bullish"
        summary = "宏观信号整体偏多，风险偏好占优。"
    elif defensive_count >= bullish_count + 2:
        verdict = "defensive"
        summary = "宏观信号整体偏防御，注意控制仓位风险。"
    else:
        verdict = "neutral"
        summary = "宏观信号分化，尚未形成明确方向。"

    meta = {
        "summary": summary,
        "summary_zh": summary,
        "bullish_count": bullish_count,
        "defensive_count": defensive_count,
        "total_count": total,
        "latest_prices": {
            "510300": round(series_broad[0]["close"], 2) if series_broad else None,
            "159915": round(series_growth[0]["close"], 2) if series_growth else None,
            "510880": round(series_defensive[0]["close"], 2) if series_defensive else None,
            "518880": round(series_safe[0]["close"], 2) if series_safe else None,
        },
    }

    return signals, {
        "verdict": verdict,
        "bullish_count": bullish_count,
        "defensive_count": defensive_count,
        "total_count": total,
        "meta": meta,
    }


def _build_macro_news_tone() -> dict:
    """Derive macro news tone from the latest news summary."""
    summary = _get_cached_news_summary()
    if not summary or not summary.get("sentiment_breakdown"):
        return {
            "id": "macro_news_tone",
            "label": "Macro News Tone",
            "label_zh": "宏观新闻语气",
            "status": "neutral",
            "value": 0,
            "explanation": "宏观新闻快照暂未生成",
            "explanation_zh": "宏观新闻快照暂未生成",
            "source": "news_summary",
        }

    sb = summary["sentiment_breakdown"]
    positive = sb.get("bullish", 0)
    negative = sb.get("bearish", 0)
    tone_score = positive - negative

    if tone_score >= 5:
        status, expl, expl_zh = "bullish", "宏观新闻流整体偏积极", "宏观新闻流整体偏积极"
    elif tone_score <= -5:
        status, expl, expl_zh = "defensive", "宏观新闻流整体偏防御", "宏观新闻流整体偏防御"
    else:
        status, expl, expl_zh = "neutral", "宏观新闻流多空交织", "宏观新闻流多空交织"

    return {
        "id": "macro_news_tone",
        "label": "Macro News Tone",
        "label_zh": "宏观新闻语气",
        "status": status,
        "value": tone_score,
        "explanation": expl,
        "explanation_zh": expl_zh,
        "source": "news_summary",
    }


def get_macro_signals() -> dict:
    """Return cached macro signals, or build fresh if expired."""
    global _macro_signals_cache, _macro_signals_time
    now = time.time()
    if _macro_signals_cache and (now - _macro_signals_time) < MACRO_CACHE_TTL:
        return _macro_signals_cache

    try:
        signals, meta = _build_macro_signals()
        _macro_signals_cache = {
            "available": True,
            "verdict": meta["verdict"],
            "bullish_count": meta["bullish_count"],
            "defensive_count": meta["defensive_count"],
            "total_count": meta["total_count"],
            "signals": signals,
            "meta": meta["meta"],
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        _macro_signals_time = now
    except Exception as e:
        if not _macro_signals_cache:
            _macro_signals_cache = {"available": False, "error": str(e)}
        _macro_signals_time = now
    return _macro_signals_cache


# ═══════════════════════════════════════════════════════════════════════════
# ETF Flow Snapshot (Requirement 5 & 6)
# ═══════════════════════════════════════════════════════════════════════════

def _build_etf_flow_snapshot() -> tuple[list[dict], dict]:
    """Build ETF flow snapshot for major A-share ETFs.

    Algorithm (Requirement 5):
      flow_score = price_change_pct × max(volume_ratio, 0.1)

    Direction (Requirement 5 & 6):
      flow_score ≥ 2.5  → inflow
      flow_score ≤ -2.5 → outflow
      else → mixed

    Share change monitoring (Requirement 6):
      Uses volume as proxy for share flow direction.
    """
    etf_rows: list[dict] = []
    for symbol in ETF_FLOW_SYMBOLS:
        series = fetch_daily_kline(symbol, 10)
        if len(series) <= ETF_FLOW_BASELINE_VOLUME_DAYS:
            continue

        latest = series[0]
        previous = series[ETF_FLOW_LOOKBACK_DAYS]
        latest_close = float(latest["close"])
        previous_close = float(previous["close"])
        latest_volume = float(latest.get("volume", 0))
        avg_volume = _calc_average_volume(series, 1, ETF_FLOW_BASELINE_VOLUME_DAYS) or latest_volume or 1.0

        if previous_close == 0:
            continue

        price_change_pct = ((latest_close / previous_close) - 1.0) * 100.0
        volume_ratio = latest_volume / avg_volume if avg_volume else 1.0
        flow_score = price_change_pct * max(volume_ratio, 0.1)

        # Direction from flow_score
        if flow_score >= 2.5:
            direction = "inflow"
        elif flow_score <= -2.5:
            direction = "outflow"
        else:
            direction = "mixed"

        # Volume proxy for share change (Requirement 6)
        # Volume surge = likely share creation, Volume contraction = likely redemption
        if volume_ratio >= 1.5:
            volume_signal = "expansion"    # 份额扩张
        elif volume_ratio <= 0.5:
            volume_signal = "contraction"  # 份额收缩
        else:
            volume_signal = "stable"       # 份额稳定

        # Calculate trend over 5 days for share change estimate
        oldest_vol = float(series[min(len(series) - 1, 5)].get("volume", 0)) if len(series) > 5 else latest_volume
        share_change_estimate = ((latest_volume / oldest_vol) - 1.0) * 100 if oldest_vol > 0 else 0

        etf_rows.append({
            "symbol": _raw_code(symbol),
            "sina_code": symbol,
            "price_change_pct": round(price_change_pct, 2),
            "latest_volume": int(latest_volume),
            "avg_volume": int(avg_volume),
            "volume_ratio": round(volume_ratio, 2),
            "flow_score": round(flow_score, 2),
            "direction": direction,
            "volume_signal": volume_signal,
            "share_change_estimate_pct": round(share_change_estimate, 2),
            "as_of": latest["date"],
        })

    etf_rows.sort(key=lambda r: abs(float(r["flow_score"])), reverse=True)

    inflow_count = sum(1 for r in etf_rows if r["direction"] == "inflow")
    outflow_count = sum(1 for r in etf_rows if r["direction"] == "outflow")
    expansion_count = sum(1 for r in etf_rows if r["volume_signal"] == "expansion")
    contraction_count = sum(1 for r in etf_rows if r["volume_signal"] == "contraction")
    net_score = round(sum(float(r["flow_score"]) for r in etf_rows), 2)

    if inflow_count >= outflow_count + 3 and net_score > 0:
        direction = "inflow"
        summary_text = "ETF整体资金方向偏流入，机构资金积极。"
    elif outflow_count >= inflow_count + 3 and net_score < 0:
        direction = "outflow"
        summary_text = "ETF整体资金方向偏流出，注意避险情绪。"
    else:
        direction = "mixed"
        summary_text = "ETF资金方向分化，无明显趋势。"

    summary = {
        "direction": direction,
        "summary": summary_text,
        "summary_zh": summary_text,
        "inflow_count": inflow_count,
        "outflow_count": outflow_count,
        "expansion_count": expansion_count,     # 份额扩张 ETF 数
        "contraction_count": contraction_count,  # 份额收缩 ETF 数
        "tracked_count": len(etf_rows),
        "net_score": net_score,
        "is_estimated": True,
    }

    return etf_rows, summary


def get_etf_flows() -> dict:
    """Return cached ETF flow snapshot, or build fresh if expired."""
    global _etf_flow_cache, _etf_flow_time
    now = time.time()
    if _etf_flow_cache and (now - _etf_flow_time) < ETF_FLOW_CACHE_TTL:
        return _etf_flow_cache

    try:
        etfs, summary = _build_etf_flow_snapshot()
        _etf_flow_cache = {
            "available": True,
            "summary": summary,
            "etfs": etfs,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        _etf_flow_time = now
    except Exception as e:
        if not _etf_flow_cache:
            _etf_flow_cache = {"available": False, "error": str(e)}
        _etf_flow_time = now
    return _etf_flow_cache


# ═══════════════════════════════════════════════════════════════════════════
# Market Sentiment Aggregator (Dashboard)
# ═══════════════════════════════════════════════════════════════════════════

def get_market_sentiment() -> dict:
    """Aggregate macro, ETF flow, and news sentiment into a dashboard summary.

    Reads from in-memory caches only - never blocks on network I/O.
    """
    global _macro_signals_cache, _etf_flow_cache, _news_summary_cache
    macro = _macro_signals_cache if _macro_signals_cache else {"available": False}
    etf = _etf_flow_cache if _etf_flow_cache else {"available": False}
    news = _news_summary_cache if _news_summary_cache else {}

    has_macro = macro.get("available", False)
    has_etf = etf.get("available", False)
    has_news = bool(news.get("item_count", 0))

    if not (has_macro or has_etf or has_news):
        return {
            "available": False,
            "mood": "neutral",
            "mood_label": "等待数据",
            "mood_summary": "市场情绪数据正在首次采集中，请稍候...",
            "score": 0,
            "gauge_pct": 50,
            "signals": {
                "macro": {"verdict": "unknown", "verdict_label": "等待中", "bullish_pct": 0, "detail": ""},
                "etf_flow": {"verdict": "unknown", "verdict_label": "等待中", "net_score": 0, "detail": ""},
                "news": {"verdict": "unknown", "verdict_label": "等待中", "bullish_pct": 0, "activity": "quiet", "detail": ""},
            },
            "updated_at": datetime.now().strftime("%m-%d %H:%M"),
        }

    # ── Macro signal ──
    if has_macro:
        m_verdict = macro.get("verdict", "neutral")
        m_bullish = macro.get("bullish_count", 0)
        m_total = macro.get("total_count", 4)
        m_bullish_pct = round(m_bullish / m_total * 100) if m_total else 50
        _label_map = {"bullish": "偏多", "defensive": "偏空", "neutral": "中性"}
        m_label = _label_map.get(m_verdict, "未知")
        if m_verdict == "bullish":
            m_detail = f"{m_bullish}/{m_total} 信号偏多"
        elif m_verdict == "defensive":
            m_detail = f"{macro.get('defensive_count', 0)}/{m_total} 信号偏空"
        else:
            m_detail = "信号分化"
    else:
        m_verdict = "unknown"
        m_label = "等待中"
        m_bullish_pct = 0
        m_detail = "宏观数据获取中..."

    # ── ETF flow ──
    if has_etf:
        e_summary = etf.get("summary", {})
        e_dir = e_summary.get("direction", "mixed")
        e_label = {"inflow": "流入", "outflow": "流出", "mixed": "分化"}.get(e_dir, "未知")
        e_net = e_summary.get("net_score", 0)
        if e_net >= 0:
            e_detail = "净流入 {:.1f}".format(abs(e_net))
        else:
            e_detail = "净流出 {:.1f}".format(abs(e_net))
    else:
        e_dir = "unknown"
        e_label = "等待中"
        e_net = 0
        e_detail = "ETF数据获取中..."

    # ── News sentiment ──
    if has_news:
        sb = news.get("sentiment_breakdown", {})
        n_bull = sb.get("bullish", 0)
        n_bear = sb.get("bearish", 0)
        n_neut = sb.get("neutral", 0)
        n_total = n_bull + n_bear + n_neut
        n_bullish_pct = round(n_bull / n_total * 100) if n_total else 50
        n_activity = news.get("activity_level", "quiet")
        if n_bull > n_bear:
            n_verdict = "bullish"
            n_label = "偏积极"
        elif n_bear > n_bull:
            n_verdict = "bearish"
            n_label = "偏消极"
        else:
            n_verdict = "neutral"
            n_label = "中性"
        n_detail = f"{n_bull}\u2191 {n_bear}\u2193"
        if n_activity != "quiet":
            act_cn = {"elevated": "活跃", "active": "正常", "calm": "平静"}.get(n_activity, "")
            n_detail += f" {act_cn}"
    else:
        n_verdict = "unknown"
        n_label = "等待中"
        n_bullish_pct = 0
        n_activity = "quiet"
        n_detail = "新闻数据获取中..."

    # ── Overall mood score ──
    score = 0
    if m_verdict == "bullish":
        score += 1
    elif m_verdict == "defensive":
        score -= 1
    if e_dir == "inflow":
        score += 1
    elif e_dir == "outflow":
        score -= 1
    if n_verdict == "bullish":
        score += 1
    elif n_verdict == "bearish":
        score -= 1

    if score >= 2:
        mood = "bullish"
        mood_label = "乐观"
    elif score <= -2:
        mood = "defensive"
        mood_label = "谨慎"
    else:
        mood = "neutral"
        mood_label = "中性"

    # ── Mood summary ──
    parts = []
    if has_macro and m_verdict != "neutral":
        parts.append(f"宏观{m_label}")
    if has_etf and e_dir != "mixed":
        parts.append(f"资金{e_label}")
    if has_news and n_verdict != "neutral":
        parts.append(f"新闻{n_label}")
    if parts:
        mood_summary = "、".join(parts) + f"，市场情绪偏{mood_label}"
    else:
        mood_summary = "各维度信号中性，市场方向不明朗"

    return {
        "available": True,
        "mood": mood,
        "mood_label": mood_label,
        "mood_summary": mood_summary,
        "score": score,
        "gauge_pct": round((score + 3) / 6 * 100),
        "signals": {
            "macro": {"verdict": m_verdict, "verdict_label": m_label, "bullish_pct": m_bullish_pct, "detail": m_detail},
            "etf_flow": {"verdict": e_dir, "verdict_label": e_label, "net_score": round(e_net, 1), "detail": e_detail},
            "news": {"verdict": n_verdict, "verdict_label": n_label, "bullish_pct": n_bullish_pct, "activity": n_activity, "detail": n_detail},
        },
        "updated_at": datetime.now().strftime("%m-%d %H:%M"),
    }


# ═══════════════════════════════════════════════════════════════════════════
# LLM Integration (Requirement 7)
# ═══════════════════════════════════════════════════════════════════════════

def _call_llm_analysis(stock_code: str, stock_name: str, category: str,
                       position: dict | None,
                       sentiment: dict, price_data: dict,
                       macro_signals: dict, etf_flows: dict,
                       news_summary: dict, relevant_news: list[dict]) -> dict | None:
    """Send analysis data to LLM and return structured recommendation.

    Falls back to None on any error, triggering algorithmic analysis.
    """
    if not _LLM_CONFIG.get("enabled", True):
        return None

    api_url = _LLM_CONFIG.get("api_url", "")
    api_key = _LLM_CONFIG.get("api_key", "")
    model = _LLM_CONFIG.get("model", "deepseek-v4-pro")

    if not api_url or not api_key:
        return None

    # ── Build prompt ──
    pos_text = "未持仓"
    if position:
        shares = position.get("shares", 0)
        cost = position.get("cost", 0)
        pnl = position.get("pnl_pct", 0)
        pos_text = f"持仓{shares}股, 成本{cost:.3f}, 浮动盈亏{pnl:.2f}%"

    macro_text = json.dumps({
        "verdict": macro_signals.get("verdict"),
        "signals": macro_signals.get("signals", [])[:4],
    }, ensure_ascii=False, indent=2)

    etf_text = json.dumps({
        "direction": etf_flows.get("summary", {}).get("direction"),
        "summary": etf_flows.get("summary", {}).get("summary"),
        "details": etf_flows.get("etfs", [])[:5],
    }, ensure_ascii=False, indent=2)

    tech_text = json.dumps({
        "price": price_data.get("price"),
        "change_pct": price_data.get("change_pct"),
        "support": price_data.get("nearest_support"),
        "resistance": price_data.get("nearest_resistance"),
    }, ensure_ascii=False)

    news_items_text = json.dumps([{
        "title": n.get("title"),
        "source": n.get("source"),
        "sentiment": n.get("overall_sentiment_label"),
        "score": n.get("overall_sentiment_score"),
    } for n in relevant_news[:5]], ensure_ascii=False, indent=2)

    prompt = f"""你是一位专业的A股市场分析师。基于以下数据，为 {stock_name}（{stock_code}，行业：{category}）提供结构化的交易建议。

## 持仓信息
{pos_text}

## 宏观环境
{macro_text}

## ETF资金流向
{etf_text}

## 技术面
{tech_text}

## 新闻面分析
- 情感标签: {sentiment.get("sentiment_label")}
- 情感分数: {sentiment.get("sentiment_score")}
- 提及次数: {sentiment.get("total_mentions")}
- 看多因素: {json.dumps(sentiment.get("bullish_factors", []), ensure_ascii=False)}
- 看空因素: {json.dumps(sentiment.get("bearish_factors", []), ensure_ascii=False)}
- 活跃度: {news_summary.get("activity_level")}
- 情绪分布: {json.dumps(news_summary.get("sentiment_breakdown", {}), ensure_ascii=False)}

## 相关新闻
{news_items_text}

## 输出要求
返回纯JSON（不要markdown代码块），结构如下：
{{
  "recommendation": "加仓/减仓/继续持有/清仓/观望",
  "action": "buy/sell/hold/wait",
  "confidence": "高/中/低",
  "summary": "一句话中文总结",
  "reasons": ["看多理由1", "看多理由2"],
  "risks": ["风险1", "风险2"],
  "trade_plan": {{  // 仅持仓且需要买卖时
    "action": "buy",
    "shares": 整数股数,
    "price": 目标价格,
    "price_range": [下限, 上限],
    "target_price": 目标价,
    "stop_loss": 止损价,
    "reasoning": "操作理由"
  }},
  "watch_plan": {{  // 仅未持仓时
    "entry_price": 入场价,
    "entry_condition": "入场条件",
    "target_price": 目标价,
    "stop_loss": 止损价
  }}
}}

JSON:"""

    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2048,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "StockMonitor/1.0",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
    except Exception as e:
        print(f"[llm] API调用失败: {e}", file=sys.stderr)
        return None

    try:
        response = json.loads(raw)
        content = ""
        choices = response.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            content = msg.get("content", "")
        if not content:
            return None

        # Strip markdown code blocks
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r'^```\w*\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

        result = json.loads(content)
        if isinstance(result, dict) and "recommendation" in result:
            return result
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[llm] 解析响应失败: {e}", file=sys.stderr)

    return None


# ═══════════════════════════════════════════════════════════════════════════
# Sentiment Analysis
# ═══════════════════════════════════════════════════════════════════════════

def _analyze_news_for_stock(normalized_news: list[dict], stock_name: str,
                            stock_code: str, category: str | None) -> dict:
    """Analyze all normalized news items for relevance and sentiment to a stock."""
    relevant = []
    total_bullish = 0
    total_bearish = 0
    bull_factors: list[str] = []
    bear_factors: list[str] = []

    for item in normalized_news:
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        relevance = _score_stock_relevance(text, stock_name, stock_code, category)
        if relevance < 2:
            continue

        bull, bear, matched = _score_sentiment(text)
        total_bullish += bull
        total_bearish += bear

        sentiment = "neutral"
        if bull > bear:
            sentiment = "bullish"
        elif bear > bull:
            sentiment = "bearish"

        # Attach ticker-level sentiment to the news item
        tk_sent = _compute_ticker_sentiment(text, stock_name, stock_code)
        if tk_sent:
            item["ticker_sentiment"].append(tk_sent)

        relevant.append(item)

        if bull > 0:
            for m in matched:
                if m.startswith("+"):
                    bull_factors.append(m[1:])
        if bear > 0:
            for m in matched:
                if m.startswith("-"):
                    bear_factors.append(m[1:])

    bull_factors = list(dict.fromkeys(bull_factors))[:5]
    bear_factors = list(dict.fromkeys(bear_factors))[:5]

    net_bullish = total_bullish - total_bearish
    if net_bullish >= 3:
        label = "bullish"
    elif net_bullish <= -3:
        label = "bearish"
    else:
        label = "neutral"

    relevant.sort(key=lambda x: (x.get("time_published", ""),
                                  len(x.get("ticker_sentiment", [])),
                                  abs(x.get("overall_sentiment_score", 0))),
                  reverse=True)

    return {
        "relevant_news": relevant[:8],
        "sentiment_score": net_bullish,
        "sentiment_label": label,
        "bullish_factors": bull_factors,
        "bearish_factors": bear_factors,
        "total_mentions": len(relevant),
    }


# ═══════════════════════════════════════════════════════════════════════════
# Technical Levels
# ═══════════════════════════════════════════════════════════════════════════

def _get_technical_levels(stock_code: str) -> dict:
    from price_fetcher import fetch_prices_batch, get_current_fx_rate

    try:
        from config import _CONFIG_PATH
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        sina_url = cfg["sina_api"]["base_url"]
    except Exception:
        sina_url = "http://hq.sinajs.cn/list={codes}"

    prices = fetch_prices_batch([stock_code], sina_url, timeout=3)
    sp = prices.get(stock_code)
    if not sp or sp.price <= 0 or sp.prev_close <= 0:
        return {"available": False}

    change_pct = (sp.price - sp.prev_close) / sp.prev_close * 100
    is_hk = stock_code.startswith("rt_hk")
    price = sp.price
    if is_hk:
        fx = get_current_fx_rate()
        price = sp.price * fx if fx > 0 else sp.price

    pc = sp.prev_close
    hi = sp.high
    lo = sp.low

    supports = sorted([lo, round(price * 0.98, 2), round(price * 0.95, 2),
                       round(price * 0.90, 2)], reverse=True)
    supports = [s for s in supports if s < price][:3]

    resistances = sorted([hi, round(price * 1.02, 2), round(price * 1.05, 2),
                          round(price * 1.10, 2)])
    resistances = [r for r in resistances if r > price][:3]

    nearest_support = supports[0] if supports else round(price * 0.98, 2)
    nearest_resistance = resistances[0] if resistances else round(price * 1.02, 2)
    dist_to_support = round((price - nearest_support) / price * 100, 2)
    dist_to_resistance = round((nearest_resistance - price) / price * 100, 2)

    return {
        "available": True,
        "price": round(price, 3),
        "prev_close": round(pc, 3),
        "change_pct": round(change_pct, 2),
        "volume": sp.volume,
        "high": hi,
        "low": lo,
        "support_levels": supports,
        "resistance_levels": resistances,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "dist_to_support_pct": dist_to_support,
        "dist_to_resistance_pct": dist_to_resistance,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Algorithmic Trade Advice (fallback when LLM unavailable)
# ═══════════════════════════════════════════════════════════════════════════

def _generate_trade_advice(sentiment: dict, price_data: dict,
                           stock_name: str, position: dict | None = None,
                           macro_signals: dict | None = None,
                           etf_flows: dict | None = None) -> dict:
    sent_score = sentiment.get("sentiment_score", 0)
    sent_label = sentiment.get("sentiment_label", "neutral")
    bull_factors = sentiment.get("bullish_factors", [])
    bear_factors = sentiment.get("bearish_factors", [])
    mention_count = sentiment.get("total_mentions", 0)
    price_avail = price_data.get("available", False)

    reasons: list[str] = []
    risks: list[str] = []
    score = 0.0
    has_position = position is not None and position.get("shares", 0) > 0

    # ── News sentiment ──
    if sent_label == "bullish":
        score += sent_score * 0.5
        reasons.append("近期相关新闻整体偏向正面，多头情绪占优")
    elif sent_label == "bearish":
        score -= abs(sent_score) * 0.5
        risks.append("近期相关新闻偏向负面，需关注风险因素")

    if mention_count >= 5:
        reasons.append(f"市场关注度较高，近期有{mention_count}条相关资讯")

    for f in bull_factors[:3]:
        reasons.append(f"利好因素: {f}")
        score += 0.3
    for f in bear_factors[:3]:
        risks.append(f"风险因素: {f}")
        score -= 0.3

    # ── Macro signals ──
    if macro_signals and macro_signals.get("available"):
        verdict = macro_signals.get("verdict", "neutral")
        if verdict == "bullish":
            reasons.append("宏观环境偏多，市场风险偏好上升")
            score += 0.5
        elif verdict == "defensive":
            risks.append("宏观环境偏防御，建议控制仓位")
            score -= 0.5

    # ── ETF flow ──
    if etf_flows and etf_flows.get("available"):
        etf_dir = etf_flows.get("summary", {}).get("direction", "mixed")
        if etf_dir == "inflow":
            reasons.append("ETF整体资金流入，机构看多情绪较浓")
            score += 0.3
        elif etf_dir == "outflow":
            risks.append("ETF整体资金流出，注意市场情绪转弱")
            score -= 0.3

    # ── Price data ──
    current_price = 0.0
    if price_avail:
        change_pct = price_data.get("change_pct", 0)
        current_price = price_data.get("price", 0)
        vol = price_data.get("volume", 0)

        if change_pct >= 3:
            reasons.append(f"今日涨幅{change_pct:.1f}%，短线动能强劲")
            score += 1.0
        elif change_pct >= 1:
            reasons.append(f"今日上涨{change_pct:.1f}%，走势稳健")
            score += 0.5
        elif change_pct <= -3:
            risks.append(f"今日跌幅{abs(change_pct):.1f}%，短线回调明显")
            score -= 1.0
        elif change_pct <= -1:
            risks.append(f"今日下跌{abs(change_pct):.1f}%，走势偏弱")
            score -= 0.5

        if vol > 100_000_000:
            reasons.append("今日成交量较大，资金关注度高")
            score += 0.3
        elif 0 < vol < 10_000_000:
            risks.append("今日成交量偏低，流动性偏弱")
            score -= 0.2
    else:
        reasons.append("当前为非交易时段，基于新闻面分析")

    # ── Position-aware scoring ──
    pnl_pct = 0.0
    cost = 0.0
    shares_held = 0
    if has_position:
        pnl_pct = position.get("pnl_pct", 0) or 0
        cost = position.get("cost", 0) or 0
        shares_held = position.get("shares", 0) or 0

        if pnl_pct >= 20:
            reasons.append(f"持仓浮盈{pnl_pct:.1f}%，已有可观利润")
            score += 0.5
        elif pnl_pct >= 5:
            reasons.append(f"持仓浮盈{pnl_pct:.1f}%，处于盈利状态")
            score += 0.3
        elif pnl_pct <= -15:
            risks.append(f"持仓浮亏{abs(pnl_pct):.1f}%，深度套牢需警惕")
            score -= 1.5
        elif pnl_pct <= -8:
            risks.append(f"持仓浮亏{abs(pnl_pct):.1f}%，短期走弱明显")
            score -= 1.0
        elif pnl_pct <= -5:
            risks.append(f"持仓浮亏{abs(pnl_pct):.1f}%，短期走弱")
            score -= 0.5

        if price_avail:
            dist_to_sup = price_data.get("dist_to_support_pct", 100)
            dist_to_res = price_data.get("dist_to_resistance_pct", 100)
            if dist_to_sup < 3:
                reasons.append(f"股价接近支撑位{price_data.get('nearest_support', 0):.2f}")
            if dist_to_res < 2:
                risks.append(f"股价接近阻力位{price_data.get('nearest_resistance', 0):.2f}")

    # ── Generate recommendation ──
    result: dict = {"reasons": reasons[:5], "risks": risks[:5]}

    if has_position:
        result["position_info"] = {
            "shares": shares_held,
            "cost": round(cost, 3),
            "pnl_pct": round(pnl_pct, 2),
            "current_price": round(current_price, 3) if current_price else None,
        }
        result.update(_gen_holding_advice(
            score, pnl_pct, shares_held, cost, current_price,
            stock_name, price_data, price_avail,
        ))
    else:
        result.update(_gen_watch_advice(score, stock_name, price_data, price_avail))

    return result


def _gen_holding_advice(score: float, pnl_pct: float, shares: int,
                         cost: float, current_price: float,
                         stock_name: str, price_data: dict,
                         price_avail: bool) -> dict:
    trade_plan = None
    ns = price_data.get("nearest_support", 0) if price_avail else 0
    nr = price_data.get("nearest_resistance", 0) if price_avail else 0

    if score >= 3:
        add_shares = max(100, int(shares * 0.15 / 100) * 100)
        ep = ns if ns > 0 else round(current_price * 0.99, 2)
        tp = nr if nr > 0 else round(current_price * 1.08, 2)
        sl = round(min(ns * 0.97, cost * 0.92) if ns and cost else current_price * 0.93, 2)
        recommendation, action, confidence = "加仓", "buy", "高"
        summary = f"{stock_name}多项指标共振看多，建议加仓{add_shares}股，目标价{tp:.2f}"
        trade_plan = {
            "action": "buy", "shares": add_shares, "price": ep,
            "price_range": [round(ep * 0.995, 2), round(ep * 1.005, 2)],
            "target_price": tp, "stop_loss": sl,
            "reasoning": f"信号评分{score:.1f}，技术面偏强，在支撑位{ep:.2f}附近加仓，跌破{sl:.2f}止损",
        }
    elif score >= 1:
        if pnl_pct > 10:
            recommendation, action, confidence = "继续持有", "hold", "中"
            summary = f"{stock_name}走势稳健且已有浮盈{pnl_pct:.1f}%，建议继续持有"
        else:
            add_shares = max(100, int(shares * 0.10 / 100) * 100)
            ep = ns if ns > 0 else round(current_price * 0.98, 2)
            tp = nr if nr > 0 else round(current_price * 1.05, 2)
            sl = round(min(ns * 0.97, cost * 0.93) if ns and cost else current_price * 0.94, 2)
            recommendation, action, confidence = "加仓", "buy", "中"
            summary = f"{stock_name}信号偏多，可轻仓加仓{add_shares}股，目标{tp:.2f}"
            trade_plan = {
                "action": "buy", "shares": add_shares, "price": ep,
                "price_range": [round(ep * 0.99, 2), round(ep * 1.01, 2)],
                "target_price": tp, "stop_loss": sl,
                "reasoning": f"信号评分{score:.1f}，适度看多，在{ep:.2f}附近小幅加仓",
            }
    elif score >= 0:
        recommendation, action, confidence = "继续持有", "hold", "中"
        if pnl_pct > 5:
            summary = f"{stock_name}信号中性，浮盈{pnl_pct:.1f}%，可继续持有观望"
        elif pnl_pct >= -5:
            summary = f"{stock_name}信号中性，持仓成本附近，建议持有等待方向明确"
        else:
            summary = f"{stock_name}信号中性偏弱，浮亏{abs(pnl_pct):.1f}%，持有但需关注止损"
    elif score >= -2:
        if pnl_pct > 15:
            sell_shares = max(100, int(shares * 0.3 / 100) * 100)
            ep = nr if nr > 0 else round(current_price * 1.01, 2)
            recommendation, action, confidence = "减仓", "sell", "中"
            summary = f"{stock_name}信号转弱但浮盈可观({pnl_pct:.1f}%)，建议减仓{sell_shares}股锁定利润"
            trade_plan = {
                "action": "sell", "shares": sell_shares, "price": ep,
                "price_range": [round(ep * 0.99, 2), round(ep * 1.01, 2)],
                "target_price": ns if ns else round(current_price * 0.95, 2),
                "stop_loss": round(current_price * 1.05, 2),
                "reasoning": f"信号评分{score:.1f}偏弱，止盈减仓锁定利润",
            }
        elif pnl_pct <= -8:
            sell_shares = max(100, int(shares * 0.5 / 100) * 100)
            recommendation, action, confidence = "减仓", "sell", "高"
            summary = f"{stock_name}信号偏弱且浮亏{abs(pnl_pct):.1f}%，建议减仓{sell_shares}股控制风险"
            trade_plan = {
                "action": "sell", "shares": sell_shares,
                "price": round(current_price, 2) if current_price else 0,
                "price_range": [round(current_price * 0.99, 2), round(current_price * 1.01, 2)] if current_price else [0, 0],
                "target_price": 0,
                "stop_loss": round(current_price * 0.92, 2) if current_price else 0,
                "reasoning": f"信号评分{score:.1f}，浮亏超8%，减仓止损控制下行风险",
            }
        else:
            recommendation, action, confidence = "继续持有", "hold", "中"
            summary = f"{stock_name}信号偏弱但未触发止损，建议持有观察"
    else:
        if pnl_pct > 5:
            sell_shares = max(100, int(shares * 0.5 / 100) * 100)
            recommendation, action, confidence = "减仓", "sell", "高"
            summary = f"{stock_name}信号共振看空，建议减仓{sell_shares}股保住利润"
        else:
            sell_shares = shares
            recommendation, action, confidence = "清仓", "sell", "高"
            summary = f"{stock_name}信号共振看空，建议清仓{shares}股止损离场"
        ep = round(current_price, 2) if current_price else 0
        trade_plan = {
            "action": "sell", "shares": sell_shares, "price": ep,
            "price_range": [round(ep * 0.99, 2), round(ep * 1.01, 2)] if ep else [0, 0],
            "target_price": ns if ns else 0, "stop_loss": 0,
            "reasoning": f"信号评分{score:.1f}，强烈看空，及时止损控制风险",
        }

    result: dict = {
        "recommendation": recommendation, "action": action,
        "confidence": confidence, "score": round(score, 1), "summary": summary,
    }
    if trade_plan:
        result["trade_plan"] = trade_plan
    return result


def _gen_watch_advice(score: float, stock_name: str, price_data: dict,
                       price_avail: bool) -> dict:
    cp = price_data.get("price", 0) if price_avail else 0
    ns = price_data.get("nearest_support", 0) if price_avail else 0
    nr = price_data.get("nearest_resistance", 0) if price_avail else 0

    if score >= 3:
        confidence = "高"
        summary = f"{stock_name}多项指标看多，但当前未持仓，建议在回调时择机建仓"
        ep = ns if ns else round(cp * 0.97, 2)
        cond = f"等待回调至{ep:.2f}附近企稳后可建仓"
    elif score >= 1:
        confidence = "中"
        summary = f"{stock_name}信号偏多，可观察等待更好的入场时机"
        ep = ns if ns else round(cp * 0.96, 2)
        cond = f"建议等待回调至{ep:.2f}附近再考虑入场"
    elif score >= -1.5:
        confidence = "中"
        summary = f"{stock_name}信号中性，暂不建议入场，保持观望"
        ep = ns if ns else round(cp * 0.95, 2) if cp else 0
        cond = f"需等待明确的多头信号出现，参考支撑位{ep:.2f}"
    else:
        confidence = "中"
        summary = f"{stock_name}信号偏弱，当前不建议买入"
        ep = 0
        cond = "需等待趋势反转信号和底部确认再考虑"

    tp = nr if nr else round(cp * 1.08, 2) if cp else 0
    sl = ns * 0.95 if ns else round(cp * 0.92, 2) if cp else 0

    result: dict = {
        "recommendation": "观望", "action": "wait",
        "confidence": confidence, "score": round(score, 1), "summary": summary,
    }
    if ep > 0 and cp > 0:
        result["watch_plan"] = {
            "entry_price": round(ep, 2), "entry_condition": cond,
            "target_price": round(tp, 2), "stop_loss": round(sl, 2),
        }
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Main Analysis Pipeline
# ═══════════════════════════════════════════════════════════════════════════

def _fetch_all_market_news() -> list[dict]:
    """Fetch news from all sources, normalize, dedupe, return standardized list."""
    all_raw: list[dict] = []

    try:
        all_raw.extend(fetch_cls_telegraph(60))
    except Exception as e:
        print(f"[intel] 财联社获取失败: {e}", file=sys.stderr)

    try:
        all_raw.extend(fetch_jin10_flash(50))
    except Exception as e:
        print(f"[intel] 金十数据获取失败: {e}", file=sys.stderr)

    # Normalize all items
    normalized = []
    for item in all_raw:
        norm = _normalize_news_item(item)
        if norm:
            normalized.append(norm)

    # Dedupe by URL, sort by time
    return _dedupe_news_items(normalized)


def _get_cached_news_summary() -> dict:
    """Return cached news summary or empty dict."""
    global _news_summary_cache
    return _news_summary_cache


def analyze_single_stock(stock_code: str, stock_name: str,
                         category: str | None = None,
                         market_news: list[dict] | None = None,
                         position: dict | None = None) -> dict:
    """Full analysis pipeline for a single stock."""
    # Get price data
    price_data = _get_technical_levels(stock_code)

    # Fetch market-wide news if not provided
    if market_news is None:
        market_news = _fetch_all_market_news()

    # Fetch stock-specific news (A-share only)
    raw_code = _raw_code(stock_code)
    stock_news: list[dict] = []
    if not stock_code.startswith("rt_hk"):
        try:
            raw_stock = fetch_eastmoney_stock_news(raw_code, 10)
            for item in raw_stock:
                norm = _normalize_news_item(item)
                if norm:
                    stock_news.append(norm)
        except Exception:
            pass

    all_news = list(market_news) + stock_news

    # Build news summary (Requirement 3)
    global _news_summary_cache, _news_summary_time
    now = time.time()
    if not _news_summary_cache or (now - _news_summary_time) > NEWS_SUMMARY_CACHE_TTL:
        _news_summary_cache = _build_news_summary(market_news)
        _news_summary_time = now

    # Analyze sentiment
    sentiment = _analyze_news_for_stock(all_news, stock_name, stock_code, category)

    # Get macro signals and ETF flows
    macro_signals = get_macro_signals()
    etf_flows = get_etf_flows()

    # ── Try LLM analysis first, fall back to algorithmic ──
    llm_result = _call_llm_analysis(
        stock_code, stock_name, category or "其它",
        position, sentiment, price_data,
        macro_signals, etf_flows, _news_summary_cache,
        sentiment.get("relevant_news", []),
    )

    if llm_result:
        advice = llm_result
        # Ensure required fields
        advice.setdefault("score", round(sentiment.get("sentiment_score", 0), 1))
        advice.setdefault("reasons", sentiment.get("bullish_factors", [])[:5])
        advice.setdefault("risks", sentiment.get("bearish_factors", [])[:5])
    else:
        advice = _generate_trade_advice(
            sentiment, price_data, stock_name, position,
            macro_signals, etf_flows,
        )

    # Build final result
    result = {
        "status": "ok",
        "code": stock_code,
        "name": stock_name,
        "category": category or "其它",
        "recommendation": advice["recommendation"],
        "action": advice.get("action", "hold"),
        "confidence": advice["confidence"],
        "score": advice["score"],
        "summary": advice["summary"],
        "reasons": advice["reasons"],
        "risks": advice["risks"],
        "sentiment_label": sentiment["sentiment_label"],
        "sentiment_score": sentiment["sentiment_score"],
        "total_mentions": sentiment["total_mentions"],
        "news": sentiment["relevant_news"],
        "news_summary": _news_summary_cache,
        "macro_signals": macro_signals,
        "etf_flows": etf_flows,
        "price": price_data,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if advice.get("trade_plan"):
        result["trade_plan"] = advice["trade_plan"]
    if advice.get("watch_plan"):
        result["watch_plan"] = advice["watch_plan"]
    if advice.get("position_info"):
        result["position_info"] = advice["position_info"]
    return result


# ═══════════════════════════════════════════════════════════════════════════
# Caching & Background Refresh
# ═══════════════════════════════════════════════════════════════════════════

def refresh_hotspot_data(stocks: list[tuple[str, str]],
                         code_to_cat: dict | None = None) -> None:
    global _hotspot_data
    if not stocks:
        return

    code_to_cat = code_to_cat or {}
    print(f"[intel] 开始刷新市场情报 ({len(stocks)} 只股票)...")

    market_news = _fetch_all_market_news()
    print(f"[intel] 获取市场新闻 {len(market_news)} 条")

    new_data = {}
    for code, name in stocks:
        try:
            cat = code_to_cat.get(_raw_code(code))
            result = analyze_single_stock(code, name, cat, market_news)
            new_data[code] = result
        except Exception as e:
            print(f"[intel] {name}({code}) 分析失败: {e}", file=sys.stderr)
            new_data[code] = _empty_result(code, name, str(e))
        time.sleep(0.1)

    with _hotspot_lock:
        _hotspot_data = new_data

    buy_cnt = sum(1 for v in new_data.values() if v.get("action") == "buy")
    sell_cnt = sum(1 for v in new_data.values() if v.get("action") == "sell")
    print(f"[intel] 情报刷新完成: 买入{buy_cnt} 卖出{sell_cnt} 共{len(new_data)}只分析")


def _empty_result(code: str, name: str, error: str = "") -> dict:
    return {
        "status": "error",
        "code": code, "name": name, "category": "其它",
        "recommendation": "观望", "confidence": "低", "score": 0,
        "summary": "暂无足够数据进行分析",
        "reasons": ["数据获取不足，建议稍后刷新"] if not error else [f"分析异常: {error}"],
        "risks": [],
        "sentiment_label": "neutral", "sentiment_score": 0, "total_mentions": 0,
        "news": [], "news_summary": {}, "macro_signals": {}, "etf_flows": {},
        "price": {"available": False},
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def get_hotspot_for_code(sina_code: str) -> dict:
    with _hotspot_lock:
        return _hotspot_data.get(sina_code, _empty_result(sina_code, sina_code))


def get_or_fetch_hotspot(sina_code: str, stock_name: str = "",
                         code_to_cat: dict | None = None,
                         position: dict | None = None) -> dict:
    if not stock_name:
        stock_name = sina_code
    code_to_cat = code_to_cat or {}
    cat = code_to_cat.get(_raw_code(sina_code))
    try:
        result = analyze_single_stock(sina_code, stock_name, cat, position=position)
    except Exception as e:
        result = _empty_result(sina_code, stock_name, str(e))

    with _hotspot_lock:
        _hotspot_data[sina_code] = result
    return result


def get_hotspot_json(sina_code: str) -> str:
    return json.dumps(get_hotspot_for_code(sina_code), ensure_ascii=False)


def refresh_hotspot_loop(stocks: list[tuple[str, str]],
                         code_to_cat: dict | None = None,
                         interval_seconds: int = 300) -> None:
    while True:
        try:
            refresh_hotspot_data(stocks, code_to_cat)
        except Exception as e:
            print(f"[intel] 情报刷新循环异常: {e}", file=sys.stderr)
        time.sleep(interval_seconds)
