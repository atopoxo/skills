"""
Configuration loader and validator for stock monitor.
"""

import configparser
import json
import os
import sys

# Fix Windows console encoding for Chinese output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_CONFIG = {
    "eastmoney": {
        "login_mode": "manual",
        "account": "",
        "password": "",
        "cookies": "",
        "auto_login": False,
        "login_timeout_seconds": 30,
        "session_cache_file": "eastmoney_session.pkl",
        "holdings_refresh_seconds": 300,
    },
    "alert": {
        "threshold_pct": 0.5,
        "window_seconds": 30,
        "poll_interval_seconds": 1,
        "cooldown_seconds": 300,
    },
    "feishu": {
        "enabled": False,
        "mode": "app",
        "msg_title": "股票异动报警",
        # ── webhook 模式 ──
        "webhook_url": "",
        # ── app 模式（应用机器人） ──
        "app_id": "",
        "app_secret": "",
        "receive_id": "",
        "receive_id_type": "open_id",
        # ── 账户页面外网访问（可选，用于手机等跨网络访问） ──
        # 留空则自动使用局域网IP。设置示例:
        #   ngrok:     "https://xxx.ngrok-free.app"
        #   frp:       "http://frp.example.com:18080"
        #   端口转发:   "http://公网IP:18080"
        "account_page_url": "",
    },
    "console_alert": {
        "enabled": True,
        "show_all_ticks": False,
    },
    "sina_api": {
        "base_url": "http://hq.sinajs.cn/list={codes}",
        "request_timeout_seconds": 2,
    },
}


def create_default_config(path=None, interactive=True):
    """Write a config.json file. If interactive, prompts user for credentials."""
    if path is None:
        path = _CONFIG_PATH

    cfg = _deep_copy_config(DEFAULT_CONFIG)

    if interactive:
        cfg = _interactive_setup(cfg)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"[config] 配置已保存到: {path}")


def _deep_copy_config(template):
    """Deep copy nested config dict."""
    import copy
    return copy.deepcopy(template)


def _interactive_setup(cfg):
    """Prompt user for credentials and preferences."""
    print()
    print("=" * 50)
    print("  东方财富 + 飞书 配置向导")
    print("=" * 50)
    print("(直接回车跳过不填)\n")

    # ── East Money ──
    print("── 东方财富账户 ──")
    print("  推荐: 手动模式 — 浏览器登录后复制 Cookie")
    print("  备选: 自动模式 — 账号密码登录 (可能因验证码失效)")
    mode = input("  登录模式 [manual]: ").strip().lower()
    if mode == "auto":
        cfg["eastmoney"]["login_mode"] = "auto"
        account = input("  交易账号: ").strip()
        if account:
            cfg["eastmoney"]["account"] = account
            cfg["eastmoney"]["auto_login"] = True
            password = input("  交易密码: ").strip()
            cfg["eastmoney"]["password"] = password
            print("  ✓ 已设置自动登录\n")
        else:
            print("  - 已跳过\n")
    else:
        cfg["eastmoney"]["login_mode"] = "manual"
        cfg["eastmoney"]["auto_login"] = True
        print("  请按以下步骤操作:")
        print("    1. 浏览器打开 https://jywg.18.cn 并登录")
        print("    2. 按 F12 → Application → Cookies → jywg.18.cn")
        print("    3. 复制所有 Cookie，格式: name1=value1; name2=value2")
        cookies = input("  粘贴 Cookie (留空跳过): ").strip()
        if cookies:
            cfg["eastmoney"]["cookies"] = cookies
            print("  ✓ 已设置 Cookie 登录\n")
        else:
            print("  - 已跳过，后续可手动编辑 config.json\n")

    # ── Feishu ──
    print("── 飞书机器人 ──")
    print("  1. Webhook (自定义机器人，群里添加后复制 URL)")
    print("  2. App (应用机器人，需 App ID + App Secret)")
    mode = input("  选择模式 [2]: ").strip()
    if mode == "1":
        cfg["feishu"]["mode"] = "webhook"
        webhook = input("  Webhook URL: ").strip()
        if webhook:
            cfg["feishu"]["enabled"] = True
            cfg["feishu"]["webhook_url"] = webhook
            title = input(f"  报警标题 [{cfg['feishu']['msg_title']}]: ").strip()
            if title:
                cfg["feishu"]["msg_title"] = title
            print("  ✓ 已启用飞书 Webhook 报警\n")
        else:
            print("  - 已禁用飞书报警\n")
    else:
        cfg["feishu"]["mode"] = "app"
        app_id = input("  App ID: ").strip()
        if app_id:
            cfg["feishu"]["enabled"] = True
            cfg["feishu"]["app_id"] = app_id
            app_secret = input("  App Secret: ").strip()
            cfg["feishu"]["app_secret"] = app_secret
            chat_id = input("  接收对象 ID (留空=机器人所在群): ").strip()
            if chat_id:
                cfg["feishu"]["receive_id"] = chat_id
            id_type = input(f"  接收对象类型 [{cfg['feishu']['receive_id_type']}]: ").strip()
            if id_type:
                cfg["feishu"]["receive_id_type"] = id_type
            title = input(f"  报警标题 [{cfg['feishu']['msg_title']}]: ").strip()
            if title:
                cfg["feishu"]["msg_title"] = title
            print("  ✓ 已启用飞书应用机器人报警\n")
        else:
            print("  - 已禁用飞书报警\n")

    # ── Alert threshold ──
    print("── 报警参数 ──")
    threshold = input(f"  涨跌幅阈值 [{cfg['alert']['threshold_pct']}%]: ").strip()
    if threshold:
        try:
            cfg["alert"]["threshold_pct"] = float(threshold)
        except ValueError:
            print(f"  输入无效，使用默认值 {cfg['alert']['threshold_pct']}%")

    cooldown = input(f"  同股票报警冷却秒数 [{cfg['alert']['cooldown_seconds']}]: ").strip()
    if cooldown:
        try:
            cfg["alert"]["cooldown_seconds"] = int(cooldown)
        except ValueError:
            print(f"  输入无效，使用默认值 {cfg['alert']['cooldown_seconds']}s")

    print("  ✓ 配置完成")
    print()
    return cfg


def validate_config(cfg):
    """Validate config dict. Returns list of error strings."""
    errors = []

    if "eastmoney" in cfg:
        em = cfg["eastmoney"]
        mode = em.get("login_mode", "manual")
        if em.get("auto_login"):
            if mode == "auto":
                if not em.get("account"):
                    errors.append("eastmoney.account: 自动登录模式必须填写账号")
                if not em.get("password"):
                    errors.append("eastmoney.password: 自动登录模式必须填写密码")
            elif mode == "manual":
                if not em.get("cookies"):
                    errors.append("eastmoney.cookies: 手动模式必须提供 Cookie")

    if "alert" in cfg:
        alert = cfg["alert"]
        if alert.get("threshold_pct", 0) <= 0:
            errors.append("alert.threshold_pct: 必须大于 0")
        if alert.get("poll_interval_seconds", 1) < 1:
            errors.append("alert.poll_interval_seconds: 必须 >= 1")
        if alert.get("window_seconds", 30) < alert.get("poll_interval_seconds", 1):
            errors.append("alert.window_seconds: 必须 >= poll_interval_seconds")

    if "feishu" in cfg:
        fs = cfg["feishu"]
        if fs.get("enabled"):
            mode = fs.get("mode", "webhook")
            if mode == "app":
                if not fs.get("app_id"):
                    errors.append("feishu.app_id: 应用机器人模式必须填写 App ID")
                if not fs.get("app_secret"):
                    errors.append("feishu.app_secret: 应用机器人模式必须填写 App Secret")
                if not fs.get("receive_id"):
                    errors.append("feishu.receive_id: 应用机器人模式必须填写接收对象 ID")
                if not fs.get("receive_id_type"):
                    errors.append("feishu.receive_id_type: 应用机器人模式必须填写接收对象类型")
            else:
                url = fs.get("webhook_url", "")
                if not url or not url.startswith("https://"):
                    errors.append("feishu.webhook_url: Webhook 模式必须填写有效的 HTTPS URL")

    return errors


def load_config(path=None):
    """Load and validate config. Exits on fatal errors, warns on non-fatal."""
    if path is None:
        path = _CONFIG_PATH

    if not os.path.exists(path):
        print(f"[config] 配置文件不存在: {path}")
        create_default_config(path)
        print("[config] 请编辑配置文件后重新运行。")
        raise SystemExit(0)

    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    errors = validate_config(cfg)
    if errors:
        print("[config] 配置错误:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        raise SystemExit(1)

    return cfg


# ── custom.ini categories ──────────────────────────────────────────

_CUSTOM_INI_PATH = os.path.join(os.path.dirname(__file__), "custom.ini")


def load_categories(path=None):
    """Load stock categories from custom.ini.

    Returns:
        dict[str, str]: {sina_code: category_name}
        list[str]: ordered category names (excluding "其它")
    """
    if path is None:
        path = _CUSTOM_INI_PATH

    code_to_cat = {}
    cat_order = []

    if not os.path.exists(path):
        return code_to_cat, cat_order

    ini = configparser.ConfigParser()
    ini.read(path, encoding="utf-8")

    for section in ini.sections():
        if section == "其它":
            continue
        cat_order.append(section)
        raw = ini.get(section, "stocks", fallback="")
        if not raw.strip():
            continue
        for code in raw.split(","):
            code = code.strip()
            if code:
                code_to_cat[code] = section

    return code_to_cat, cat_order
