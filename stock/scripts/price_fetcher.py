"""
Real-time stock price fetcher via Sina Finance API.
Refactored from stock_monitor.py for standalone reuse with 1s polling support.
"""

import json
import re
import sys
import os
import threading
import urllib.request
from dataclasses import dataclass
from datetime import datetime, time as _time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class StockPrice:
    code: str
    name: str
    price: float
    prev_close: float
    open: float
    high: float
    low: float
    volume: int
    timestamp: datetime


def fetch_prices_batch(codes, base_url, timeout=2.0):
    """Fetch real-time prices for multiple stock codes.

    Args:
        codes: list of Sina-format codes like ["sh688008", "sz159599"]
        base_url: URL template with {codes} placeholder
        timeout: HTTP request timeout in seconds

    Returns:
        dict[str, StockPrice] keyed by code. Failed codes are silently omitted.
    """
    if not codes:
        return {}

    url = base_url.format(codes=",".join(codes))
    req = urllib.request.Request(url, headers={"Referer": "http://finance.sina.com.cn"})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("gbk")
    except Exception as e:
        print(f"[price] 获取行情失败: {e}", file=sys.stderr)
        return {}

    results = {}
    for line in raw.strip().split("\n"):
        m = re.match(r'var hq_str_(\w+)="(.*)"', line)
        if not m:
            continue
        code = m.group(1)
        fields = m.group(2).split(",")
        if len(fields) < 6:
            continue
        # HK stocks (rt_hk) have ~20 fields vs A-share 32+ fields
        is_hk = code.startswith("rt_hk")
        if not is_hk and len(fields) < 30:
            continue
        try:
            if is_hk:
                # HK stock fields (rt_hk): [2]=open, [3]=prev_close, [6]=price, [12]=volume
                price_val = float(fields[6]) if fields[6] else 0
                prev_close_val = float(fields[3]) if fields[3] else 0
                open_val = float(fields[2]) if fields[2] else 0
                high_val = float(fields[4]) if fields[4] else 0
                low_val = float(fields[5]) if fields[5] else 0
                vol_val = int(float(fields[12])) if len(fields) > 12 and fields[12] else 0
                name = fields[1] if len(fields) > 1 and fields[1] else fields[0]
            else:
                # A-share: [1]=open, [2]=prev_close, [3]=price, [4]=high, [5]=low, [8]=volume
                price_val = float(fields[3]) if fields[3] else 0
                prev_close_val = float(fields[2]) if fields[2] else 0
                open_val = float(fields[1]) if fields[1] else 0
                high_val = float(fields[4]) if fields[4] else 0
                low_val = float(fields[5]) if fields[5] else 0
                vol_val = int(float(fields[8])) if fields[8] else 0
                name = fields[0]

            if price_val <= 0 or prev_close_val <= 0:
                continue
            results[code] = StockPrice(
                code=code,
                name=name,
                open=open_val,
                prev_close=prev_close_val,
                price=price_val,
                high=high_val,
                low=low_val,
                volume=vol_val,
                timestamp=datetime.now(),
            )
        except (ValueError, IndexError):
            continue

    return results


# ── HKD/CNY real-time exchange rate ──────────────────────────────

_FX_HKD_CNY_URL = "http://hq.sinajs.cn/list=fx_shkdcny"
_fx_lock = threading.Lock()
_fx_rate_live = 0.86        # latest fetched rate (updated every tick)
_fx_rate_closing = 0.86     # frozen at HK close, persisted to cache file
_fx_cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".fx_rate_cache")


def _is_hk_session(now=None):
    """True during HK trading: Mon-Fri, 9:30-12:00 or 13:00-16:00."""
    if now is None:
        now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (_time(9, 30) <= t <= _time(12, 0)) or (_time(13, 0) <= t <= _time(16, 0))

def fetch_hkd_cny_rate(check_time=None, timeout=2.0):
    """Fetch HKD→CNY rate from Sina forex API.

    When check_time is None: returns the current live rate.
    When check_time is a datetime: queries 5-minute K-line data and returns
    the rate of the candle closest to that time (used for closing-rate lookup)."""
    if check_time is None:
        req = urllib.request.Request(
            _FX_HKD_CNY_URL,
            headers={"Referer": "http://finance.sina.com.cn"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("gbk")
            m = re.match(r'var hq_str_(\w+)="(.*)"', raw)
            if m:
                fields = m.group(2).split(",")
                if len(fields) >= 2 and fields[1]:
                    return float(fields[1])
        except Exception:
            pass
        return None

    # Historical rate: query 5-minute K-lines from Sina forex JSONP API
    url = (
        "https://vip.stock.finance.sina.com.cn/forex/api/jsonp.php/"
        "var%20t=/NewForexService.getMinKLine"
        "?symbol=fx_shkdcny&scale=5&datalen=200"
    )
    try:
        req = urllib.request.Request(url, headers={"Referer": "http://finance.sina.com.cn"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        # Strip JSONP wrapper: /*<script>...*/ var t=([...]);
        m = re.search(r"=\((.+)\);?\s*$", raw, re.DOTALL)
        if not m:
            return None
        data = json.loads(m.group(1))
        if not data:
            return None
        best = None
        best_diff = float("inf")
        target_ts = check_time.timestamp()
        for candle in data:
            d = candle.get("d", "")
            try:
                candle_dt = datetime.strptime(d, "%Y-%m-%d %H:%M:%S")
                diff = abs(candle_dt.timestamp() - target_ts)
                if diff < best_diff:
                    best_diff = diff
                    best = candle
            except ValueError:
                continue
        if best:
            close_val = best.get("c", "")
            if close_val:
                return float(close_val)
    except Exception:
        pass
    return None


def update_fx_rate():
    """Fetch the latest HKD/CNY rate. Call on every monitor tick."""
    rate = fetch_hkd_cny_rate()
    if rate is not None and rate > 0:
        global _fx_rate_live
        with _fx_lock:
            _fx_rate_live = rate


def freeze_fx_rate():
    """Save live rate as closing rate and persist to cache file.
    Call when HK market transitions from trading→closed."""
    global _fx_rate_closing
    with _fx_lock:
        _fx_rate_closing = _fx_rate_live


def init_fx_rate(rate=None):
    """Initialize FX rate on startup. Priority order:
    1. K-line query at 16:10 today (closing-time rate from Sina 5-min candles)
    2. Live fetch (last resort)"""
    global _fx_rate_closing, _fx_rate_live

    now = datetime.now()
    if not _is_hk_session(now):
        check_time = now.replace(hour=16, minute=10, second=0, microsecond=0)
        closing_rate = fetch_hkd_cny_rate(check_time=check_time)
        if closing_rate and closing_rate > 0:
            with _fx_lock:
                _fx_rate_closing = closing_rate

    # Always fetch live rate to warm up _fx_rate_live
    live = fetch_hkd_cny_rate()
    if live and live > 0:
        with _fx_lock:
            _fx_rate_live = live


def get_current_fx_rate():
    """Return the effective HKD→CNY rate:
    live rate during HK trading hours, closing rate otherwise."""
    if _is_hk_session():
        with _fx_lock:
            return _fx_rate_live
    with _fx_lock:
        return _fx_rate_closing
