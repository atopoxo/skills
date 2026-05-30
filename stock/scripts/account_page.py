"""
Account page — generates a mobile-app-like account overview page
mimicking the East Money (东方财富) app's personal account page UI.
Opens in the default browser after successful login.
"""

import json
import os
import re
import socket
import subprocess
import sys
import threading
import webbrowser
import time
import urllib.request
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs
from news_fetcher import get_news_json
from price_fetcher import get_current_fx_rate
import market_intel

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_FIXED_PORT = 18080

# Shared state for real-time price updates
_holdings_data = {}
_holdings_lock = threading.Lock()
_code_to_cat_cache: dict = {}  # populated by _generate_page
_cat_order_cache: list = []

# Shared state for hotspot (AI analysis) caching to avoid blocking HTTP handler
_hotspot_cache: dict = {}
_hotspot_lock = threading.Lock()


def _resolve_market(code):
    code = str(code)
    # Zero-pad short codes (East Money may strip leading zeros from HK codes)
    if len(code) < 5:
        code = code.zfill(5)
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
        return f"rt_hk{code.zfill(5)}"
    if market == "sh":
        return f"sh{code}"
    return f"sz{code}"


def _find_position(sina_code: str) -> dict | None:
    """Find position data for a given Sina-format stock code."""
    with _holdings_lock:
        if not _holdings_data:
            return None
        for p in _holdings_data.get("positions", []):
            code = str(p.get("code", ""))
            market = _resolve_market(code)
            if _to_sina_code(code, market) == sina_code:
                return {
                    "shares": p.get("shares", 0),
                    "available": p.get("available", 0),
                    "cost": p.get("cost", 0),
                    "market_value": p.get("market_value", 0),
                    "total_pnl": p.get("total_pnl", 0),
                    "pnl_pct": p.get("pnl_pct", 0),
                }
    return None


def set_holdings_data(data):
    """Store initial holdings data. East Money returns all prices in CNY
    (including HK stocks), so no conversion is needed.
    Derives _cash for total_value reconstruction."""
    global _holdings_data
    with _holdings_lock:
        import copy
        _holdings_data = copy.deepcopy(data)
        total_mv = sum(
            p.get("market_value", 0) or 0
            for p in _holdings_data.get("positions", [])
        )
        _holdings_data["_cash"] = (_holdings_data.get("total_value", 0) or 0) - total_mv


def update_price_data(price_map):
    """Merge latest price_map (sina_code → StockPrice) into per-position fields.
    HK stock prices from Sina are HKD; converted to CNY via get_current_fx_rate.
    Uses 东方财富 港股通 结算汇率 卖出价, distinguished by 沪市/深市."""
    global _holdings_data
    with _holdings_lock:
        if not _holdings_data:
            return
        for p in _holdings_data.get("positions", []):
            code = str(p.get("code", ""))
            market = _resolve_market(code)
            sina = _to_sina_code(code, market)
            sp = price_map.get(sina)
            if sp and sp.price > 0:
                shares = p.get("shares", 0)
                cost = p.get("cost", 0)
                if market == "hk":
                    # Determine 沪港通(sh) vs 深港通(sz) from account market type
                    acct_type = str(p.get("account_type", p.get("Market", "")))
                    hk_channel = "sh" if acct_type.upper() in ("HA", "SH", "1") else "sz"
                    fx = get_current_fx_rate(hk_channel)
                    price_cny = sp.price * fx
                    prev_close_cny = sp.prev_close * fx
                    p["price"] = price_cny  # CNY for display consistency with cost
                    p["prev_close"] = prev_close_cny
                    p["market_value"] = shares * price_cny
                    p["daily_pnl"] = (price_cny - prev_close_cny) * shares
                    if cost > 0:
                        # cost is already in CNY (account currency)
                        p["total_pnl"] = (price_cny - cost) * shares
                        p["pnl_pct"] = (price_cny - cost) / cost * 100
                else:
                    p["price"] = sp.price
                    p["prev_close"] = getattr(sp, "prev_close", p.get("prev_close", sp.price))
                    p["market_value"] = shares * sp.price
                    p["daily_pnl"] = (sp.price - p["prev_close"]) * shares
                    if cost > 0:
                        p["total_pnl"] = (sp.price - cost) * shares
                        p["pnl_pct"] = (sp.price - cost) / cost * 100


def _get_holdings_json():
    """Return current holdings data as JSON, computing totals from positions
    on every call so header values always match the sum of stock cards."""
    with _holdings_lock:
        total_mv = 0
        total_daily = 0
        for p in _holdings_data.get("positions", []):
            total_mv += p.get("market_value", 0) or 0
            total_daily += p.get("daily_pnl", 0) or 0
        result = dict(_holdings_data)
        result["total_daily_pnl"] = total_daily
        result["total_value"] = total_mv + result.pop("_cash", 0)
    # Serialize outside lock to avoid blocking other threads
    return json.dumps(result, ensure_ascii=False, default=str)


def _get_lan_ip():
    """Return the machine's LAN IP address, falling back to 127.0.0.1."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        s.connect(("10.254.254.254", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>东方财富 - 个人普通账户</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    background: #f5f5f5;
    display: flex;
    justify-content: center;
    min-height: 100vh;
}
.app-container {
    width: 100%;
    max-width: 430px;
    background: #f0f0f0;
    min-height: 100vh;
}

/* ── Header ── */
.header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: #fff;
    padding: 20px 16px 16px;
    position: relative;
}
.header-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
    font-size: 13px;
    color: rgba(255,255,255,0.7);
}
.header-title { font-size: 18px; font-weight: 600; }
.account-type {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: rgba(255,255,255,0.12);
    padding: 4px 10px;
    border-radius: 12px;
    font-size: 12px;
    color: rgba(255,255,255,0.85);
}
.account-type .dot {
    width: 6px; height: 6px;
    background: #4caf50;
    border-radius: 50%;
}
.header-asset-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 6px;
}
.header-asset-label { font-size: 14px; color: rgba(255,255,255,0.8); }
.header-asset-value {
    font-size: 30px;
    font-weight: 700;
    color: #fff;
    letter-spacing: 1px;
}
.eye-btn {
    background: none; border: none;
    color: rgba(255,255,255,0.6);
    font-size: 16px;
    cursor: pointer;
    padding: 4px;
}
.header-pnl-row {
    display: flex;
    gap: 24px;
    margin-top: 12px;
    font-size: 12px;
}
.header-pnl-item { color: rgba(255,255,255,0.7); }
.header-pnl-value { font-size: 15px; font-weight: 600; }
.header-pnl-value.up { color: #ff5252; }
.header-pnl-value.down { color: #4caf50; }

/* ── Asset Summary Card ── */
.asset-card {
    margin: -6px 12px 10px;
    background: #fff;
    border-radius: 12px;
    padding: 16px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.08);
    position: relative;
    z-index: 1;
}
.asset-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
    font-size: 15px;
    font-weight: 600;
    color: #333;
}
.asset-card-header .time {
    font-size: 11px;
    color: #999;
    font-weight: 400;
}
.asset-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid #f0f0f0;
    font-size: 14px;
}
.asset-row:last-child { border-bottom: none; }
.asset-row .label { color: #666; }
.asset-row .value { font-weight: 600; color: #333; }
.asset-row .value.red { color: #e33a3d; }
.asset-row .value.green { color: #4caf50; }
.asset-row .value.bold { font-size: 16px; font-weight: 700; }

/* ── Section ── */
.section {
    margin: 0 12px 10px;
}
.section-title {
    font-size: 15px;
    font-weight: 600;
    color: #333;
    padding: 8px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.section-title .count { font-size: 12px; color: #999; font-weight: 400; }

/* ── Stock Card ── */
.stock-card {
    background: #fff;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 8px;
    box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}
.stock-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 10px;
}
.stock-name { font-size: 15px; font-weight: 600; color: #222; }
.stock-code {
    font-size: 11px;
    color: #999;
    margin-top: 2px;
}
.stock-meta {
    display: flex;
    gap: 20px;
    font-size: 12px;
    color: #888;
    margin-bottom: 8px;
}
.stock-meta span { color: #555; font-weight: 500; }
.stock-bottom {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.stock-pnl {
    font-size: 13px;
    font-weight: 600;
}
.stock-pnl.up { color: #e33a3d; }
.stock-pnl.down { color: #4caf50; }
.stock-value {
    font-size: 13px;
    color: #666;
}

/* ── Bottom Tab Bar ── */
.tab-bar {
    position: sticky;
    bottom: 0;
    background: #fff;
    display: flex;
    justify-content: space-around;
    padding: 8px 0 env(safe-area-inset-bottom, 8px);
    border-top: 1px solid #e8e8e8;
    margin-top: 12px;
}
.tab-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    font-size: 10px;
    color: #999;
    cursor: pointer;
    padding: 4px 16px;
}
.tab-item.active { color: #e33a3d; }
.tab-item .tab-icon { font-size: 20px; }
.tab-item.active .tab-icon { color: #e33a3d; }

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 40px 20px;
    color: #999;
    font-size: 14px;
}

/* ── Category Collapse ── */
.cat-section {
    margin-bottom: 6px;
}
.cat-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0;
    cursor: pointer;
    user-select: none;
}
.cat-header .cat-name {
    font-size: 14px;
    font-weight: 600;
    color: #333;
}
.cat-header .cat-info {
    display: flex;
    align-items: center;
    gap: 6px;
    flex: 1;
    margin-left: 8px;
}
.cat-header .cat-mv {
    font-size: 12px;
    color: #555;
    font-weight: 500;
}
.cat-header .cat-total-pnl {
    font-size: 12px;
    font-weight: 600;
}
.cat-header .cat-total-pnl.up { color: #e33a3d; }
.cat-header .cat-total-pnl.down { color: #4caf50; }
.cat-header .cat-right {
    display: flex;
    align-items: center;
    gap: 6px;
}
.cat-header .cat-daily-pnl {
    font-size: 12px;
    font-weight: 500;
}
.cat-header .cat-daily-pnl.up { color: #e33a3d; }
.cat-header .cat-daily-pnl.down { color: #4caf50; }
.cat-header .cat-count {
    font-size: 11px;
    color: #999;
    white-space: nowrap;
}
.cat-header .cat-arrow {
    font-size: 12px;
    color: #bbb;
    transition: transform 0.2s;
    display: inline-block;
}
.cat-section.collapsed .cat-body { display: none; }
.cat-section.collapsed .cat-arrow { transform: rotate(-90deg); }

/* ── Blur for hidden amounts ── */
.blur-on .amount { filter: blur(6px); }

/* ── News Modal ── */
.modal-backdrop {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.5);
    z-index: 1000;
    display: flex; align-items: flex-end; justify-content: center;
}
.modal-backdrop.hidden { display: none; }
.modal-sheet {
    width: 100%; max-width: 430px; max-height: 70vh;
    background: #fff; border-radius: 16px 16px 0 0;
    display: flex; flex-direction: column;
    animation: slideUp 0.25s ease-out;
}
@keyframes slideUp { from { transform: translateY(100%); } to { transform: translateY(0); } }
.modal-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 16px; border-bottom: 1px solid #eee;
}
.modal-title { font-size: 16px; font-weight: 600; }
.modal-close {
    background: none; border: none; font-size: 20px;
    color: #999; cursor: pointer; padding: 4px 8px;
}
.modal-body {
    overflow-y: auto; padding: 12px 16px; flex: 1;
}
.news-item {
    padding: 12px 0; border-bottom: 1px solid #f0f0f0;
    cursor: pointer; transition: background 0.15s;
}
.news-item:hover { background: #fafafa; }
.news-item:last-child { border-bottom: none; }
.news-item a {
    font-size: 14px; color: #333; text-decoration: none; font-weight: 500;
    display: block;
}
.news-item a:hover { color: #e33a3d; }
.news-item a:visited { color: #888; }
.news-item .news-intro {
    font-size: 12px; color: #999; margin-top: 4px;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    overflow: hidden;
}
.news-item .news-time { font-size: 11px; color: #bbb; margin-top: 4px; }
.news-empty { text-align: center; padding: 30px; color: #999; font-size: 14px; }
.news-loading { text-align: center; padding: 30px; color: #999; font-size: 14px; }

/* ── Hot News Button ── */
.news-btn {
    display: inline-flex; align-items: center; gap: 3px;
    font-size: 11px; color: #e33a3d; cursor: pointer;
    padding: 2px 8px; border: 1px solid #e33a3d;
    border-radius: 10px; background: #fff;
    margin-left: 8px; transition: all 0.15s;
}
.news-btn:hover { background: #e33a3d; color: #fff; }
.news-btn .badge {
    background: #e33a3d; color: #fff; font-size: 10px;
    border-radius: 8px; padding: 0 5px; min-width: 16px; text-align: center;
}
.news-btn:hover .badge { background: #fff; color: #e33a3d; }

/* ── Market Sentiment Gauge ── */
.sentiment-card {
    margin: 0 12px 10px;
    background: #141824;
    border-radius: 12px;
    padding: 14px 16px 16px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.2);
}
.sentiment-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0;
    font-size: 14px;
    font-weight: 600;
    color: #ccd;
}
.sentiment-card-header .sentiment-time {
    font-size: 10px;
    color: #667;
    font-weight: 400;
}
.sentiment-gauge-wrap {
    position: relative;
    width: 100%;
    max-width: 320px;
    margin: 0 auto;
}
.sentiment-gauge-wrap svg {
    display: block;
    width: 100%;
    height: auto;
}
.sentiment-needle {
    transform-origin: 150px 125px;
    transition: transform 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}
.sentiment-center-display {
    text-align: center;
    margin-top: -40px;
    position: relative;
    z-index: 1;
}
.sentiment-center-value {
    font-size: 26px;
    font-weight: 700;
    letter-spacing: 2px;
    color: #fff;
}
.sentiment-center-summary {
    font-size: 11px;
    color: #889;
    margin-top: 2px;
    line-height: 1.4;
}
@keyframes gaugePulse {
    0%, 100% { opacity: 0.3; }
    50% { opacity: 0.8; }
}
.sentiment-center-value.loading {
    animation: gaugePulse 1.5s ease-in-out infinite;
    color: #556;
}
/* ── Sector Sentiment Cards ── */
.sector-sentiment-wrap {
    margin: 0 12px 10px;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}
.sector-card {
    flex: 1 1 auto;
    min-width: 100px;
    max-width: 130px;
    background: #141824;
    border-radius: 10px;
    padding: 8px 6px 10px;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}
.sector-card .sector-name {
    font-size: 11px;
    font-weight: 600;
    color: #99a;
    margin-bottom: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.sector-mini-gauge {
    width: 80px;
    height: 48px;
    margin: 0 auto;
    display: block;
}
.sector-mini-needle {
    transform-origin: 40px 36px;
    transition: transform 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}
.sector-card .sector-value {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 1px;
    margin-top: -2px;
}
.sector-card .sector-meta {
    font-size: 9px;
    color: #556;
    margin-top: 1px;
    line-height: 1.3;
}
.sector-bullish .sector-value { color: #ff6b6b; }
.sector-bearish .sector-value { color: #69db7c; }
.sector-neutral .sector-value { color: #ffd43b; }
.sector-no_data .sector-value { color: #556; }
.sector-bullish { border-top: 2px solid #ff6b6b; }
.sector-bearish { border-top: 2px solid #69db7c; }
.sector-neutral { border-top: 2px solid #ffd43b; }
.sector-no_data { border-top: 2px solid #3a3d4a; }
.sector-empty {
    color: #556;
    font-size: 12px;
    text-align: center;
    padding: 14px 0;
    margin: 0 12px 10px;
    background: #141824;
    border-radius: 10px;
}
</style>
</head>
<body>
<div class="app-container">

<!-- ── Header ── -->
<div class="header">
    <div class="header-top">
        <span class="header-title">东方证券</span>
        <span class="account-type"><span class="dot"></span>个人普通账户</span>
    </div>
    <div class="header-asset-row">
        <span class="header-asset-label">总资产</span>
        <span class="header-asset-value amount" id="headerTotal">--</span>
        <button class="eye-btn" id="eyeBtn" title="显示/隐藏金额">👁</button>
    </div>
    <div class="header-pnl-row">
        <div class="header-pnl-item">
            今日盈亏<br><span class="header-pnl-value" id="headerDailyPnl">--</span>
        </div>
        <div class="header-pnl-item">
            持仓盈亏<br><span class="header-pnl-value" id="headerPosPnl">--</span>
        </div>
        <div class="header-pnl-item">
            累计盈亏<br><span class="header-pnl-value" id="headerTotalPnl">--</span>
        </div>
    </div>
</div>

<!-- ── Asset Summary Card ── -->
<div class="asset-card">
    <div class="asset-card-header">
        <span>资产概览</span>
        <span class="time" id="updateTime">--</span>
    </div>
    <div class="asset-row">
        <span class="label">总资产</span>
        <span class="value amount bold" id="totalValue">--</span>
    </div>
    <div class="asset-row">
        <span class="label">持仓市值</span>
        <span class="value amount" id="marketValue">--</span>
    </div>
    <div class="asset-row">
        <span class="label">可用资金</span>
        <span class="value amount" id="availFunds">--</span>
    </div>
    <div class="asset-row">
        <span class="label">今日盈亏</span>
        <span class="value amount" id="dailyPnl">--</span>
    </div>
    <div class="asset-row">
        <span class="label">持仓盈亏</span>
        <span class="value amount" id="posPnl">--</span>
    </div>
    <div class="asset-row">
        <span class="label">累计盈亏</span>
        <span class="value amount" id="totalPnl">--</span>
    </div>
</div>

<!-- ── Sector Sentiment Dashboard ── -->
<div class="sector-sentiment-wrap" id="sectorSentimentWrap">
    <div class="sector-empty" id="sectorSentimentEmpty">板块情绪数据采集中...</div>
</div>

<!-- ── Market Sentiment Gauge ── -->
<div class="sentiment-card" id="sentimentDashboard">
    <div class="sentiment-card-header">
        <span>市场情绪</span>
        <span class="sentiment-time" id="sentimentTime">--</span>
    </div>
    <div class="sentiment-gauge-wrap">
        <svg viewBox="0 0 300 175" xmlns="http://www.w3.org/2000/svg">
            <defs>
                <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                    <stop offset="0%" stop-color="#4caf50"/>
                    <stop offset="35%" stop-color="#8bc34a"/>
                    <stop offset="50%" stop-color="#f59e0b"/>
                    <stop offset="65%" stop-color="#ff9800"/>
                    <stop offset="80%" stop-color="#ff5722"/>
                </linearGradient>
            </defs>
            <!-- Outer silver ring -->
            <path d="M 45 125 A 105 105 0 0 1 255 125"
                  fill="none" stroke="#334" stroke-width="4" stroke-linecap="round"/>
            <!-- Colored arc (0-80) -->
            <path d="M 45 125 A 105 105 0 0 1 255 125"
                  fill="none" stroke="url(#gaugeGrad)" stroke-width="10" stroke-linecap="butt"
                  stroke-dasharray="263.89 65.97" stroke-dashoffset="0"/>
            <!-- Red zone arc (80-100) -->
            <path d="M 45 125 A 105 105 0 0 1 255 125"
                  fill="none" stroke="#e33a3d" stroke-width="10" stroke-linecap="butt"
                  stroke-dasharray="65.97 263.89" stroke-dashoffset="-263.89"/>
            <!-- Tick marks -->
            <line x1="45.0" y1="125.0" x2="54.0" y2="125.0" stroke="#8899aa" stroke-width="1.5"/>
<line x1="50.1" y1="92.6" x2="58.7" y2="95.3" stroke="#8899aa" stroke-width="1"/>
<line x1="65.1" y1="63.3" x2="72.3" y2="68.6" stroke="#8899aa" stroke-width="1.5"/>
<line x1="88.3" y1="40.1" x2="93.6" y2="47.3" stroke="#8899aa" stroke-width="1"/>
<line x1="117.6" y1="25.1" x2="120.3" y2="33.7" stroke="#8899aa" stroke-width="1.5"/>
<line x1="150.0" y1="20.0" x2="150.0" y2="29.0" stroke="#8899aa" stroke-width="1"/>
<line x1="182.4" y1="25.1" x2="179.7" y2="33.7" stroke="#8899aa" stroke-width="1.5"/>
<line x1="211.7" y1="40.1" x2="206.4" y2="47.3" stroke="#8899aa" stroke-width="1"/>
<line x1="234.9" y1="63.3" x2="227.7" y2="68.6" stroke="#8899aa" stroke-width="1.5"/>
<line x1="249.9" y1="92.6" x2="241.3" y2="95.3" stroke="#8899aa" stroke-width="1"/>
<line x1="255.0" y1="125.0" x2="246.0" y2="125.0" stroke="#8899aa" stroke-width="1.5"/>
            <!-- Numbers -->
            <text x="66.0" y="129.0" text-anchor="middle" font-size="10" fill="#8899aa" font-family="Arial, sans-serif">0</text>
<text x="82.0" y="79.6" text-anchor="middle" font-size="10" fill="#8899aa" font-family="Arial, sans-serif">20</text>
<text x="124.0" y="49.1" text-anchor="middle" font-size="10" fill="#8899aa" font-family="Arial, sans-serif">40</text>
<text x="176.0" y="49.1" text-anchor="middle" font-size="10" fill="#8899aa" font-family="Arial, sans-serif">60</text>
<text x="218.0" y="79.6" text-anchor="middle" font-size="10" fill="#8899aa" font-family="Arial, sans-serif">80</text>
<text x="234.0" y="129.0" text-anchor="middle" font-size="10" fill="#8899aa" font-family="Arial, sans-serif">100</text>
            <!-- Center cap -->
            <circle cx="150" cy="125" r="8" fill="#1a1a2e" stroke="#334" stroke-width="2"/>
            <!-- Needle -->
            <g class="sentiment-needle" id="gaugeNeedle" style="transform:rotate(0deg)">
                <line x1="150" y1="125" x2="150" y2="30" stroke="#e8e8e8" stroke-width="2" stroke-linecap="round"/>
                <polygon points="146,36 150,24 154,36" fill="#e33a3d"/>
            </g>
            <!-- Center dot -->
            <circle cx="150" cy="125" r="4" fill="#e8e8e8"/>
        </svg>
    </div>
    <div class="sentiment-center-display">
        <div class="sentiment-center-value loading" id="sentimentMood">--</div>
        <div class="sentiment-center-summary" id="sentimentSummary">正在获取市场数据...</div>
    </div>
</div>

<!-- ── Holdings by Category ── -->
<div class="section">
    <div class="section-title">
        <span>持仓股票</span>
        <span class="count" id="stockCount">0只</span>
    </div>
    <div id="stockList"></div>
</div>

<!-- ── Tab Bar ── -->
<div class="tab-bar">
    <div class="tab-item"><span class="tab-icon">📈</span>行情</div>
    <div class="tab-item active"><span class="tab-icon">💼</span>账户</div>
    <div class="tab-item"><span class="tab-icon">🔄</span>交易</div>
    <div class="tab-item"><span class="tab-icon">📊</span>理财</div>
    <div class="tab-item"><span class="tab-icon">👤</span>我的</div>
</div>

<!-- ── News Modal ── -->
<div class="modal-backdrop hidden" id="newsModal" onclick="if(event.target===this)closeNews()">
    <div class="modal-sheet">
        <div class="modal-header">
            <span class="modal-title" id="newsModalTitle">热点新闻</span>
            <button class="modal-close" onclick="closeNews()">✕</button>
        </div>
        <div class="modal-body" id="newsModalBody">
            <div class="news-loading">加载中...</div>
        </div>
    </div>
</div>

</div>

<script>
const DATA = __DATA_PLACEHOLDER__;
const CATEGORIES = __CATEGORIES_PLACEHOLDER__;

function fmt(v, dec) {
    if (v == null || isNaN(v)) return '--';
    dec = (dec == null) ? 2 : dec;
    return Number(v).toLocaleString('zh-CN', {minimumFractionDigits: dec, maximumFractionDigits: dec});
}
function fmtMoney(v) { return fmtWan(v); }
function fmtPnl(v)  { return fmtWan(v, true); }
function fmtWan(v, isPnl) {
    if (v == null || isNaN(v)) return '--';
    var abs = Math.abs(v);
    if (abs >= 100000) {
        var s = isPnl ? (v >= 0 ? '+' : '') : '';
        return s + (v / 10000).toFixed(2) + '万';
    }
    if (isPnl) return (v >= 0 ? '+' : '') + fmt(v);
    return '¥' + fmt(v);
}
function pnlClass(v) {
    if (v > 0) return 'up';
    if (v < 0) return 'down';
    return '';
}
function setHtml(id, html) { document.getElementById(id).innerHTML = html; }
function setClass(id, cls) { document.getElementById(id).className = cls; }

function renderStockCard(p) {
    var cumPnlPct = p.pnl_pct || 0;
    var dailyPnlVal = p.daily_pnl || 0;
    var totalPnlVal = p.total_pnl || 0;
    var pnlCls = pnlClass(dailyPnlVal);
    var tPnlCls = pnlClass(totalPnlVal);
    var dailyPnlPct = (p.prev_close > 0) ? ((p.price - p.prev_close) / p.prev_close * 100) : 0;

    var sid = 's' + p.code;
    var html = '<div class="stock-card" id="card-' + sid + '">';
    html += '<div class="stock-top">';
    html += '<div><div class="stock-name">' + p.name;
    html += '<button class="news-btn" data-code="' + p.code + '" data-name="' + p.name + '" onclick="event.stopPropagation();var e=this;openNews(e.dataset.code,e.dataset.name)">建议</button>';
    html += '</div>';
    html += '<div class="stock-code">' + p.code + '</div></div>';
    html += '<div class="stock-pnl ' + pnlCls + '" id="dailyPnl-' + sid + '">' + fmtPnl(dailyPnlVal) + ' (' + fmtPnl(dailyPnlPct) + '%)</div>';
    html += '</div>';
    html += '<div class="stock-meta">';
    html += '<span>成本: ' + fmt(p.cost, 3) + '</span>';
    html += '<span>现价: <b id="price-' + sid + '">' + fmt(p.price, 3) + '</b></span>';
    html += '</div>';
    html += '<div class="stock-bottom">';
    html += '<div class="stock-meta">';
    html += '<div>持仓 <span>' + (p.shares || 0) + '</span>股';
    html += ' | 可用 <span>' + (p.available || 0) + '</span>股</div>';
    html += '</div>';
    html += '<div class="stock-value" id="mv-' + sid + '">市值: ' + fmtWan(p.market_value) + '</div>';
    html += '</div>';
    html += '<div style="font-size:11px;margin-top:4px;">';
    html += '累计盈亏 <span class="stock-pnl ' + tPnlCls + '" id="totalPnl-' + sid + '">' + fmtPnl(totalPnlVal) + ' (' + fmtPnl(cumPnlPct) + '%)</span>';
    html += '</div>';
    html += '</div>';
    return html;
}


function updatePrices(data) {
    var d = data || DATA;
    var totalVal = d.total_value || 0;
    var dailyPnl = d.total_daily_pnl || 0;
    var pos = d.positions || [];

    var marketVal = 0;
    var holdingPnl = 0;
    var cumPnl = 0;
    pos.forEach(function(p) {
        marketVal += p.market_value || 0;
        holdingPnl += (p.market_value || 0) - (p.cost || 0) * (p.shares || 0);
        cumPnl += p.total_pnl || 0;
    });
    var availCash = totalVal - marketVal;

    // Header
    setHtml('headerTotal', fmtMoney(totalVal));
    var hdp = document.getElementById('headerDailyPnl');
    hdp.innerHTML = fmtPnl(dailyPnl);
    hdp.className = 'header-pnl-value ' + pnlClass(dailyPnl);
    var hpp = document.getElementById('headerPosPnl');
    hpp.innerHTML = fmtPnl(holdingPnl);
    hpp.className = 'header-pnl-value ' + pnlClass(holdingPnl);
    var htp = document.getElementById('headerTotalPnl');
    htp.innerHTML = fmtPnl(cumPnl);
    htp.className = 'header-pnl-value ' + pnlClass(cumPnl);

    setHtml('availFunds', fmtMoney(availCash));
    setClass('dailyPnl', 'value amount ' + pnlClass(dailyPnl));
    setHtml('dailyPnl', fmtPnl(dailyPnl));
    setClass('posPnl', 'value amount ' + pnlClass(holdingPnl));
    setHtml('posPnl', fmtPnl(holdingPnl));
    setClass('totalPnl', 'value amount ' + pnlClass(cumPnl));
    setHtml('totalPnl', fmtPnl(cumPnl));

    var now = new Date();
    setHtml('updateTime', now.toLocaleString('zh-CN'));

    // Update each stock card
    pos.forEach(function(p) {
        var sid = 's' + p.code;
        var dailyPnlVal = p.daily_pnl || 0;
        var dailyPnlPct = (p.prev_close > 0) ? ((p.price - p.prev_close) / p.prev_close * 100) : 0;
        var pnlCls = pnlClass(dailyPnlVal);
        var totalPnlVal = p.total_pnl || 0;
        var cumPnlPct = p.pnl_pct || 0;
        var tPnlCls = pnlClass(totalPnlVal);

        var el;

        // Daily P&L
        el = document.getElementById('dailyPnl-' + sid);
        if (el) {
            el.className = 'stock-pnl ' + pnlCls;
            el.innerHTML = fmtPnl(dailyPnlVal) + ' (' + fmtPnl(dailyPnlPct) + '%)';
        }

        // Price
        el = document.getElementById('price-' + sid);
        if (el) { el.textContent = fmt(p.price, 3); }

        // Market value
        el = document.getElementById('mv-' + sid);
        if (el) { el.textContent = '市值: ' + fmtWan(p.market_value); }

        // Total P&L
        el = document.getElementById('totalPnl-' + sid);
        if (el) {
            el.className = 'stock-pnl ' + tPnlCls;
            el.innerHTML = fmtPnl(totalPnlVal) + ' (' + fmtPnl(cumPnlPct) + '%)';
        }
    });

    // Update category headers (market value, total P&L, daily P&L)
    var catMap = {};
    var catOrder = CATEGORIES.order || [];
    var codeToCat = CATEGORIES.code_to_cat || {};
    catOrder.forEach(function(c) { catMap[c] = {mv: 0, daily: 0, total: 0}; });
    catMap['其它'] = {mv: 0, daily: 0, total: 0};

    pos.forEach(function(p) {
        var code = String(p.code || '');
        var cat = codeToCat[code];
        if (!cat || !catMap[cat]) cat = '其它';
        catMap[cat].mv += p.market_value || 0;
        catMap[cat].daily += p.daily_pnl || 0;
        catMap[cat].total += p.total_pnl || 0;
    });

    catOrder.forEach(function(cat) {
        var d = catMap[cat];
        if (!d || d.mv === 0) return;
        updateCatHeader(cat, d.mv, d.total, d.daily);
    });
    if (catMap['其它'].mv > 0) {
        updateCatHeader('其它', catMap['其它'].mv, catMap['其它'].total, catMap['其它'].daily);
    }
}

function updateCatHeader(cat, mv, totalPnl, dailyPnl) {
    var el;
    el = document.getElementById('cat-mv-' + cat);
    if (el) el.textContent = fmtWan(mv);
    el = document.getElementById('cat-total-pnl-' + cat);
    if (el) {
        el.textContent = fmtWan(totalPnl, true);
        el.className = 'cat-total-pnl ' + pnlClass(totalPnl);
    }
    el = document.getElementById('cat-daily-pnl-' + cat);
    if (el) {
        el.textContent = fmtWan(dailyPnl, true);
        el.className = 'cat-daily-pnl ' + pnlClass(dailyPnl);
    }
}

function render(data) {
    var d = data || DATA;
    // Check for login failure state
    if (DATA._error === 'login_failed') {
        setHtml('headerTotal', '--');
        setHtml('stockCount', '0只');
        setHtml('stockList', '<div class="empty-state" style="font-size:15px;color:#e33a3d;">⚠️ 登录失败，无法获取持仓数据</div>'
            + '<div class="empty-state" style="font-size:12px;margin-top:12px;line-height:1.6;">请检查 config.json 中的 Cookie 是否过期<br>或关闭程序后使用 <b>--relogin</b> 参数重新登录</div>');
        var now = new Date();
        setHtml('updateTime', now.toLocaleString('zh-CN'));
        // Hide sentiment sections
        setHtml('sentimentMood', '--');
        setHtml('sentimentSummary', '请先完成登录');
        document.getElementById('sentimentMood').classList.add('loading');
        return;
    }
    // Save collapse state before re-render
    var collapsed = {};
    document.querySelectorAll('.cat-section').forEach(function(el, i) {
        if (el.classList.contains('collapsed')) collapsed[i] = true;
    });
    var totalVal = d.total_value || 0;
    var dailyPnl = d.total_daily_pnl || 0;
    var pos = d.positions || [];

    var marketVal = 0;
    var holdingPnl = 0;
    var cumPnl = 0;
    pos.forEach(function(p) {
        marketVal += p.market_value || 0;
        holdingPnl += (p.market_value || 0) - (p.cost || 0) * (p.shares || 0);
        cumPnl += p.total_pnl || 0;
    });
    var availCash = totalVal - marketVal;

    // Header
    setHtml('headerTotal', fmtMoney(totalVal));
    var hdp = document.getElementById('headerDailyPnl');
    hdp.innerHTML = fmtPnl(dailyPnl);
    hdp.className = 'header-pnl-value ' + pnlClass(dailyPnl);
    var hpp = document.getElementById('headerPosPnl');
    hpp.innerHTML = fmtPnl(holdingPnl);
    hpp.className = 'header-pnl-value ' + pnlClass(holdingPnl);
    var htp = document.getElementById('headerTotalPnl');
    htp.innerHTML = fmtPnl(cumPnl);
    htp.className = 'header-pnl-value ' + pnlClass(cumPnl);

    // Asset card
    setHtml('totalValue', fmtMoney(totalVal));
    setHtml('marketValue', fmtMoney(marketVal));
    setHtml('availFunds', fmtMoney(availCash));
    setClass('dailyPnl', 'value amount ' + pnlClass(dailyPnl));
    setHtml('dailyPnl', fmtPnl(dailyPnl));
    setClass('posPnl', 'value amount ' + pnlClass(holdingPnl));
    setHtml('posPnl', fmtPnl(holdingPnl));
    setClass('totalPnl', 'value amount ' + pnlClass(cumPnl));
    setHtml('totalPnl', fmtPnl(cumPnl));

    var now = new Date();
    setHtml('updateTime', now.toLocaleString('zh-CN'));

    // Build category → positions lookup
    var catMap = {};       // {catName: [position, ...]}
    var catOrder = CATEGORIES.order || [];
    var otherPos = [];     // uncategorized
    var codeToCat = CATEGORIES.code_to_cat || {};

    catOrder.forEach(function(c) { catMap[c] = []; });

    pos.forEach(function(p) {
        var code = String(p.code || '');
        var cat = codeToCat[code];
        if (cat && catMap[cat]) {
            catMap[cat].push(p);
        } else {
            otherPos.push(p);
        }
    });

    // Build HTML grouped by category
    var listHtml = '';
    var totalCount = 0;

    catOrder.forEach(function(cat) {
        var stocks = catMap[cat];
        if (!stocks || stocks.length === 0) return;
        stocks.sort(function(a, b) { return (b.market_value || 0) - (a.market_value || 0); });
        totalCount += stocks.length;

        var catMv = 0;
        var catDailyPnl = 0;
        var catTotalPnl = 0;
        stocks.forEach(function(p) {
            catMv += p.market_value || 0;
            catDailyPnl += p.daily_pnl || 0;
            catTotalPnl += p.total_pnl || 0;
        });
        var totalPnlCls = pnlClass(catTotalPnl);
        var dailyPnlCls = pnlClass(catDailyPnl);


        listHtml += '<div class="cat-section">';
        listHtml += '<div class="cat-header" onclick="toggleCat(this)">';
        listHtml += '<span class="cat-name">' + cat + '</span>';
        listHtml += '<div class="cat-info">';
        listHtml += '<span class="cat-mv" id="cat-mv-' + cat + '">' + fmtWan(catMv) + '</span>';
        listHtml += '<span class="cat-total-pnl ' + totalPnlCls + '" id="cat-total-pnl-' + cat + '">' + fmtWan(catTotalPnl, true) + '</span>';
        listHtml += '</div>';
        listHtml += '<div class="cat-right">';
        listHtml += '<span class="cat-daily-pnl ' + dailyPnlCls + '" id="cat-daily-pnl-' + cat + '">' + fmtWan(catDailyPnl, true) + '</span>';
        listHtml += '<span class="cat-count">' + stocks.length + '只</span>';
        listHtml += '<span class="cat-arrow">▼</span>';
        listHtml += '</div>';
        listHtml += '</div>';
        listHtml += '<div class="cat-body">';
        stocks.forEach(function(p) { listHtml += renderStockCard(p); });
        listHtml += '</div></div>';
    });

    // Others (uncategorized)
    if (otherPos.length > 0) {
        totalCount += otherPos.length;
        otherPos.sort(function(a, b) { return (b.market_value || 0) - (a.market_value || 0); });
        var oMv = 0, oDaily = 0, oTotal = 0;
        otherPos.forEach(function(p) {
            oMv += p.market_value || 0;
            oDaily += p.daily_pnl || 0;
            oTotal += p.total_pnl || 0;
        });
        var oTotalCls = pnlClass(oTotal);
        var oDailyCls = pnlClass(oDaily);

        listHtml += '<div class="cat-section">';
        listHtml += '<div class="cat-header" onclick="toggleCat(this)">';
        listHtml += '<span class="cat-name">其它</span>';
        listHtml += '<div class="cat-info">';
        listHtml += '<span class="cat-mv" id="cat-mv-其它">' + fmtWan(oMv) + '</span>';
        listHtml += '<span class="cat-total-pnl ' + oTotalCls + '" id="cat-total-pnl-其它">' + fmtWan(oTotal, true) + '</span>';
        listHtml += '</div>';
        listHtml += '<div class="cat-right">';
        listHtml += '<span class="cat-daily-pnl ' + oDailyCls + '" id="cat-daily-pnl-其它">' + fmtWan(oDaily, true) + '</span>';
        listHtml += '<span class="cat-count">' + otherPos.length + '只</span>';
        listHtml += '<span class="cat-arrow">▼</span>';
        listHtml += '</div>';
        listHtml += '</div>';
        listHtml += '<div class="cat-body">';
        otherPos.forEach(function(p) { listHtml += renderStockCard(p); });
        listHtml += '</div></div>';
    }

    if (totalCount === 0) {
        listHtml = '<div class="empty-state">暂无持仓数据</div>';
    }

    setHtml('stockCount', totalCount + '只');
    setHtml('stockList', listHtml);

    // Restore collapse state
    document.querySelectorAll('.cat-section').forEach(function(el, i) {
        if (collapsed[i]) el.classList.add('collapsed');
    });
}

function toggleCat(header) {
    header.parentElement.classList.toggle('collapsed');
}

// Eye toggle
(function() {
    var visible = true;
    document.getElementById('eyeBtn').addEventListener('click', function() {
        visible = !visible;
        this.textContent = visible ? '👁' : '👁‍🗨';
        if (visible) {
            document.body.classList.remove('blur-on');
        } else {
            document.body.classList.add('blur-on');
        }
    });
})();

// Force hard reload if restored from bfcache (stale data)
window.addEventListener('pageshow', function(e) {
    if (e.persisted) { window.location.reload(true); }
});

// Keyboard shortcut: Ctrl+H to toggle amounts
document.addEventListener('keydown', function(e) {
    if (e.ctrlKey && e.key === 'h') {
        e.preventDefault();
        document.getElementById('eyeBtn').click();
    }
});

// ── News Modal ──
function openNews(code, name) {
    document.getElementById('newsModalTitle').textContent = name + ' — 热点情报';
    document.getElementById('newsModalBody').innerHTML = '<div class="news-loading">分析中...</div>';
    document.getElementById('newsModal').classList.remove('hidden');
    _fetchHotspot(code, name, 0);
}

function _fetchHotspot(code, name, retryCount) {
    fetch('/hotspot?code=' + encodeURIComponent(code) + '&name=' + encodeURIComponent(name)).then(function(r) {
        return r.json();
    }).then(function(data) {
        if (data.status === 'processing' && retryCount < 3) {
            // Background analysis still running — retry after 3 seconds
            document.getElementById('newsModalBody').innerHTML =
                '<div class="news-loading">AI分析进行中，约需等待10-30秒... (' + (retryCount + 1) + '/3)</div>';
            setTimeout(function() { _fetchHotspot(code, name, retryCount + 1); }, 3000);
            return;
        }
        renderHotspot(data);
    }).catch(function() {
        document.getElementById('newsModalBody').innerHTML = '<div class="news-empty">加载失败，请稍后重试</div>';
    });
}

function renderHotspot(data) {
    var body = document.getElementById('newsModalBody');
    if (!data || data.status === 'error') {
        body.innerHTML = '<div class="news-empty">数据获取失败' + (data && data.reasons ? ': ' + data.reasons[0] : '') + '</div>';
        return;
    }

    var actColors = {buy: '#e33a3d', sell: '#4caf50', hold: '#f59e0b', wait: '#888'};
    var actBg = {buy: '#fff5f5,#ffe8e8', sell: '#f0fff0,#e0ffe0', hold: '#fffef5,#fff8e0', wait: '#f5f5f5,#eee'};
    var actColor = actColors[data.action] || '#f59e0b';
    var confStars = data.confidence === '高' ? '★★★' : data.confidence === '中' ? '★★☆' : '★☆☆';

    var html = '';

    // ── Recommendation card ──
    html += '<div style="background:linear-gradient(135deg,' + (actBg[data.action] || '#f5f5f5,#eee') +
            ');border-radius:12px;padding:16px;margin-bottom:12px;text-align:center;">';
    html += '<div style="font-size:13px;color:#888;margin-bottom:6px;">智能分析 · 买卖建议</div>';
    html += '<div style="font-size:36px;font-weight:700;color:' + actColor + ';">' + (data.recommendation || '观望') + '</div>';
    html += '<div style="font-size:12px;color:#999;margin-top:4px;">置信度 ' + confStars + ' · 评分 ' + (data.score || 0) + '</div>';
    html += '<div style="font-size:13px;color:#555;margin-top:8px;line-height:1.5;">' + (data.summary || '') + '</div>';
    html += '</div>';

    // ── Position info card (if holding) ──
    if (data.position_info) {
        var pi = data.position_info;
        var pnlColor = (pi.pnl_pct || 0) >= 0 ? '#e33a3d' : '#4caf50';
        var pnlSign = (pi.pnl_pct || 0) >= 0 ? '+' : '';
        html += '<div style="background:#fff;border-radius:10px;padding:14px;margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,0.04);">';
        html += '<div style="font-size:14px;font-weight:600;color:#333;margin-bottom:8px;">持仓状态</div>';
        html += '<div style="display:flex;justify-content:space-between;font-size:13px;color:#555;padding:3px 0;">';
        html += '<span>持有</span><span style="font-weight:600;">' + (pi.shares || 0) + ' 股</span></div>';
        html += '<div style="display:flex;justify-content:space-between;font-size:13px;color:#555;padding:3px 0;">';
        html += '<span>成本</span><span style="font-weight:600;">¥' + (pi.cost || 0).toFixed(3) + '</span></div>';
        if (pi.current_price) {
            html += '<div style="display:flex;justify-content:space-between;font-size:13px;color:#555;padding:3px 0;">';
            html += '<span>现价</span><span style="font-weight:600;">¥' + pi.current_price.toFixed(3) + '</span></div>';
        }
        html += '<div style="display:flex;justify-content:space-between;font-size:13px;padding:3px 0;">';
        html += '<span>浮动盈亏</span><span style="font-weight:600;color:' + pnlColor + ';">' + pnlSign + (pi.pnl_pct || 0).toFixed(2) + '%</span></div>';
        html += '</div>';
    }

    // ── Trade plan card (if actionable) ──
    if (data.trade_plan) {
        var tp = data.trade_plan;
        var tpBg = tp.action === 'buy' ? '#fff5f5' : '#f0fff0';
        var tpBorder = tp.action === 'buy' ? '#e33a3d' : '#4caf50';
        html += '<div style="background:' + tpBg + ';border:1px solid ' + tpBorder +
                ';border-radius:10px;padding:14px;margin-bottom:10px;">';
        html += '<div style="font-size:14px;font-weight:600;color:' + tpBorder + ';margin-bottom:10px;">' +
                (tp.action === 'buy' ? '买入计划' : '卖出计划') + '</div>';
        html += '<div style="display:flex;justify-content:space-between;font-size:13px;color:#555;padding:3px 0;">';
        html += '<span>操作数量</span><span style="font-weight:700;color:#333;">' + (tp.shares || 0) + ' 股</span></div>';
        html += '<div style="display:flex;justify-content:space-between;font-size:13px;color:#555;padding:3px 0;">';
        html += '<span>' + (tp.action === 'buy' ? '买入价格' : '卖出价格') + '</span><span style="font-weight:700;color:#333;">¥' + (tp.price || 0).toFixed(2) + '</span></div>';
        if (tp.price_range && tp.price_range[0]) {
            html += '<div style="display:flex;justify-content:space-between;font-size:13px;color:#555;padding:3px 0;">';
            html += '<span>价格区间</span><span style="font-weight:600;">¥' + tp.price_range[0].toFixed(2) + ' ~ ¥' + tp.price_range[1].toFixed(2) + '</span></div>';
        }
        if (tp.target_price && tp.target_price > 0) {
            html += '<div style="display:flex;justify-content:space-between;font-size:13px;color:#555;padding:3px 0;">';
            html += '<span>目标价位</span><span style="font-weight:600;color:#e33a3d;">¥' + tp.target_price.toFixed(2) + '</span></div>';
        }
        if (tp.stop_loss && tp.stop_loss > 0) {
            html += '<div style="display:flex;justify-content:space-between;font-size:13px;color:#555;padding:3px 0;">';
            html += '<span>止损价位</span><span style="font-weight:600;color:#4caf50;">¥' + tp.stop_loss.toFixed(2) + '</span></div>';
        }
        if (tp.reasoning) {
            html += '<div style="font-size:11px;color:#999;margin-top:8px;line-height:1.4;">' + tp.reasoning + '</div>';
        }
        html += '</div>';
    }

    // ── Watch plan card (if not holding) ──
    if (data.watch_plan && !data.position_info) {
        var wp = data.watch_plan;
        html += '<div style="background:#f8f9ff;border:1px solid #8899cc;border-radius:10px;padding:14px;margin-bottom:10px;">';
        html += '<div style="font-size:14px;font-weight:600;color:#5566aa;margin-bottom:10px;">入场参考</div>';
        if (wp.entry_price && wp.entry_price > 0) {
            html += '<div style="display:flex;justify-content:space-between;font-size:13px;color:#555;padding:3px 0;">';
            html += '<span>建议入场价</span><span style="font-weight:700;color:#333;">¥' + wp.entry_price.toFixed(2) + '</span></div>';
        }
        html += '<div style="font-size:12px;color:#888;margin-top:6px;line-height:1.5;">' + (wp.entry_condition || '') + '</div>';
        if (wp.target_price && wp.target_price > 0) {
            html += '<div style="display:flex;justify-content:space-between;font-size:13px;color:#555;padding:3px 0;margin-top:4px;">';
            html += '<span>目标价位</span><span style="font-weight:600;color:#e33a3d;">¥' + wp.target_price.toFixed(2) + '</span></div>';
        }
        if (wp.stop_loss && wp.stop_loss > 0) {
            html += '<div style="display:flex;justify-content:space-between;font-size:13px;color:#555;padding:3px 0;">';
            html += '<span>止损价位</span><span style="font-weight:600;color:#4caf50;">¥' + wp.stop_loss.toFixed(2) + '</span></div>';
        }
        html += '</div>';
    }

    // ── Analysis details ──
    html += '<div style="background:#fff;border-radius:10px;padding:14px;margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,0.04);">';
    html += '<div style="font-size:14px;font-weight:600;color:#333;margin-bottom:10px;">分析依据</div>';
    if (data.reasons && data.reasons.length > 0) {
        html += '<div style="margin-bottom:8px;">';
        html += '<div style="font-size:12px;color:#e33a3d;margin-bottom:4px;">看多因素</div>';
        data.reasons.forEach(function(r) {
            html += '<div style="font-size:12px;color:#555;padding:3px 0;padding-left:12px;">• ' + r + '</div>';
        });
        html += '</div>';
    }
    if (data.risks && data.risks.length > 0) {
        html += '<div>';
        html += '<div style="font-size:12px;color:#4caf50;margin-bottom:4px;">风险因素</div>';
        data.risks.forEach(function(r) {
            html += '<div style="font-size:12px;color:#555;padding:3px 0;padding-left:12px;">• ' + r + '</div>';
        });
        html += '</div>';
    }
    if ((!data.reasons || data.reasons.length === 0) && (!data.risks || data.risks.length === 0)) {
        html += '<div style="font-size:12px;color:#999;text-align:center;padding:8px;">暂无显著多空信号，建议结合盘面综合判断</div>';
    }
    if (data.sentiment_label) {
        var slColor = data.sentiment_label === 'bullish' ? '#e33a3d' :
                      data.sentiment_label === 'bearish' ? '#4caf50' : '#999';
        var slText = data.sentiment_label === 'bullish' ? '偏多' :
                     data.sentiment_label === 'bearish' ? '偏空' : '中性';
        html += '<div style="margin-top:8px;font-size:11px;color:#999;">新闻情绪: <span style="color:' + slColor + ';font-weight:600;">' + slText + '</span>';
        if (data.total_mentions) html += ' · ' + data.total_mentions + '条相关';
        html += ' · ' + (data.updated_at || '') + '</div>';
    }
    html += '</div>';

    // ── Related news ──
    html += '<div style="font-size:14px;font-weight:600;color:#333;margin-bottom:8px;">相关资讯</div>';
    if (data.news && data.news.length > 0) {
        data.news.forEach(function(item) {
            var sentimentLabel = item.overall_sentiment_label || '';
            var sColor = sentimentLabel === 'Bullish' ? '#e33a3d' :
                         sentimentLabel === 'Bearish' ? '#4caf50' : '#999';
            var sTag = sentimentLabel === 'Bullish' ? '利好' :
                       sentimentLabel === 'Bearish' ? '利空' : '';
            var newsUrl = item.url || '#';
            html += '<div class="news-item" onclick="window.open(\\'' + newsUrl + '\\', \\'_blank\\')" style="cursor:pointer;">';
            html += '<div style="display:flex;justify-content:space-between;align-items:flex-start;">';
            html += '<span style="flex:1;font-size:14px;color:#333;font-weight:500;">' + (item.title || '') + '</span>';
            if (sTag) html += '<span style="font-size:10px;color:#fff;background:' + sColor + ';padding:1px 5px;border-radius:4px;margin-left:6px;white-space:nowrap;">' + sTag + '</span>';
            html += '</div>';
            if (item.summary) html += '<div class="news-intro">' + item.summary + '</div>';
            if (item.time_published || item.source) {
                html += '<div class="news-time">' + (item.source || '') + ' · ' + (item.time_published || '') + '</div>';
            }
            html += '</div>';
        });
    } else {
        html += '<div class="news-empty">暂无直接相关资讯，上方分析基于价格走势和板块动向</div>';
    }

    body.innerHTML = html;
}
function closeNews() {
    document.getElementById('newsModal').classList.add('hidden');
}

function updateSentiment(data) {
    if (!data) return;

    if (data.updated_at) {
        setHtml('sentimentTime', data.updated_at);
    }

    var gaugePct = data.gauge_pct;
    if (gaugePct == null) gaugePct = 50;

    // Rotate needle: gauge_pct 0 → -90deg, 50 → 0deg, 100 → +90deg
    var angle = (gaugePct - 50) * 1.8;
    var needle = document.getElementById('gaugeNeedle');
    if (needle) {
        needle.style.transform = 'rotate(' + angle + 'deg)';
    }

    // Update center display
    var el = document.getElementById('sentimentMood');
    if (el) {
        el.classList.remove('loading');
        if (!data.available) {
            el.textContent = '--';
            el.classList.add('loading');
        } else {
            el.textContent = data.mood_label || '--';
            var m = data.mood || 'neutral';
            if (m === 'bullish') {
                el.style.color = '#ff6b6b';
            } else if (m === 'defensive') {
                el.style.color = '#69db7c';
            } else {
                el.style.color = '#ffd43b';
            }
        }
    }

    setHtml('sentimentSummary', data.mood_summary || '正在获取市场数据...');
}

function updateSectorSentiment(data) {
    var wrap = document.getElementById('sectorSentimentWrap');
    if (!wrap) return;
    if (!data || !data.available || !(data.sectors && data.sectors.length)) {
        var infoEl = document.getElementById('sectorSentimentEmpty');
        if (infoEl) {
            infoEl.textContent = data && data.available === false ? '板块新闻采集中，稍后更新...' : '暂无板块情绪数据';
        }
        return;
    }
    var infoEl = document.getElementById('sectorSentimentEmpty');
    if (infoEl) infoEl.remove();

    var html = '';
    data.sectors.forEach(function(s) {
        var cls = 'sector-' + (s.verdict || 'neutral');
        var gPct = s.gauge_pct != null ? s.gauge_pct : 50;
        if (s.verdict === 'no_data') gPct = 0;
        var needleAngle = (gPct - 50) * 1.62;
        var metaText = s.verdict === 'no_data' ? (s.news_count > 0 ? s.news_count + '条相关' : '暂无数据') : s.news_count + '条相关新闻';
        var sourceNote = s.data_source ? '<div style="font-size:8px;color:#445">' + s.data_source + '</div>' : '';

        html += '<div class="sector-card ' + cls + '">';
        html += '<div class="sector-name">' + s.sector + '</div>';
        html += '<svg class="sector-mini-gauge" viewBox="0 0 80 48">';
        html += '<defs><linearGradient id="sg' + s.sector + '" x1="0%" y1="0%" x2="100%" y2="0%">';
        html += '<stop offset="0%" stop-color="#4caf50"/><stop offset="35%" stop-color="#8bc34a"/>';
        html += '<stop offset="50%" stop-color="#f59e0b"/><stop offset="65%" stop-color="#ff9800"/>';
        html += '<stop offset="80%" stop-color="#ff5722"/></linearGradient></defs>';
        html += '<path d="M 8 36 A 32 32 0 0 1 72 36" fill="none" stroke="#334" stroke-width="2" stroke-linecap="round"/>';
        html += '<path d="M 8 36 A 32 32 0 0 1 72 36" fill="none" stroke="url(#sg' + s.sector + ')" stroke-width="4" stroke-linecap="butt" stroke-dasharray="80.42 20.11" stroke-dashoffset="0"/>';
        html += '<path d="M 8 36 A 32 32 0 0 1 72 36" fill="none" stroke="#e33a3d" stroke-width="4" stroke-linecap="butt" stroke-dasharray="20.11 80.42" stroke-dashoffset="-80.42"/>';
        html += '<g class="sector-mini-needle" style="transform:rotate(' + needleAngle.toFixed(1) + 'deg)">';
        html += '<line x1="40" y1="36" x2="40" y2="12" stroke="#e8e8e8" stroke-width="1.2" stroke-linecap="round"/>';
        html += '</g>';
        html += '<circle cx="40" cy="36" r="2" fill="#e8e8e8"/>';
        html += '</svg>';
        html += '<div class="sector-value">' + (s.verdict_label || '--') + '</div>';
        html += '<div class="sector-meta">' + metaText + '</div>';
        html += sourceNote;
        html += '</div>';
    });
    wrap.innerHTML = html;
}

render();


// Initial sentiment fetch
fetch('/sentiment').then(function(r) { return r.json(); }).then(updateSentiment).catch(function(){});
fetch('/sector-sentiment').then(function(r) { return r.json(); }).then(updateSectorSentiment).catch(function(){});

// Poll for real-time updates every 1 second
var _pollCount = 0;
var _syncFailures = 0;
setInterval(function() {
    fetch('/data').then(function(r) { return r.json(); }).then(function(d) {
        _syncFailures = 0;
        updatePrices(d);
    }).catch(function(){
        _syncFailures++;
        if (_syncFailures === 5) {
            // Show warning icon in update time after 5 consecutive failures
            setHtml('updateTime', '⚠ 数据同步失败');
        }
    });
    _pollCount++;
    if (_pollCount % 30 === 0) {
        fetch('/sentiment').then(function(r) { return r.json(); }).then(updateSentiment).catch(function(){});
        fetch('/sector-sentiment').then(function(r) { return r.json(); }).then(updateSectorSentiment).catch(function(){});
    }
}, 1000);
</script>
</body>
</html>"""


def _generate_page(holdings_data, code_to_cat=None, cat_order=None):
    """Generate HTML page with holdings and category data embedded."""
    global _code_to_cat_cache, _cat_order_cache
    _code_to_cat_cache = code_to_cat or {}
    _cat_order_cache = cat_order or []
    data_json = json.dumps(holdings_data, ensure_ascii=False, default=str)
    data_json = data_json.replace("</", "<\\/")

    categories = {
        "code_to_cat": code_to_cat or {},
        "order": cat_order or [],
    }
    cat_json = json.dumps(categories, ensure_ascii=False)

    html = _HTML_TEMPLATE.replace("__DATA_PLACEHOLDER__", data_json)
    html = html.replace("__CATEGORIES_PLACEHOLDER__", cat_json)
    return html


class _Handler(BaseHTTPRequestHandler):
    page_html = ""

    def do_GET(self):
        self.close_connection = True
        try:
            self._handle()
        except Exception as e:
            # Never leave the client hanging — always send a response
            try:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                error_body = json.dumps(
                    {"status": "error", "reasons": [f"Server error: {e}"]},
                    ensure_ascii=False,
                )
                self.wfile.write(error_body.encode("utf-8"))
            except Exception:
                pass

    def _handle(self):
        path = urlparse(self.path).path
        if path == "/" or path == "":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(_Handler.page_html.encode("utf-8"))
        elif path == "/data":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(_get_holdings_json().encode("utf-8"))
        elif path == "/health":
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
        elif path == "/news":
            qs = parse_qs(urlparse(self.path).query)
            raw_code = qs.get("code", [""])[0]
            market = _resolve_market(raw_code)
            sina = _to_sina_code(raw_code, market)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(get_news_json(sina).encode("utf-8"))
        elif path == "/hotspot":
            qs = parse_qs(urlparse(self.path).query)
            raw_code = qs.get("code", [""])[0]
            stock_name = qs.get("name", [""])[0]
            market = _resolve_market(raw_code)
            sina = _to_sina_code(raw_code, market)
            position = _find_position(sina)
            # Run hotspot analysis in a background thread to avoid blocking the
            # HTTP handler (LLM calls can take 90+ seconds). Return cached data
            # immediately if available, otherwise a "processing" placeholder.
            with _hotspot_lock:
                cached = _hotspot_cache.get(sina)
            if cached:
                # Serve cached result instantly — no blocking at all
                result = cached
            else:
                # No cache yet: start a background fetch and return placeholder
                result = {
                    "status": "processing",
                    "code": sina,
                    "name": stock_name,
                    "recommendation": "分析中...",
                    "action": "wait",
                    "confidence": "低",
                    "score": 0,
                    "summary": "正在获取市场数据和AI分析，请稍后再次点击...",
                    "reasons": ["后台分析进行中"],
                    "risks": [],
                    "sentiment_label": "neutral",
                    "sentiment_score": 0,
                    "total_mentions": 0,
                    "news": [],
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
                def _fetch_in_background():
                    try:
                        r = market_intel.get_or_fetch_hotspot(
                            sina, stock_name, _code_to_cat_cache, position)
                        with _hotspot_lock:
                            _hotspot_cache[sina] = r
                    except Exception:
                        pass
                threading.Thread(target=_fetch_in_background, daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        elif path == "/sentiment":
            sentiment = market_intel.get_market_sentiment()
            # Merge portfolio concentration risk when holdings available
            with _holdings_lock:
                if _holdings_data and _holdings_data.get("positions"):
                    risk = market_intel.compute_portfolio_risk(
                        dict(_holdings_data), _code_to_cat_cache)
                    sentiment["concentration"] = risk
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(sentiment, ensure_ascii=False).encode("utf-8"))
        elif path == "/sector-sentiment":
            sector_data = market_intel.get_sector_sentiment(
                _code_to_cat_cache, _cat_order_cache)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(json.dumps(sector_data, ensure_ascii=False).encode("utf-8"))
        elif path == "/shutdown":
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b"ok")
            # Shutdown the server in a separate thread to avoid deadlock
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress HTTP log noise


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def _try_shutdown_old(port):
    """Send /shutdown to any existing server on `port`, then wait for it to die.
    Only attempts shutdown if port is confirmed in use first."""
    # Check if port is actually in use before attempting shutdown.
    # Prevents urllib connection attempt from disrupting subsequent bind() on Windows.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        result = s.connect_ex(("127.0.0.1", port))
        s.close()
        if result != 0:
            return  # Port not in use — nothing to shut down
    except Exception:
        pass

    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/shutdown", method="GET"
        )
        urllib.request.urlopen(req, timeout=2)
        time.sleep(0.5)
    except Exception:
        pass


def launch_account_page(holdings_data, code_to_cat=None, cat_order=None, open_browser=True):
    """Start a local HTTP server and open the account page in the browser.

    Args:
        holdings_data: Dict with keys: total_value, total_daily_pnl, positions
        code_to_cat: Dict mapping stock code → category name
        cat_order: List of category names in display order
        open_browser: Whether to auto-open the default browser

    Returns:
        HTTPServer instance (call server.shutdown() to stop)
    """
    import copy
    page_data = copy.deepcopy(holdings_data)
    set_holdings_data(page_data)
    _Handler.page_html = _generate_page(page_data, code_to_cat, cat_order)

    _try_shutdown_old(_FIXED_PORT)

    host_ip = _get_lan_ip()
    server = _ThreadingHTTPServer(("0.0.0.0", _FIXED_PORT), _Handler)
    server._url = f"http://{host_ip}:{_FIXED_PORT}"
    server._local_url = f"http://127.0.0.1:{_FIXED_PORT}"

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print(f"[account_page] 账户页面已启动: {server._local_url} (局域网: {server._url})")

    if open_browser:
        time.sleep(0.3)
        webbrowser.open_new_tab(server._local_url)

    return server


def start_tunnel(port, cloudflared_path=None):
    """Start cloudflared tunnel and return the public trycloudflare.com URL.

    Args:
        port: Local port to expose
        cloudflared_path: Path to cloudflared binary (default: ~/bin/cloudflared.exe)

    Returns:
        (public_url, process) or (None, None) on failure
    """
    if cloudflared_path is None:
        cloudflared_path = os.path.expandvars(r"%USERPROFILE%\bin\cloudflared.exe")

    if not os.path.exists(cloudflared_path):
        print(f"[tunnel] cloudflared 未找到: {cloudflared_path}", file=sys.stderr)
        return None, None

    print(f"[tunnel] 启动 Cloudflare Tunnel (端口 {port})...")
    proc = subprocess.Popen(
        [cloudflared_path, "tunnel", "--url", f"http://localhost:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )

    url = None
    deadline = time.time() + 30
    try:
        for line in proc.stdout:
            line = line.rstrip()
            if "trycloudflare.com" in line:
                m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if m:
                    url = m.group(0)
                    break
            if time.time() > deadline:
                break
    except Exception:
        pass

    if url:
        print(f"[tunnel] 公网地址: {url}")
        # Drain remaining stdout in a daemon thread to prevent pipe buffer
        # from filling up and blocking the cloudflared process.
        def _drain():
            try:
                for _ in proc.stdout:
                    pass
            except Exception:
                pass
        threading.Thread(target=_drain, daemon=True).start()
        return url, proc
    else:
        print("[tunnel] 未能获取公网地址", file=sys.stderr)
        try:
            proc.kill()
        except Exception:
            pass
        return None, None
