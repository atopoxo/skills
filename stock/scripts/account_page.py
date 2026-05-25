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
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_FIXED_PORT = 18080


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

    var html = '<div class="stock-card">';
    html += '<div class="stock-top">';
    html += '<div><div class="stock-name">' + p.name + '</div>';
    html += '<div class="stock-code">' + p.code + '</div></div>';
    html += '<div class="stock-pnl ' + pnlCls + '">' + fmtPnl(dailyPnlVal) + '</div>';
    html += '</div>';
    html += '<div class="stock-meta">';
    html += '<span>成本: ' + fmt(p.cost, 3) + '</span>';
    html += '<span>现价: ' + fmt(p.price, 3) + '</span>';
    html += '</div>';
    html += '<div class="stock-bottom">';
    html += '<div class="stock-meta">';
    html += '<div>持仓 <span>' + (p.shares || 0) + '</span>股';
    html += ' | 可用 <span>' + (p.available || 0) + '</span>股</div>';
    html += '</div>';
    html += '<div class="stock-value">市值: ' + fmtWan(p.market_value) + '</div>';
    html += '</div>';
    html += '<div style="font-size:11px;margin-top:4px;">';
    html += '累计盈亏 <span class="stock-pnl ' + tPnlCls + '">' + fmtPnl(totalPnlVal) + ' (' + fmtPnl(cumPnlPct) + '%)</span>';
    html += '</div>';
    html += '</div>';
    return html;
}

function render() {
    var d = DATA;
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
        listHtml += '<span class="cat-mv">' + fmtWan(catMv) + '</span>';
        listHtml += '<span class="cat-total-pnl ' + totalPnlCls + '">' + fmtWan(catTotalPnl, true) + '</span>';
        listHtml += '</div>';
        listHtml += '<div class="cat-right">';
        listHtml += '<span class="cat-daily-pnl ' + dailyPnlCls + '">' + fmtWan(catDailyPnl, true) + '</span>';
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
        listHtml += '<span class="cat-mv">' + fmtWan(oMv) + '</span>';
        listHtml += '<span class="cat-total-pnl ' + oTotalCls + '">' + fmtWan(oTotal, true) + '</span>';
        listHtml += '</div>';
        listHtml += '<div class="cat-right">';
        listHtml += '<span class="cat-daily-pnl ' + oDailyCls + '">' + fmtWan(oDaily, true) + '</span>';
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

render();
</script>
</body>
</html>"""


def _generate_page(holdings_data, code_to_cat=None, cat_order=None):
    """Generate HTML page with holdings and category data embedded."""
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
        path = urlparse(self.path).path
        if path == "/" or path == "":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(_Handler.page_html.encode("utf-8"))
        elif path == "/health":
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
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


class _ReusableHTTPServer(HTTPServer):
    pass


def _try_shutdown_old(port):
    """Send /shutdown to any existing server on `port`, then wait for it to die."""
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/shutdown", method="GET"
        )
        urllib.request.urlopen(req, timeout=1)
        time.sleep(0.3)
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
    _Handler.page_html = _generate_page(holdings_data, code_to_cat, cat_order)

    _try_shutdown_old(_FIXED_PORT)

    host_ip = _get_lan_ip()
    server = _ReusableHTTPServer(("0.0.0.0", _FIXED_PORT), _Handler)
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
