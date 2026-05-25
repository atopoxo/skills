"""
Real-time stock price fetcher via Sina Finance API.
Refactored from stock_monitor.py for standalone reuse with 1s polling support.
"""

import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime

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
        if len(fields) < 32:
            continue
        try:
            price_val = float(fields[3]) if fields[3] else 0
            prev_close_val = float(fields[2]) if fields[2] else 0
            if price_val <= 0 or prev_close_val <= 0:
                continue
            results[code] = StockPrice(
                code=code,
                name=fields[0],
                open=float(fields[1]) if fields[1] else 0,
                prev_close=prev_close_val,
                price=price_val,
                high=float(fields[4]) if fields[4] else 0,
                low=float(fields[5]) if fields[5] else 0,
                volume=int(float(fields[8])) if fields[8] else 0,
                timestamp=datetime.now(),
            )
        except (ValueError, IndexError):
            continue

    return results
