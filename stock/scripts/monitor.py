"""
Stock price monitor — real-time rolling window, threshold detection, alert dispatch.
"""

import sys
import time
from collections import deque
from datetime import datetime

from alert import AlertEvent
from price_fetcher import fetch_prices_batch

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


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
        self.summary_interval = config.get("console_alert", {}).get("summary_interval_seconds", 60)
        self.sina_url = config["sina_api"]["base_url"]
        self.sina_timeout = config["sina_api"].get("request_timeout_seconds", 2)

        self.alert = alert_dispatcher
        self.stocks = []  # list of (code, display_name)
        self._windows = {}  # code → PriceWindow
        self._last_alert = {}  # code → timestamp
        self._running = False
        self._last_summary_time = None

        # category support
        self._code_to_cat = {}
        self._cat_order = []

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

    def set_categories(self, code_to_cat, cat_order):
        """Set stock category mapping for categorized summaries."""
        self._code_to_cat = code_to_cat
        self._cat_order = cat_order

    def run(self):
        print(f"[monitor] 开始监控 {len(self.stocks)} 只股票, "
              f"阈值 ±{self.threshold_pct}%, 窗口 {self.window_seconds}s, "
              f"轮询 {self.poll_interval}s, 冷却 {self.cooldown_seconds}s")
        print(f"[monitor] 按 Ctrl+C 停止\n")

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

        # Build daily change data for categorized summary
        stocks_data = []

        for code, display_name in self.stocks:
            if code not in prices:
                continue

            sp = prices[code]
            window = self._windows[code]
            window.push(sp.price)

            # Daily change
            daily_change = (sp.price - sp.prev_close) / sp.prev_close * 100 if sp.prev_close > 0 else 0
            stocks_data.append((code, display_name, sp.price, daily_change))

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

        # Periodic categorized summary
        now = datetime.now()
        if self._last_summary_time is None or \
                (now - self._last_summary_time).total_seconds() >= self.summary_interval:
            self._last_summary_time = now
            self.alert.send_categorized_summary(stocks_data, self._code_to_cat, self._cat_order)

    def _check_cooldown(self, code):
        now = time.time()
        last = self._last_alert.get(code, 0)
        if now - last >= self.cooldown_seconds:
            self._last_alert[code] = now
            return True
        return False
