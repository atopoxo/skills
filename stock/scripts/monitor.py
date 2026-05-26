"""
Stock price monitor — real-time rolling window, threshold detection, alert dispatch.
Trading-hours aware: only monitors and alerts during each stock's market hours.
"""

import sys
import time
from collections import deque
from datetime import datetime, time as _time

from alert import AlertEvent
from price_fetcher import fetch_prices_batch, update_fx_rate, freeze_fx_rate, init_fx_rate

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Trading hours ──────────────────────────────────────────────────

def _is_a_share_session(now):
    """True during A-share trading: Mon-Fri, 9:30-11:30 or 13:00-15:00."""
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (_time(9, 30) <= t <= _time(11, 30)) or (_time(13, 0) <= t <= _time(15, 0))


def _is_hk_session(now):
    """True during HK trading: Mon-Fri, 9:30-12:00 or 13:00-16:00."""
    if now.weekday() >= 5:
        return False
    t = now.time()
    return (_time(9, 30) <= t <= _time(12, 0)) or (_time(13, 0) <= t <= _time(16, 0))


def is_trading_time(sina_code, now=None):
    """Check whether `sina_code` is currently in its market's trading hours."""
    if now is None:
        now = datetime.now()
    if sina_code.startswith("rt_hk"):
        return _is_hk_session(now)
    return _is_a_share_session(now)


class PriceWindow:
    """Per-stock rolling window tracking (timestamp, price) pairs."""

    def __init__(self, window_seconds, poll_interval):
        self.window_seconds = window_seconds
        self.maxlen = int(window_seconds / poll_interval) + 2
        self._deque = deque(maxlen=self.maxlen)

    def push(self, price):
        self._deque.append((datetime.now(), price))

    def get_oldest(self):
        """Return (timestamp, price) of the oldest entry close to window_seconds old, or None."""
        if len(self._deque) < 2:
            return None
        oldest = self._deque[0]
        age = (datetime.now() - oldest[0]).total_seconds()
        if age >= self.window_seconds * 0.8:
            return oldest
        return None

    def ready(self):
        return self.get_oldest() is not None


class StockMonitor:
    """Core monitoring engine: 1s poll loop, rolling windows, alert dispatch."""

    def __init__(self, config, alert_dispatcher):
        self.poll_interval = config["alert"]["poll_interval_seconds"]
        self.window_seconds = config["alert"]["window_seconds"]
        self.threshold_pct = config["alert"]["threshold_pct"]
        self.cooldown_seconds = config["alert"]["cooldown_seconds"]
        self.sina_url = config["sina_api"]["base_url"]
        self.sina_timeout = config["sina_api"].get("request_timeout_seconds", 2)

        self.alert = alert_dispatcher
        self.stocks = []  # list of (code, display_name)
        self._windows = {}  # code → PriceWindow
        self._last_alert = {}  # code → timestamp
        self._running = False
        self._on_tick = None
        self._was_trading = {}  # code → bool, for detecting trading-resume transitions
        self._was_hk_trading = False  # for FX rate lifecycle

    def set_stocks(self, stocks):
        """Set monitored stocks: list of (code, display_name)."""
        self.stocks = list(stocks)
        for code, _ in self.stocks:
            if code not in self._windows:
                self._windows[code] = PriceWindow(self.window_seconds, self.poll_interval)
        # Remove windows for stocks no longer held
        active_codes = {s[0] for s in self.stocks}
        for code in list(self._windows):
            if code not in active_codes:
                del self._windows[code]
                self._last_alert.pop(code, None)

    def set_on_tick(self, callback):
        """Register a callback called after each price fetch: callback(price_map)."""
        self._on_tick = callback

    def run(self):
        print(f"[monitor] 开始监控 {len(self.stocks)} 只股票, "
              f"阈值 ±{self.threshold_pct}%, 窗口 {self.window_seconds}s, "
              f"轮询 {self.poll_interval}s, 冷却 {self.cooldown_seconds}s")
        print(f"[monitor] 按 Ctrl+C 停止\n")

        init_fx_rate()

        self._running = True
        while self._running:
            cycle_start = time.monotonic()
            try:
                self._tick()
            except Exception as e:
                print(f"[monitor] tick 异常: {e}", file=sys.stderr)

            elapsed = time.monotonic() - cycle_start
            sleep_time = max(0, self.poll_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self):
        self._running = False

    # ── internals ──────────────────────────────────────────────────

    def _tick(self):
        if not self.stocks:
            return

        codes = [s[0] for s in self.stocks]
        prices = fetch_prices_batch(codes, self.sina_url, timeout=self.sina_timeout)

        if self._on_tick:
            try:
                self._on_tick(prices)
            except Exception:
                pass

        now = datetime.now()

        # ── FX rate lifecycle ─────────────────────────────────────
        hk_trading = _is_hk_session(now)
        if hk_trading:
            update_fx_rate()
        elif self._was_hk_trading:
            # HK just closed — freeze current live rate as closing rate
            freeze_fx_rate()
        self._was_hk_trading = hk_trading

        for code, display_name in self.stocks:
            if code not in prices:
                continue

            sp = prices[code]

            trading = is_trading_time(code, now)

            if not trading:
                self._was_trading[code] = False
                continue

            # Clear window on first tick after market opens (avoid stale pre-market data)
            window = self._windows[code]
            if not self._was_trading.get(code, False):
                window._deque.clear()

            window.push(sp.price)
            self._was_trading[code] = True

            # 30s window alert check
            oldest = window.get_oldest()
            if oldest:
                old_ts, old_price = oldest
                change_30s = (sp.price - old_price) / old_price * 100
                if abs(change_30s) >= self.threshold_pct:
                    if self._check_cooldown(code):
                        event = AlertEvent(
                            code=code, name=display_name,
                            old_price=old_price, new_price=sp.price,
                            change_pct=round(change_30s, 2),
                            old_ts=old_ts, new_ts=sp.timestamp,
                        )
                        self.alert.send(event)

    def _check_cooldown(self, code):
        now = time.time()
        last = self._last_alert.get(code, 0)
        if now - last >= self.cooldown_seconds:
            self._last_alert[code] = now
            return True
        return False
