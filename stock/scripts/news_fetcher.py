"""
News fetcher — fetches hot financial news from Sina API by stock name.
Scores relevance per stock, filters by threshold, supports multi-stock news sharing.
"""

import json
import sys
import threading
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_SINA_NEWS_API = "https://feed.mix.sina.com.cn/api/roll/get"
_NEWS_FETCH_TIMEOUT = 5
_RELEVANCE_THRESHOLD = 2  # minimum score to include news for a stock

# Shared state
_news_data = {}  # {sina_code: [{title, url, time, intro, score}, ...]}
_news_lock = threading.Lock()


def _relevance_score(title, intro, keyword, display_code, categories=None):
    """Score a news item's relevance to a stock. Higher = more relevant.

    Title match:     +3 (strong signal)
    Code in title:   +3 (strong signal)
    Intro match:     +2 (medium signal)
    Code in intro:   +2 (medium signal)
    Category match:  +1 per match (weak signal — sector-wide news)
    """
    score = 0
    if keyword in title:
        score += 3
    if display_code in title:
        score += 3
    if keyword in intro:
        score += 2
    if display_code in intro:
        score += 2
    if categories:
        for cat in categories:
            if cat in title or cat in intro:
                score += 1
    return score


def _fetch_stock_news(keyword, code, categories=None, count=8):
    """Fetch news for a specific stock and score relevance.
    Only returns items with score >= _RELEVANCE_THRESHOLD."""
    display_code = code
    for prefix in ("rt_hk", "sh", "sz"):
        if display_code.startswith(prefix):
            display_code = display_code[len(prefix):]
            break
    query = f"{keyword} {display_code}"
    params = urllib.parse.urlencode({
        "pageid": "153",
        "lid": "2509",
        "k": query,
        "num": count,
        "page": "1",
    })
    url = f"{_SINA_NEWS_API}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=_NEWS_FETCH_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []

    items = []
    for entry in data.get("result", {}).get("data", []):
        title = entry.get("title", "")
        intro = entry.get("intro", "")
        score = _relevance_score(title, intro, keyword, display_code, categories)
        if score < _RELEVANCE_THRESHOLD:
            continue
        ctime = entry.get("ctime", "")
        try:
            ts = int(ctime)
            ctime = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError, OSError):
            pass
        items.append({
            "title": title,
            "url": entry.get("url", ""),
            "time": ctime,
            "intro": intro,
            "score": score,
        })
    return items


def fetch_all_news(stocks, code_to_cat=None):
    """Fetch news for all stocks (sina_code, name) tuples.
    Deduplicates by stock code. Returns {sina_code: [news_items]}."""
    result = {}
    for code, name in stocks:
        if code in result:
            continue
        categories = None
        if code_to_cat:
            # code_to_cat keys are raw East Money codes (e.g., "00981");
            # sina codes have a prefix (e.g., "rt_hk00981")
            raw_code = code
            for prefix in ("rt_hk", "sh", "sz"):
                if raw_code.startswith(prefix):
                    raw_code = raw_code[len(prefix):]
                    break
            cat = code_to_cat.get(raw_code, "")
            if cat:
                categories = [cat]
        items = _fetch_stock_news(name, code, categories)
        if items:
            result[code] = items
        time.sleep(0.2)
    return result


def set_news_data(data):
    """Atomically replace cached news data."""
    global _news_data
    with _news_lock:
        _news_data = data


def get_news_for_code(code):
    """Return news items for a specific stock code."""
    with _news_lock:
        return _news_data.get(code, [])


def get_news_json(code):
    """Return JSON string of news for the given code."""
    return json.dumps(get_news_for_code(code), ensure_ascii=False)


def refresh_news_loop(stocks, code_to_cat=None, interval_seconds=300):
    """Background thread: periodically refresh news data."""
    while True:
        try:
            data = fetch_all_news(stocks, code_to_cat)
            set_news_data(data)
            total = sum(len(v) for v in data.values())
            print(f"[news] 热点更新完成: {len(data)} 只股票, {total} 条新闻")
        except Exception as e:
            print(f"[news] 更新失败: {e}", file=sys.stderr)
        time.sleep(interval_seconds)
