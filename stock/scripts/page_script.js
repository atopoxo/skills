
const DATA = {"total_value": 1520065.49, "total_daily_pnl": 2175.44, "positions": [{"code": "000868", "name": "安凯客车", "shares": 1300, "available": 1300, "cost": 8.651, "price": 3.9, "market_value": 5070.0, "daily_pnl": -26.0, "total_pnl": -6175.66, "pnl_pct": -54.9185, "account_type": "账户0"}, {"code": "002996", "name": "顺博合金", "shares": 650, "available": 650, "cost": 15.48, "price": 7.05, "market_value": 4582.5, "daily_pnl": 97.5, "total_pnl": -5479.33, "pnl_pct": -54.4574, "account_type": "账户0"}, {"code": "159326", "name": "电网设备", "shares": 44000, "available": 44000, "cost": 1.96, "price": 2.065, "market_value": 90860.0, "daily_pnl": 880.0, "total_pnl": 4621.79, "pnl_pct": 5.3571, "account_type": "账户0"}, {"code": "159599", "name": "芯片指数", "shares": 92000, "available": 92000, "cost": 2.178, "price": 3.161, "market_value": 290812.0, "daily_pnl": 1288.0, "total_pnl": 90411.9, "pnl_pct": 45.1331, "account_type": "账户0"}, {"code": "159819", "name": "AI智能", "shares": 54000, "available": 54000, "cost": 1.572, "price": 2.041, "market_value": 110214.0, "daily_pnl": 1890.0, "total_pnl": 25352.1, "pnl_pct": 29.834600000000002, "account_type": "账户0"}, {"code": "300442", "name": "润泽科技", "shares": 2000, "available": 2000, "cost": 89.53, "price": 86.67, "market_value": 173340.0, "daily_pnl": 4400.0, "total_pnl": -5720.0, "pnl_pct": -3.1945, "account_type": "账户0"}, {"code": "300568", "name": "星源材质", "shares": 300, "available": 300, "cost": 25.731, "price": 17.01, "market_value": 5103.0, "daily_pnl": -12.0, "total_pnl": -2616.16, "pnl_pct": -33.893, "account_type": "账户0"}, {"code": "518600", "name": "上海金", "shares": 14700, "available": 14700, "cost": 10.345, "price": 9.51, "market_value": 139797.0, "daily_pnl": -3329.15, "total_pnl": -12278.41, "pnl_pct": -8.0715, "account_type": "账户0"}, {"code": "600120", "name": "浙江东方", "shares": 4500, "available": 4500, "cost": 7.348, "price": 4.89, "market_value": 22005.0, "daily_pnl": -360.0, "total_pnl": -11059.83, "pnl_pct": -33.4513, "account_type": "账户0"}, {"code": "600956", "name": "新天绿能", "shares": 200, "available": 200, "cost": 165.222, "price": 9.08, "market_value": 1816.0, "daily_pnl": 112.0, "total_pnl": -31228.32, "pnl_pct": -94.5044, "account_type": "账户0"}, {"code": "603993", "name": "洛阳钼业", "shares": 3100, "available": 3100, "cost": 22.401, "price": 18.83, "market_value": 58373.0, "daily_pnl": -1519.0, "total_pnl": -11071.07, "pnl_pct": -15.9413, "account_type": "账户0"}, {"code": "688008", "name": "澜起科技", "shares": 1200, "available": 1200, "cost": 170.653, "price": 261.22, "market_value": 313464.0, "daily_pnl": -5136.0, "total_pnl": 108680.49, "pnl_pct": 53.0709, "account_type": "账户0"}, {"code": "688270", "name": "ST臻镭", "shares": 807, "available": 807, "cost": 182.734, "price": 129.98, "market_value": 104893.86, "daily_pnl": 992.61, "total_pnl": -42572.35, "pnl_pct": -28.8693, "account_type": "账户0"}, {"code": "00981", "name": "中芯国际", "shares": 1500, "available": 1500, "cost": 61.911, "price": 76.703, "market_value": 115054.34, "daily_pnl": 4352.71, "total_pnl": 22188.55, "pnl_pct": 23.8924, "account_type": "账户0"}, {"code": "09988", "name": "阿里巴巴", "shares": 800, "available": 800, "cost": 139.231, "price": 105.851, "market_value": 84680.69, "daily_pnl": -1455.23, "total_pnl": -26703.89, "pnl_pct": -23.974500000000003, "account_type": "账户0"}]};
const CATEGORIES = {"code_to_cat": {"688008": "AI硬件", "159599": "AI硬件", "300442": "AI硬件", "159819": "AI硬件", "00981": "AI硬件", "159326": "AI硬件", "09988": "AI应用", "600120": "AI应用", "688270": "商业航天", "518600": "黄金", "603993": "战争金属"}, "order": ["AI硬件", "AI应用", "商业航天", "黄金", "战争金属"]};

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

    var html = '<div class="stock-card">';
    html += '<div class="stock-top">';
    html += '<div><div class="stock-name">' + p.name;
    html += '<button class="news-btn" data-code="' + p.code + '" data-name="' + p.name + '" onclick="event.stopPropagation();var e=this;openNews(e.dataset.code,e.dataset.name)">建议</button>';
    html += '</div>';
    html += '<div class="stock-code">' + p.code + '</div></div>';
    html += '<div class="stock-pnl ' + pnlCls + '">' + fmtPnl(dailyPnlVal) + ' (' + fmtPnl(dailyPnlPct) + '%)</div>';
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

function render(data) {
    var d = data || DATA;
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
    fetch('/hotspot?code=' + encodeURIComponent(code) + '&name=' + encodeURIComponent(name)).then(function(r) {
        return r.json();
    }).then(function(data) {
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
                html += '<div class="news-item" onclick="window.open('' + newsUrl + '', '_blank')" style="cursor:pointer;">';
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
    }).catch(function() {
        document.getElementById('newsModalBody').innerHTML = '<div class="news-empty">加载失败，请稍后重试</div>';
    });
}
function closeNews() {
    document.getElementById('newsModal').classList.add('hidden');
}

render();

// Poll for real-time updates every 1 second
setInterval(function() {
    fetch('/data').then(function(r) { return r.json(); }).then(render).catch(function(){});
}, 1000);
