"""
Stock price monitor — fetch real-time prices and alert on significant drops.

Data source: Sina Finance real-time API (free, no auth required).
"""

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import datetime

# Fix Windows console encoding for Chinese output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Default stocks to monitor: (market_code, name)
DEFAULT_STOCKS = [
    ("sh688008", "澜起科技"),
    ("sz159599", "芯片ETF东财"),
]

# Sina API URL template
SINA_API = "http://hq.sinajs.cn/list={codes}"

# Default drop threshold (percentage, positive number)
DEFAULT_THRESHOLD = 0.5

# Cache file to persist baseline prices across sessions
CACHE_FILE = "stock_cache.json"


def fetch_prices(codes):
    """Fetch real-time prices from Sina API. Returns dict: code -> {name, price, prev_close, ...}"""
    url = SINA_API.format(codes=",".join(codes))
    req = urllib.request.Request(url, headers={"Referer": "http://finance.sina.com.cn"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("gbk")
    except Exception as e:
        print(f"[{_now()}] 获取行情失败: {e}", file=sys.stderr)
        return None

    results = {}
    # Parse each line: var hq_str_CODE="field1,field2,...";
    for line in raw.strip().split("\n"):
        m = re.match(r'var hq_str_(\w+)="(.*)"', line)
        if not m:
            continue
        code = m.group(1)
        fields = m.group(2).split(",")
        if len(fields) < 32:
            continue
        try:
            results[code] = {
                "name": fields[0],
                "open": float(fields[1]) if fields[1] else 0,
                "prev_close": float(fields[2]) if fields[2] else 0,
                "price": float(fields[3]) if fields[3] else 0,
                "high": float(fields[4]) if fields[4] else 0,
                "low": float(fields[5]) if fields[5] else 0,
                "volume": int(float(fields[8])) if fields[8] else 0,
                "amount": float(fields[9]) if fields[9] else 0,
                "date": fields[30],
                "time": fields[31],
            }
        except (ValueError, IndexError):
            continue
    return results


def load_cache():
    """Load cached price data from previous session."""
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache):
    """Save price data to cache."""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _now():
    return datetime.now().strftime("%H:%M:%S")


def check_prices(threshold, quiet=False):
    """Fetch and check prices. Returns list of alert dicts."""
    codes = [c for c, _ in DEFAULT_STOCKS]
    data = fetch_prices(codes)
    if data is None:
        return []

    cache = load_cache()
    alerts = []

    for code, display_name in DEFAULT_STOCKS:
        if code not in data:
            if not quiet:
                print(f"[{_now()}] {display_name}({code}): 未获取到数据")
            continue

        d = data[code]
        price = d["price"]
        prev = d["prev_close"]
        name = d["name"]

        if prev <= 0 or price <= 0:
            if not quiet:
                print(f"[{_now()}] {name}({code}): 停牌或数据异常 (price={price}, prev_close={prev})")
            continue

        change_pct = (price - prev) / prev * 100

        # Format sign manually to avoid -0.00 display
        sign = "+" if change_pct >= 0 else ""
        arrow = "↑" if change_pct > 0 else "↓" if change_pct < 0 else "→"

        if not quiet:
            print(f"[{_now()}] {arrow} {name}({code}) 当前: {price:.2f} | "
                  f"昨收: {prev:.2f} | 涨跌: {sign}{change_pct:.2f}%")

        # Check for alert condition: drop exceeds threshold
        if change_pct <= -threshold:
            alert = {
                "code": code,
                "name": name,
                "price": price,
                "prev_close": prev,
                "change_pct": round(change_pct, 2),
                "threshold": threshold,
                "time": datetime.now().isoformat(),
            }
            alerts.append(alert)
            print(f"[{_now()}] 报警: {name}({code}) 大幅下跌 {abs(change_pct):.2f}% "
                  f"(阈值 {threshold}%), 当前价 {price:.2f}, 昨收 {prev:.2f}")

        # Update cache
        cache[code] = {**d, "cached_at": datetime.now().isoformat()}

    save_cache(cache)
    return alerts


def watch_loop(threshold, interval):
    """Continuously monitor at given interval (seconds)."""
    print(f"[{_now()}] 开始监控 {len(DEFAULT_STOCKS)} 只股票, "
          f"下跌 {threshold}% 报警, 检查间隔 {interval}s")
    print(f"[{_now()}] 按 Ctrl+C 停止监控\n")

    try:
        while True:
            check_prices(threshold)
            time.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n[{_now()}] 监控已停止")


def main():
    parser = argparse.ArgumentParser(description="股票下跌监控")
    parser.add_argument("--check", action="store_true", help="单次检查当前价格")
    parser.add_argument("--watch", action="store_true", help="持续监控模式")
    parser.add_argument("--interval", type=int, default=300,
                        help="监控间隔秒数 (默认 300)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"下跌报警阈值百分比 (默认 {DEFAULT_THRESHOLD})")
    parser.add_argument("--quiet", action="store_true", help="静默模式, 仅输出报警")
    args = parser.parse_args()

    if args.watch:
        watch_loop(args.threshold, args.interval)
    else:
        alerts = check_prices(args.threshold, quiet=args.quiet)
        if not args.quiet and not alerts:
            print(f"[{_now()}] 无报警触发")


if __name__ == "__main__":
    main()
