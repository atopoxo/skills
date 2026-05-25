"""
Stock Monitor — main entry point.
Orchestrates: fast login → holdings → 1s monitoring loop → alerts.

Login flow (fast path):
  1. Try cached cookies → directly hit holdings API  (~1s)
  2. If expired → headless browser + OCR captcha   (~15s)
  3. Fallback stocks if all login methods fail
"""

import argparse, sys, os, ctypes

from config import create_default_config, load_config, load_categories
from price_fetcher import fetch_prices_batch
from alert import AlertDispatcher
from monitor import StockMonitor
from account_page import launch_account_page, start_tunnel


def _set_process_title(title):
    """Set console window title for easy identification in Task Manager."""
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="股票异动监控系统")
    parser.add_argument("--check", action="store_true", help="单次检查（使用回退列表）")
    parser.add_argument("--init-config", action="store_true", help="生成 config.json 模板")
    parser.add_argument("--test-feishu", action="store_true", help="测试飞书 Webhook 连接")
    parser.add_argument("--relogin", action="store_true", help="强制重新浏览器登录（忽略缓存Cookie）")
    parser.add_argument("--id", type=str, default="", help="实例编号，用于区分多个监控进程")
    args = parser.parse_args()

    # Set process title
    instance_id = f" #{args.id}" if args.id else ""
    _set_process_title(f"stock{instance_id}")

    if args.init_config:
        create_default_config()
        return

    cfg = load_config()
    dispatcher = AlertDispatcher(cfg)

    if args.test_feishu:
        dispatcher.send_feishu_test()
        return

    if args.check:
        run_single_check(cfg, dispatcher)
        return

    # ── Get stocks ──────────────────────────────────────────────────
    stocks = []
    holdings_data = None

    if args.relogin:
        # Force re-login: clear cached cookies
        em = cfg.setdefault("eastmoney", {})
        em["cookies"] = ""
        stocks, holdings_data = try_fast_login(cfg)
    else:
        stocks, holdings_data = try_fast_login(cfg)

    value_map = {}
    code_to_cat, cat_order = load_categories()

    if not stocks:
        stocks = load_fallback_stocks(cfg)
        print(f"[main] 使用回退列表: {len(stocks)} 只股票")
    else:
        # Build market value lookup from holdings data
        value_map = _build_value_map(holdings_data)
        print(f"[main] 监控列表: {len(stocks)} 只股票")

        server = launch_account_page(holdings_data, code_to_cat, cat_order)

        # Priority: custom config URL > cloudflared tunnel > LAN IP
        custom_url = cfg.get("feishu", {}).get("account_page_url", "").strip()
        if custom_url:
            account_url = custom_url
        else:
            tunnel_url, _ = start_tunnel(18080)
            account_url = tunnel_url or getattr(server, "_url", None)

    if not stocks:
        print("[main] 无监控标的，退出", file=sys.stderr)
        return

    # Sort by market value descending
    if value_map:
        stocks.sort(key=lambda s: value_map.get(s[0], 0), reverse=True)

    # for code, name in stocks:
    #     mv = value_map.get(code, 0) if value_map else 0
    #     print(f"  - {name} ({code})  {_fmt_value(mv)}")

    monitor = StockMonitor(cfg, dispatcher)
    monitor.set_stocks(stocks)

    monitor.set_categories(code_to_cat, cat_order)

    # Send initial holdings summary to console + Feishu
    dispatcher.send_holdings_summary(stocks, value_map, holdings_data or {}, code_to_cat, cat_order, account_url)

    try:
        monitor.run()
    except KeyboardInterrupt:
        print(f"\n[main] 监控已停止")


def try_fast_login(cfg):
    """Use fast login module. Returns (stocks, holdings_data)."""
    try:
        from login import login

        _, result = login(cfg)
        if result is None or not result.get("positions"):
            print("[main] 持仓为空", file=sys.stderr)
            return [], None

        stocks = holdings_to_stocks(result["positions"])
        return stocks, result

    except ImportError as e:
        print(f"[main] login 模块加载失败: {e}", file=sys.stderr)
        return [], None
    except RuntimeError as e:
        print(f"[main] 登录失败: {e}", file=sys.stderr)
        return [], None
    except Exception as e:
        print(f"[main] 登录异常: {e}", file=sys.stderr)
        return [], None


def holdings_to_stocks(positions):
    """Convert position dicts to (sina_code, display_name) tuples."""
    result = []
    for p in positions:
        code = str(p.get("code", ""))
        market = _resolve_market(code)
        sina = _to_sina_code(code, market)
        result.append((sina, p.get("name", code)))
    return result


def _resolve_market(code):
    code = str(code)
    if len(code) == 5 and code.startswith("0"):
        return "hk"
    if code.startswith(("60", "68", "51", "56")):
        return "sh"
    if code.startswith(("00", "30", "15")):
        return "sz"
    return "sz"


def _to_sina_code(code, market):
    code = str(code)
    if market == "hk":
        return f"rt_hk{code}"
    if market == "sh":
        return f"sh{code}"
    return f"sz{code}"


def _build_value_map(holdings_data):
    """Build {sina_code: market_value} lookup from holdings API response."""
    if not holdings_data:
        return {}
    result = {}
    for p in holdings_data.get("positions", []):
        code = str(p.get("code", ""))
        market = _resolve_market(code)
        sina = _to_sina_code(code, market)
        result[sina] = p.get("market_value", 0)
    return result


def _fmt_value(val):
    """Format market value: >= 100k shows in 万元 with 2 decimals."""
    if val >= 100000:
        return f"市值: {val / 10000:.2f}万"
    elif val > 0:
        return f"市值: {val:,.2f}"
    return ""


def load_fallback_stocks(cfg):
    """Load fallback stock list from config."""
    fallback = cfg.get("fallback_stocks", [])
    return [(s["code"], s["name"]) for s in fallback if s.get("code")]


def run_single_check(cfg, dispatcher):
    """Legacy single-check mode."""
    stocks = load_fallback_stocks(cfg)
    if not stocks:
        print("[main] fallback_stocks 为空", file=sys.stderr)
        return
    codes = [s[0] for s in stocks]
    sina_url = cfg["sina_api"]["base_url"]
    prices = fetch_prices_batch(codes, sina_url)
    for code, display_name in stocks:
        if code not in prices:
            print(f"  {display_name}({code}): 未获取到数据")
            continue
        sp = prices[code]
        change_pct = (sp.price - sp.prev_close) / sp.prev_close * 100
        sign = "+" if change_pct >= 0 else ""
        direction = "↑" if change_pct > 0 else "↓" if change_pct < 0 else "→"
        print(f"  {direction} {display_name}({code}) 当前: {sp.price:.2f} | "
              f"昨收: {sp.prev_close:.2f} | 涨跌: {sign}{change_pct:.2f}%")


if __name__ == "__main__":
    main()
