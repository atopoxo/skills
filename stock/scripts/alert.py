"""
Alert dispatcher — console + Feishu dual-channel (webhook or app bot).
Feishu App Bot: uses App ID + App Secret to get tenant_access_token, then sends via IM API.
"""

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── helpers ───────────────────────────────────────────────────────

def _sina_to_raw(sina_code):
    """Convert sina code (sh688008) back to raw code (688008)."""
    if sina_code.startswith("rt_hk"):
        return sina_code[5:]
    if sina_code.startswith(("sh", "sz")):
        return sina_code[2:]
    return sina_code

# ── Feishu API endpoints ──
_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
_SEND_URL = "https://open.feishu.cn/open-apis/im/v1/messages"


class AlertEvent:

    def __init__(self, code, name, old_price, new_price, change_pct, old_ts, new_ts):
        self.code = code
        self.name = name
        self.old_price = old_price
        self.new_price = new_price
        self.change_pct = change_pct
        self.old_timestamp = old_ts
        self.new_timestamp = new_ts


class AlertDispatcher:

    def __init__(self, config):
        self._console_enabled = config.get("console_alert", {}).get("enabled", True)

        fs = config.get("feishu", {})
        self._feishu_enabled = fs.get("enabled", False)
        self._feishu_mode = fs.get("mode", "webhook")
        self._msg_title = fs.get("msg_title", "股票异动报警")

        # webhook 模式
        self._webhook_url = fs.get("webhook_url", "")

        # app 模式
        self._app_id = fs.get("app_id", "")
        self._app_secret = fs.get("app_secret", "")
        self._receive_id = fs.get("receive_id", fs.get("chat_id", ""))
        self._receive_id_type = fs.get("receive_id_type", "open_id")
        self._token = None
        self._token_expiry = 0

    # ── public API ──────────────────────────────────────────────────

    def send(self, event):
        """Dispatch alert to all enabled channels."""
        if self._console_enabled:
            self._send_console(event)
        if self._feishu_enabled:
            self._send_feishu(event)

    def send_holdings_summary(self, stocks, value_map, holdings_data, code_to_cat=None, cat_order=None, account_url=None):
        """Send initial holdings overview to Feishu only (console suppressed)."""
        if self._feishu_enabled:
            self._send_holdings_feishu(account_url)

    def send_feishu_test(self):
        """Send a test message to verify Feishu configuration."""
        if not self._feishu_enabled:
            print("[飞书] 飞书未启用，请先在 config.json 中启用")
            return False

        card = self._build_test_card()
        if self._feishu_mode == "app":
            ok = self._send_app(card)
        else:
            ok = self._send_webhook(card)
        if ok:
            print("[飞书] 测试消息发送成功!")
        return ok

    # ── holdings summary ────────────────────────────────────────────

    @staticmethod
    def _resolve_cat(sina_code, code_to_cat):
        """Look up category for a sina_code.
        Tries full code first, then raw numeric part (custom.ini uses bare codes like '688008')."""
        if code_to_cat is None:
            return "其它"
        if sina_code in code_to_cat:
            return code_to_cat[sina_code]
        raw = _sina_to_raw(sina_code)
        if raw in code_to_cat:
            return code_to_cat[raw]
        return "其它"

    @staticmethod
    def _fmt_stock_fields(p, value_map, sina_code, total_value):
        """Extract and format a single stock's display fields.

        Returns dict with keys: raw_code, pnl_str, d_str, pc_str, sa_str, w_str.
        """
        raw_code = _sina_to_raw(sina_code)
        price = p.get("price", 0)
        cost = p.get("cost", 0)
        shares = p.get("shares", 0)
        available = p.get("available", 0)
        mv = p.get("market_value", value_map.get(sina_code, 0))
        daily = p.get("daily_pnl", 0)
        total_pnl = p.get("total_pnl", 0)
        pnl_pct = p.get("pnl_pct", 0)

        d_str = f"{daily:+,.2f}" if daily else "—"
        pnl_str = f"{total_pnl:+,.2f}({pnl_pct:+.1f}%)" if total_pnl else "—"
        pc_str = f"{price:.2f}/{cost:.2f}" if price else "—/—"
        sa_str = f"{shares}/{available}" if shares else "—/—"
        weight = (mv / total_value * 100) if total_value > 0 and mv > 0 else 0
        w_str = f"{weight:.1f}%" if mv > 0 else "—"

        return {
            "raw_code": raw_code,
            "pnl_str": pnl_str,
            "d_str": d_str,
            "pc_str": pc_str,
            "sa_str": sa_str,
            "w_str": w_str,
        }

    def _group_stocks_by_cat(self, stocks, code_to_cat, cat_order):
        """Group (sina_code, name) tuples by category.
        Returns list of (cat_name, [(code, name)]) — ALL categories from custom.ini included, even empty ones."""
        if not cat_order:
            return [("", list(stocks))]

        cats = {c: [] for c in cat_order}
        fallback = []
        for item in stocks:
            cat = self._resolve_cat(item[0], code_to_cat)
            if cat in cats:
                cats[cat].append(item)
            else:
                fallback.append(item)

        # Always show every category in custom.ini order, even empty ones.
        # "其它" / "其它" catch-all only appears if there are unclassified stocks.
        result = [(c, cats[c]) for c in cat_order]
        if fallback:
            result.append(("其它", fallback))
        return result

    def _print_holdings_console(self, stocks, value_map, positions, total_value, code_to_cat=None, cat_order=None):
        """Print formatted holdings table to console, grouped by category."""
        total_daily_pnl = sum(p.get("daily_pnl", 0) for p in positions)
        daily_str = f"{total_daily_pnl:+,.2f}" if total_daily_pnl else "—"

        pos_lookup = {str(p.get("code", "")): p for p in positions}
        grouped = self._group_stocks_by_cat(stocks, code_to_cat, cat_order)

        print()
        print("=" * 90)
        print(f"  持仓总览 — 总资产: {total_value:,.2f} — 当日盈亏: {daily_str} — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 90)
        print(f"  {'名称':>8} {'持仓盈亏':>16} {'当日盈亏':>12} {'现价/成本价':>16} {'持仓/可用':>12} {'个股仓位':>8} {'证券代码':>10}")
        print("-" * 90)

        for cat_name, cat_stocks in grouped:
            if cat_name:
                count = len(cat_stocks)
                print(f"  [{cat_name}] ({count}只)")

            if not cat_stocks:
                print(f"  {'(无持仓)':>90}")
            else:
                for sina_code, name in cat_stocks:
                    p = pos_lookup.get(_sina_to_raw(sina_code), {})
                    fld = self._fmt_stock_fields(p, value_map, sina_code, total_value)
                    print(f"  {name:>8} {fld['pnl_str']:>16} {fld['d_str']:>12} {fld['pc_str']:>16} {fld['sa_str']:>12} {fld['w_str']:>8} {fld['raw_code']:>10}")

            if cat_name:
                print()

        print("=" * 90)
        print()

    def _send_holdings_feishu(self, account_url):
        """Send a link to the account overview page on Feishu."""
        if not account_url:
            return

        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "持仓总览"},
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": f"点击查看持仓详情：[账户页面]({account_url})"},
                    },
                    {
                        "tag": "note",
                        "elements": [{
                            "tag": "plain_text",
                            "content": f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        }],
                    },
                ],
            },
        }

        if self._feishu_mode == "app":
            self._send_app(card)
        else:
            self._send_webhook(card)

    # ── console ────────────────────────────────────────────────────

    def _send_console(self, event):
        direction = "📈 上涨" if event.change_pct > 0 else "📉 下跌"
        sign = "+" if event.change_pct >= 0 else ""
        print()
        print("=" * 50)
        print(f"  ALERT  {event.new_timestamp.strftime('%Y-%m-%d %H:%M:%S')}  {direction}")
        print("-" * 50)
        print(f"  {event.name} ({event.code})")
        print(f"  30s前: {event.old_price:.2f}  →  当前: {event.new_price:.2f}")
        print(f"  变动: {sign}{event.change_pct:.2f}%")
        print("=" * 50)
        print()

    # ── feishu dispatch ────────────────────────────────────────────

    def _send_feishu(self, event):
        card = self._build_alert_card(event)
        if self._feishu_mode == "app":
            self._send_app(card)
        else:
            self._send_webhook(card)

    # ── webhook mode ────────────────────────────────────────────────

    def _send_webhook(self, card):
        data = json.dumps(card, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self._webhook_url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("code") != 0:
                    print(f"[飞书] 发送失败: {body.get('msg', '未知错误')}", file=sys.stderr)
                    return False
                return True
        except urllib.error.URLError as e:
            print(f"[飞书] HTTP 错误: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"[飞书] 发送异常: {e}", file=sys.stderr)
            return False

    # ── app bot mode ────────────────────────────────────────────────

    def _get_token(self):
        """Obtain or refresh tenant_access_token. Returns token string or None."""
        if self._token and time.time() < self._token_expiry - 60:
            return self._token

        data = json.dumps({
            "app_id": self._app_id,
            "app_secret": self._app_secret,
        }).encode("utf-8")
        req = urllib.request.Request(
            _TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("code") == 0:
                    self._token = body["tenant_access_token"]
                    self._token_expiry = time.time() + body.get("expire", 7200)
                    return self._token
                print(f"[飞书] 获取 token 失败: {body.get('msg', '未知错误')}", file=sys.stderr)
        except Exception as e:
            print(f"[飞书] 获取 token 异常: {e}", file=sys.stderr)
        return None

    def _send_app(self, card):
        token = self._get_token()
        if not token:
            return False

        payload = {
            "receive_id": self._receive_id,
            "msg_type": "interactive",
            "content": json.dumps(card["card"], ensure_ascii=False),
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        url = f"{_SEND_URL}?receive_id_type={self._receive_id_type}"
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                if body.get("code") != 0:
                    print(f"[飞书] 发送失败: {body.get('msg', '未知错误')}", file=sys.stderr)
                    return False
                return True
        except urllib.error.URLError as e:
            print(f"[飞书] HTTP 错误: {e}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"[飞书] 发送异常: {e}", file=sys.stderr)
            return False

    # ── card builders ───────────────────────────────────────────────

    def _build_alert_card(self, event):
        direction = "📈 上涨" if event.change_pct > 0 else "📉 下跌"
        color = "red" if abs(event.change_pct) >= 2 else "yellow" if abs(event.change_pct) >= 1 else "green"
        sign = "+" if event.change_pct >= 0 else ""
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"股票异动 {direction}"},
                    "template": color,
                },
                "elements": [{
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**{event.name}** ({event.code})\n"
                            f"价格: {event.old_price:.2f} → {event.new_price:.2f}\n"
                            f"变动: {sign}{event.change_pct:.2f}%\n"
                            f"时间: {event.new_timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                        ),
                    },
                }],
            },
        }

    def _build_test_card(self):
        color = "green" if self._feishu_mode == "app" else "blue"
        title = f"{self._msg_title} - 测试 ({'App Bot' if self._feishu_mode == 'app' else 'Webhook'})"
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": color,
                },
                "elements": [{
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"测试消息发送成功！\n模式: {'应用机器人' if self._feishu_mode == 'app' else 'Webhook'}\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    },
                }],
            },
        }
