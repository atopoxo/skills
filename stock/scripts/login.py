"""
Fast East Money login — cookie cache → playwright + ddddocr fallback.
Goal: < 2s on cache hit, < 15s on cache miss (browser automation).

Usage:
    from login import login, get_cached_cookies
    cookies = login(config)  # returns cookie string or raises
"""

import json, os, re, sys, time, urllib.request

# ── Fast path: try cached cookies directly on holdings API ──────────
def try_cached_cookies(cookie_str, timeout=5):
    """Test if cookies work by hitting the validatekey + position API directly.
    Returns holdings dict or None. This is the fast path (~1s)."""
    if not cookie_str or not cookie_str.strip():
        return None
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
    headers = {"User-Agent": ua, "Cookie": cookie_str.strip()}

    # Get validatekey from trade page
    try:
        body = _http_get("https://jywg.18.cn/Trade/Buy", headers, timeout)
        m = re.search(r'id="em_validatekey"[^>]+value="([^"]+)', body)
        if not m:
            return None
        vk = m.group(1)
    except Exception:
        return None

    # Call holdings API
    try:
        url = f"https://jywg.18.cn/Com/queryAssetAndPositionV1?validatekey={vk}"
        req = urllib.request.Request(url, data=b"{}", headers={
            **headers,
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://jywg.18.cn/Trade/Buy",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        if data.get("Status") == 0:
            _dump_raw_response(data)
            return _parse_holdings(data)
    except Exception:
        pass
    return None


def _parse_holdings(data):
    """Parse holdings API response. Iterates all Data entries (sub-accounts).
    Returns {total_value, total_daily_pnl, positions[list]}."""
    data_list = data.get("Data", [])
    if not data_list:
        print("[login] API返回空Data", file=sys.stderr)
        return {"total_value": 0, "total_daily_pnl": 0, "positions": []}

    print(f"[login] API返回 {len(data_list)} 个子账户")

    all_positions = []
    total_value = 0.0

    for i, account in enumerate(data_list):
        acct_type = account.get("Market", account.get("Jylx", f"账户{i}"))
        zzc = _safe_float(account.get("Zzc"))
        raw_positions = account.get("positions", [])
        print(f"[login]   账户{i}: 类型={acct_type}, 总资产={zzc:,.2f}, 持仓条目={len(raw_positions)}")

        total_value += zzc

        for p in raw_positions:
            code = str(p.get("Zqdm", ""))
            if not code or _safe_int(p.get("Zqsl", 0)) <= 0:
                continue
            name = str(p.get("Zqmc", p.get("zqzwqc", "")))
            shares_val = _safe_int(p.get("Zqsl"))
            price_val = _safe_float(p.get("Zxjg"))
            daily_pnl_val = _safe_float(p.get("Dryk"))
            all_positions.append({
                "code": code,
                "name": name,
                "shares": shares_val,
                "available": _safe_int(p.get("Kysl")),
                "cost": _safe_float(p.get("Cbjg")),
                "price": price_val,
                "prev_close": price_val - daily_pnl_val / shares_val if shares_val > 0 else price_val,
                "market_value": _safe_float(p.get("Zxsz")),
                "daily_pnl": daily_pnl_val,
                "total_pnl": _safe_float(p.get("Ljyk")),
                "pnl_pct": _safe_float(p.get("Ykbl")) * 100,
                "account_type": str(acct_type),
            })

    total_daily_pnl = sum(p["daily_pnl"] for p in all_positions)

    # Use the first account's Zzc if it looks like the master total;
    # otherwise sum across all accounts.
    if len(data_list) >= 2 and total_value > _safe_float(data_list[0].get("Zzc")) + 1:
        # Multiple accounts with separate totals — sum is correct
        pass
    else:
        # First account's Zzc is the master total
        total_value = _safe_float(data_list[0].get("Zzc"))

    print(f"[login] 合计: 总资产={total_value:,.2f}, 持仓={len(all_positions)}只")

    return {
        "total_value": total_value,
        "total_daily_pnl": total_daily_pnl,
        "positions": all_positions,
    }


def _dump_raw_response(data):
    """Save raw API response to a debug file."""
    try:
        import os as _os
        path = _os.path.join(_os.path.dirname(__file__), "api_debug.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        print(f"[login] API原始数据已保存到 {path}")
    except Exception:
        pass


def _safe_float(val, default=0.0):
    try: return float(val) if val not in (None, "") else default
    except (ValueError, TypeError): return default


def _safe_int(val, default=0):
    try: return int(val) if val not in (None, "") else default
    except (ValueError, TypeError): return default


def _http_get(url, headers, timeout):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ── Chrome profile copy — preserves user's existing permissions ─────
def _copy_chrome_profile(src, dst):
    """Copy essential Chrome profile files so existing permission grants stick.
    Only copies small config files, not caches/history."""
    if os.path.exists(dst):
        return  # already copied
    import shutil
    os.makedirs(dst, exist_ok=True)
    # Copy Default profile (Preferences, Cookies, etc.)
    default_src = os.path.join(src, "Default")
    default_dst = os.path.join(dst, "Default")
    if os.path.isdir(default_src):
        os.makedirs(default_dst, exist_ok=True)
        for name in os.listdir(default_src):
            sp = os.path.join(default_src, name)
            dp = os.path.join(default_dst, name)
            if os.path.isfile(sp):
                size = os.path.getsize(sp)
                # Skip large files (caches, history > 10MB)
                if size > 10 * 1024 * 1024:
                    continue
                try:
                    shutil.copy2(sp, dp)
                except OSError:
                    pass
    # Copy Local State (global prefs)
    for f in ("Local State", "First Run", "Last Version"):
        fp = os.path.join(src, f)
        if os.path.isfile(fp):
            try:
                shutil.copy2(fp, os.path.join(dst, f))
            except OSError:
                pass
    print(f"[login] Chrome配置已复制 ({src} -> {dst})")


# ── Browser automation fallback ─────────────────────────────────────
def _browser_login(account, password):
    """Open system Chrome, auto-fill credentials, OCR captcha (3 attempts).
    Falls back to manual captcha entry if OCR fails."""
    import ddddocr
    from PIL import Image, ImageEnhance, ImageFilter
    from playwright.sync_api import sync_playwright
    import io

    ocr = ddddocr.DdddOcr(show_ad=False)
    pw = sync_playwright().start()
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    user_data_dir = os.path.join(os.path.dirname(__file__), ".chrome_profile")
    _copy_chrome_profile(
        src=os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
        dst=user_data_dir,
    )

    for browser_attempt in range(2):
        try:
            ctx = pw.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                executable_path=chrome_path,
                headless=False,
                ignore_https_errors=True,
            )
            page = ctx.new_page()
            page.goto("https://jywg.18.cn/", wait_until="networkidle", timeout=15000)
            page.wait_for_selector('#txtPwd', state='attached', timeout=10000)

            # Unlock password & fill account
            page.fill('#txtZjzh', account, force=True)
            page.evaluate(f"""
                const pwd = document.querySelector('#txtPwd');
                if (pwd) {{
                    pwd.type = 'password';
                    pwd.removeAttribute('readonly');
                    pwd.removeAttribute('disabled');
                    pwd.value = {json.dumps(password)};
                    pwd.dispatchEvent(new Event('input', {{bubbles: true}}));
                    pwd.dispatchEvent(new Event('change', {{bubbles: true}}));
                }}
            """)

            # ── OCR captcha loop (3 attempts) ──
            for ocr_attempt in range(3):
                img = page.locator('img[src*="YZM"]')
                img.scroll_into_view_if_needed()
                raw_bytes = img.screenshot()

                # Preprocess: grayscale → upscale → median → contrast → binary
                pil_img = Image.open(io.BytesIO(raw_bytes)).convert('L')
                pil_img = pil_img.resize((pil_img.width * 3, pil_img.height * 3), Image.LANCZOS)
                pil_img = pil_img.filter(ImageFilter.MedianFilter(3))
                pil_img = ImageEnhance.Contrast(pil_img).enhance(2.5)
                pil_img = pil_img.point(lambda x: 0 if x < 90 else 255)
                buf = io.BytesIO()
                pil_img.save(buf, format='PNG')
                captcha_text = ocr.classification(buf.getvalue())

                _FIX = str.maketrans({'o':'0','O':'0','l':'1','I':'1','i':'1',
                    'z':'2','Z':'2','s':'5','S':'5','g':'9','q':'9','b':'6','B':'8'})
                captcha_text = ''.join(c for c in captcha_text.translate(_FIX) if c.isdigit())
                print(f"[login] OCR识别 (尝试{ocr_attempt+1}): {captcha_text}")

                if len(captcha_text) < 4:
                    if ocr_attempt < 2:
                        img.click()
                        time.sleep(0.5)
                    continue

                page.fill('#txtValidCode', captcha_text, force=True)
                page.locator('button:has-text("登　录")').click()
                time.sleep(1)
                try:
                    page.wait_for_url("**/Trade/**", timeout=4000)
                except Exception:
                    pass

                if "/Trade/" in page.url or "/Search/" in page.url:
                    all_cookies = ctx.cookies()
                    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in all_cookies)
                    print(f"[login] OCR登录成功 (尝试 {ocr_attempt + 1} 次)")
                    ctx.close()
                    pw.stop()
                    return cookie_str

                # OCR failed — check page error, refresh captcha, retry
                try:
                    err_el = page.locator('.error, .prompt, [class*="error"], [class*="warn"]').first
                    if err_el.is_visible(timeout=500):
                        print(f"[login] 页面提示: {err_el.inner_text()}")
                except Exception:
                    pass

                if ocr_attempt < 2:
                    img.click()
                    time.sleep(0.5)

            # ── Manual fallback ──
            print("[login] OCR 3次均失败，请手动输入验证码并点击登录...")
            print("[login] 等待登录完成 (最多180秒)...")
            page.locator('#txtValidCode').focus()

            try:
                page.wait_for_url("**/Trade/**", timeout=180000)
            except Exception:
                if "/Trade/" not in page.url and "/Search/" not in page.url:
                    ctx.close()
                    raise RuntimeError("登录超时 (180秒未完成)")

            all_cookies = ctx.cookies()
            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in all_cookies)
            print(f"[login] 浏览器登录成功 ({len(all_cookies)} 个Cookie)")
            ctx.close()
            pw.stop()
            return cookie_str

        except RuntimeError:
            pw.stop()
            raise
        except Exception as e:
            if browser_attempt == 0:
                print(f"[login] 浏览器异常 ({e}), 重试...")
                try:
                    ctx.close()
                except Exception:
                    pass
                time.sleep(2)
                continue
            pw.stop()
            raise RuntimeError(f"浏览器登录失败: {e}")

# ── Public API ──────────────────────────────────────────────────────
def login(config):
    """Fast login to East Money. Returns cookie_string.
    Tries cached cookies first (<2s), falls back to browser (~15s)."""
    em = config.get("eastmoney", {})
    account = em.get("account", "")
    password = em.get("password", "")
    login_mode = em.get("login_mode", "manual")
    cache = em.get("cookies", "").strip()

    # Fast path: try cached cookies
    if login_mode == "manual" and cache:
        result = try_cached_cookies(cache)
        if result is not None:
            print(f"[login] Cookie缓存有效 → 直接使用 ({len(result['positions'])} 只持仓)")
            return cache, result

    # Slow path: browser login
    if not account or not password:
        raise RuntimeError("Cookie已过期且未配置账号密码，无法自动登录")

    print(f"[login] Cookie已过期，启动浏览器自动登录 (账号: {account[:3]}***)")
    new_cookies = _browser_login(account, password)

    # Verify new cookies work
    result = try_cached_cookies(new_cookies)
    if result is None:
        raise RuntimeError("浏览器登录获取的Cookie无效")

    # Save to config
    _save_cookies_to_config(config, new_cookies)

    print(f"[login] 登录成功 → {len(result['positions'])} 只持仓, 总资产 {result['total_value']:,.2f}")
    return new_cookies, result


def _save_cookies_to_config(config, cookie_str):
    """Update cookies in config dict. The caller writes it to file."""
    em = config.setdefault("eastmoney", {})
    em["cookies"] = cookie_str
    # Also write back to config file
    import json
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print("[login] Cookie已保存到 config.json")
    except Exception as e:
        print(f"[login] Cookie保存失败: {e}")
