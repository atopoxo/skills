"""
Fetch user's stock positions from East Money trading platform (jywg.18.cn).
API: /Com/queryAssetAndPositionV1 (validated with em_validatekey from page).
"""

import json
import re
import sys
import urllib.request
import urllib.error

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def fetch_holdings(session):
    """Fetch holdings from East Money. Returns list of {code, name, market, shares, cost} dicts."""
    if not session.is_authenticated():
        return []

    cookies = session.get_cookies()
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    headers_base = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": cookie_str,
    }

    # Step 1: Get validatekey from the trade page
    validatekey = _extract_validatekey(headers_base)
    if not validatekey:
        print("[东方财富] 无法获取 validatekey，Cookie 可能已过期", file=sys.stderr)
        return []

    # Step 2: Call position API
    url = f"https://jywg.18.cn/Com/queryAssetAndPositionV1?validatekey={validatekey}"
    req = urllib.request.Request(
        url,
        data=b"{}",
        headers={
            **headers_base,
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://jywg.18.cn/Trade/Buy",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        print(f"[东方财富] 持仓接口异常: {e}", file=sys.stderr)
        return []

    if data.get("Status") != 0:
        print(f"[东方财富] 持仓接口返回错误: {data.get('Message', '')}", file=sys.stderr)
        return []

    account_data = data.get("Data", [{}])[0]
    positions = account_data.get("positions", [])

    def _safe_float(val, default=0.0):
        try:
            return float(val) if val != "" and val is not None else default
        except (ValueError, TypeError):
            return default

    def _safe_int(val, default=0):
        try:
            return int(val) if val != "" and val is not None else default
        except (ValueError, TypeError):
            return default

    result = []
    for p in positions:
        code = str(p.get("Zqdm", ""))
        if not code or _safe_int(p.get("Zqsl", 0)) <= 0:
            continue
        entry = {
            "code": code,
            "name": str(p.get("Zqmc", p.get("zqzwqc", ""))),
            "market": _resolve_market(str(p.get("Market", "")), code),
            "shares": _safe_int(p.get("Zqsl")),
            "available": _safe_int(p.get("Kysl")),
            "cost": _safe_float(p.get("Cbjg")),
            "price": _safe_float(p.get("Zxjg")),
            "market_value": _safe_float(p.get("Zxsz")),
            "daily_pnl": _safe_float(p.get("Dryk")),
            "total_pnl": _safe_float(p.get("Ljyk")),
            "pnl_pct": _safe_float(p.get("Ykbl")) * 100,
        }
        result.append(entry)

    # Print summary
    total_value = _safe_float(account_data.get("Zzc"))
    print(f"[东方财富] 总资产: {total_value:,.2f} | 持仓 {len(result)} 只")
    for e in result:
        sign = "+" if e["daily_pnl"] >= 0 else ""
        print(f"  {e['name']}({e['code']}) {e['shares']}股 "
              f"@{e['price']:.3f} 市值{e['market_value']:,.2f} "
              f"今日{sign}{e['daily_pnl']:.2f}")

    return result


def holdings_to_monitor_list(holdings):
    """Convert holdings to list of (sina_code, display_name) tuples."""
    result = []
    for h in holdings:
        code = h.get("code", "")
        market = h.get("market", "")
        sina_code = _to_sina_code(code, market)
        name = h.get("name", code)
        result.append((sina_code, name))
    return result


def _extract_validatekey(headers):
    """Extract em_validatekey from the trading page."""
    try:
        req = urllib.request.Request(
            "https://jywg.18.cn/Trade/Buy",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        m = re.search(r'id="em_validatekey"[^>]+value="([^"]+)', body)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"[东方财富] 获取页面失败: {e}", file=sys.stderr)
    return None


def _resolve_market(market, code):
    """Resolve market code from API value and stock code."""
    code = str(code)
    # Check code patterns first (API market field can be unreliable)
    if len(code) == 5 and code.startswith("0"):
        return "hk"              # HK stocks padded to 5 digits
    if code.startswith(("60", "68", "51", "56")):
        return "sh"
    if code.startswith(("00", "30", "15")):
        return "sz"
    # Fall back to API market field
    m = market.upper()
    if m in ("HA", "SH", "1"):
        return "sh"
    if m in ("SA", "SZ", "0"):
        return "sz"
    if m in ("HK", "3"):
        return "hk"
    return "sz"


def _to_sina_code(stock_code, market):
    """Map East Money code + market to Sina format."""
    code = str(stock_code)
    if market == "hk":
        return f"rt_hk{code}"
    if market == "sh":
        return f"sh{code}"
    if market == "sz":
        return f"sz{code}"
    # Guess from prefix
    if code.startswith(("60", "68", "51", "56")):
        return f"sh{code}"
    # 5-digit codes starting with 0 are HK stocks
    if len(code) == 5 and code.startswith("0"):
        return f"rt_hk{code.lstrip('0')}"
    return f"sz{code}"
