"""
Real-time stock price fetcher via Sina Finance API.
Refactored from stock_monitor.py for standalone reuse with 1s polling support.
"""

import json
import re
import sys
import threading
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


# ── HKD/CNY exchange rate (港股通结算汇率 卖出价) ─────────────────
# Source: 东方财富 (East Money) 港股通 结算汇率 卖出价
# Differentiates 沪市 (Shanghai Stock Connect) and 深市 (Shenzhen Stock Connect).
#
# Architecture:
#   - Query ONCE at startup → store in memory → use forever
#   - Rate from Sina fx_shkdcny (reliable, no rate limiting) → settlement
#     sell rate = rate * 0.995
#   - 沪港通(sh) and 深港通(sz) share the same rate; tracked separately for
#     future divergence (they use different clearing agents: ChinaClear SH vs SZ)
#
#   East Money push2/push2his APIs were tried but are unreachable in most
#   environments (IP rate limiting). Sina's forex API is the primary source.
#   The Sina rate tracks PBOC central parity within ~0.5% normally.

# BOC forex page URL for PBOC central parity (中行折算价)
_BOC_FX_URL = "https://www.boc.cn/sourcedb/whpj/index.html"
_fx_lock = threading.Lock()

# Settlement sell rates -- set once at startup, never re-fetched
_fx_rate_sh = 0.86   # 沪港通 (Shanghai-HK Stock Connect)
_fx_rate_sz = 0.86   # 深港通 (Shenzhen-HK Stock Connect)
_fx_initialized = False

# Central parity -> settlement sell spread (港股通 结算汇兑比率 ~= 参考汇率 * 0.995)
_FX_SETTLEMENT_SELL_SPREAD = 0.005


def _fetch_hkd_cny_rate(timeout=5.0) -> float | None:
    """Fetch PBOC central parity (央行中间价) for HKD/CNY from BOC forex page.

    The PBOC publishes the HKD/CNY central parity daily at ~9:10 AM.
    BOC (中国银行) mirrors this as 中行折算价 on their forex page.
    This is the official rate used for 港股通 settlement calculation.

    Returns the central parity as a float (e.g. 0.8703), or None on failure."""
    try:
        req = urllib.request.Request(
            "https://www.boc.cn/sourcedb/whpj/index.html",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        # Find the HKD row and extract 中行折算价 (5th data column)
        m = re.search(r'港币.*?</tr>', html, re.DOTALL)
        if m:
            tds = re.findall(r'<td[^>]*>(.*?)</td>', m.group(0))
            if len(tds) >= 6 and tds[5]:
                # BOC quotes in 人民币/100外币, so 87.03 -> 0.8703
                return float(tds[5]) / 100.0
    except Exception:
        pass
    return None


def _to_settlement_sell(rate: float) -> float:
    """Convert HKD/CNY rate to 港股通 settlement sell rate.

    卖出结算汇兑比率 = 参考汇率 * (1 - 0.5%)"""
    return rate * (1.0 - _FX_SETTLEMENT_SELL_SPREAD)


def _fetch_and_set_fx_rates():
    """Fetch settle rate once and store in memory. Called only on first access."""
    global _fx_rate_sh, _fx_rate_sz, _fx_initialized

    with _fx_lock:
        if _fx_initialized:
            return

    rate = _fetch_hkd_cny_rate()
    if rate is not None and rate > 0:
        sell_rate = _to_settlement_sell(rate)
        with _fx_lock:
            _fx_rate_sh = sell_rate
            _fx_rate_sz = sell_rate
            _fx_initialized = True
        print(f"[fx] 港股通结算汇率(卖出): {sell_rate:.4f} (参考汇率{rate:.4f})")
    else:
        fallback = 0.86 * (1.0 - _FX_SETTLEMENT_SELL_SPREAD)
        print(f"[fx] 汇率获取失败，使用默认值 {fallback:.4f}", file=sys.stderr)


def get_current_fx_rate(market: str = "sz") -> float:
    """Return the 港股通 settlement sell rate (卖出结算汇兑比率).

    Fetched once at startup, then cached in memory forever.

    Args:
        market: 'sh' for 沪港通, 'sz' for 深港通 (default: 'sz')"""
    if not _fx_initialized:
        _fetch_and_set_fx_rates()
    with _fx_lock:
        return _fx_rate_sh if market == "sh" else _fx_rate_sz


# -- Backward-compatible aliases for monitor.py --

def update_fx_rate():
    """No-op: FX rate is fetched once at startup, never refreshed."""
    pass


def freeze_fx_rate():
    """No-op: FX rate is fetched once at startup, never refreshed."""
    pass


def init_fx_rate():
    """Trigger the one-time FX rate fetch at startup."""
    _fetch_and_set_fx_rates()

# ── Backward-compatible aliases for monitor.py ──────────────────────

def update_fx_rate():
    """No-op: FX rate is fetched once at startup, never refreshed."""
    pass


def freeze_fx_rate():
    """No-op: FX rate is fetched once at startup, never refreshed."""
    pass


def init_fx_rate():
    """Trigger the one-time FX rate fetch at startup."""
    _fetch_and_set_fx_rates()
