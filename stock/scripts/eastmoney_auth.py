"""
East Money session — minimal. Reads cookies from config.
Fast login is handled by login.py; this module is kept for backward compat.
"""

import json, os, pickle, sys, time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class EastMoneySession:
    """Thin wrapper over config cookies.

    Prefer login.try_cached_cookies() for new code — it's much faster."""

    def __init__(self, config):
        em = config.get("eastmoney", {})
        self._account = em.get("account", "")
        self._password = em.get("password", "")
        self._cookies_raw = em.get("cookies", "")
        self._cache_file = em.get("session_cache_file", "eastmoney_session.pkl")
        self._timeout = em.get("login_timeout_seconds", 10)
        self._cookies = {}
        self._authenticated = False

    def login(self):
        """Try loading session from cache, then config cookies."""
        if self._load_session():
            print("[东方财富] 使用持久化缓存会话")
            self._authenticated = True
            return True

        if self._parse_cookies_from_config():
            self._authenticated = True
            self._save_session()
            print("[东方财富] Cookie已加载")
            return True

        print("[东方财富] 未找到有效Cookie，请运行 python scripts/login.py 或使用 --no-em", file=sys.stderr)
        return False

    def is_authenticated(self):
        return self._authenticated

    def get_cookies(self):
        return dict(self._cookies)

    # ── private ─────────────────────────────────────────────────────

    def _parse_cookies_from_config(self):
        raw = self._cookies_raw.strip()
        if not raw:
            return False
        # Handle JSON array format
        if raw.startswith("["):
            try:
                self._cookies = {i["name"]: i["value"] for i in json.loads(raw) if i.get("name")}
                return bool(self._cookies)
            except json.JSONDecodeError:
                pass
        # Handle "k=v; k2=v2" format
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                self._cookies[k.strip()] = v.strip()
        return bool(self._cookies)

    def _save_session(self):
        cache_path = os.path.join(os.path.dirname(__file__), self._cache_file)
        try:
            with open(cache_path, "wb") as f:
                pickle.dump({"cookies": self._cookies, "timestamp": time.time()}, f)
        except Exception:
            pass

    def _load_session(self):
        cache_path = os.path.join(os.path.dirname(__file__), self._cache_file)
        try:
            with open(cache_path, "rb") as f:
                data = pickle.load(f)
            if time.time() - data.get("timestamp", 0) > 86400:
                return False
            self._cookies = data.get("cookies", {})
            return bool(self._cookies)
        except (FileNotFoundError, pickle.UnpicklingError, KeyError):
            return False
        except Exception:
            return False
