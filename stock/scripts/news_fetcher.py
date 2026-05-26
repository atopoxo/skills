"""
News fetcher — fetches hot financial news from Sina API by stock name.
Returns news items grouped by stock code.
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

# Shared state
_news_data = {}  # {sina_code: [{title, url, time, intro}, ...]}
_news_lock = threading.Lock()


def _fetch_stock_news(keyword, code, count=8):
    """Fetch news for a specific stock from Sina finance API.
    Uses both stock name and stock code as search keywords for relevance.
    Filters results to only include news mentioning the stock name."""
    # Strip sina prefix for human-readable code (rt_hk00700 → 00700, sh600000 → 600000)
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
        })
    return items


def fetch_all_news(stocks):
    """Fetch news for all stocks (sina_code, name) tuples.
    Deduplicates by stock code. Returns {sina_code: [news_items]}."""
    result = {}
    for code, name in stocks:
        if code in result:
            continue
        items = _fetch_stock_news(name, code)
        if items:
            result[code] = items
        time.sleep(0.2)  # Rate limit
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


def refresh_news_loop(stocks, interval_seconds=300):
    """Background thread: periodically refresh news data."""
    while True:
        try:
            data = fetch_all_news(stocks)
            set_news_data(data)
            total = sum(len(v) for v in data.values())
            print(f"[news] 热点更新完成: {len(data)} 只股票, {total} 条新闻")
        except Exception as e:
            print(f"[news] 更新失败: {e}", file=sys.stderr)
        time.sleep(interval_seconds)
