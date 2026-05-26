---
name: stock-monitor
description: 从东方财富读取持仓，1秒级实时监控持仓股票价格异动（涨跌>=0.5%/30s），支持控制台+飞书双通道报警。
type: skill
---

# Stock Monitor — 股票异动监控

从东方财富证券账户读取持仓，每秒刷新价格，当股票在 30 秒内涨跌幅超过阈值（默认 0.5%）时，通过控制台和飞书机器人双通道报警。

## 功能

1. **快速登录**: Cookie 缓存命中 ~1s；过期自动启动 headless 浏览器 + OCR 验证码 ~15s
2. **自动读取持仓**: 直接从东方财富持仓 API 获取当前持仓
3. **1秒级实时监控**: 每秒轮询新浪行情接口获取最新价格
4. **30秒滚动窗口**: 对比当前价与 30 秒前价格，变动幅度 >= 0.5% 触发报警
5. **双通道报警**: 控制台格式化输出 + 飞书机器人推送
6. **冷却机制**: 同只股票 300 秒内不重复报警

## 快速开始

### 1. 生成配置文件

```bash
python scripts/main.py --init-config
```

### 2. 编辑配置

编辑 `scripts/config.json`，填写东方财富账号、飞书配置：

```json
{
  "eastmoney": {
    "login_mode": "manual",
    "account": "你的资金账号",
    "password": "交易密码",
    "cookies": ""
  },
  "feishu": {
    "enabled": true,
    "mode": "app",
    "app_id": "cli_xxx",
    "app_secret": "xxx"
  },
  "fallback_stocks": [
    {"code": "sh688008", "name": "澜起科技", "market": "sh"}
  ]
}
```

首次运行时 `cookies` 留空，脚本会自动启动 headless 浏览器登录并保存 Cookie。

### 3. 启动监控

```bash
# 通过 stock.exe 启动（任务管理器显示为 stock.exe）
scripts/stock.exe scripts/main.py

# 多实例时用 --id 区分
scripts/stock.exe scripts/main.py --id 2

# 正常模式（Cookie缓存优先，极速启动）
scripts/stock.exe scripts/main.py

# 强制重新浏览器登录（忽略缓存Cookie）
scripts/stock.exe scripts/main.py --relogin

# 单次检查
scripts/stock.exe scripts/main.py --check

# 测试飞书
scripts/stock.exe scripts/main.py --test-feishu
```

## 登录流程（两级加速）

| 路径 | 耗时 | 说明 |
|------|------|------|
| Cookie 缓存 | ~1s | 直接调用持仓 API，命中率最高 |
| 浏览器登录 | ~15s | 非 headless Chromium + ddddocr 识别验证码，获取完整 Cookie（含 HttpOnly） |

Cookie 在浏览器登录成功后自动写入 `config.json`，有效期内后续启动均为 ~1s。

## 配置说明

### config.json

`scripts/config.json` 主要字段：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `eastmoney.account` | `""` | 东方财富交易账号 |
| `eastmoney.password` | `""` | 东方财富交易密码 |
| `eastmoney.cookies` | `""` | 登录后保存的 Cookie（自动更新） |
| `alert.threshold_pct` | `0.5` | 报警阈值百分比 |
| `alert.window_seconds` | `30` | 滚动窗口秒数 |
| `alert.poll_interval_seconds` | `1` | 轮询间隔秒数 |
| `alert.cooldown_seconds` | `300` | 同股票报警冷却秒数 |
| `feishu.enabled` | `false` | 是否启用飞书报警 |
| `feishu.mode` | `"app"` | 飞书接入模式：`"webhook"` 或 `"app"` |
| `feishu.app_id` | `""` | App 模式应用 ID |
| `feishu.app_secret` | `""` | App 模式应用 Secret |
| `feishu.receive_id` | `""` | 接收者 open_id / chat_id |
| `feishu.receive_id_type` | `"open_id"` | 接收者类型 |
| `console_alert.enabled` | `true` | 是否启用控制台报警 |

### custom.ini — 股票分类

`scripts/custom.ini` 定义股票分类，格式：

```ini
[AI硬件]
stocks = sh688008,sh000063,sh688981

[芯片]
stocks = sh688981,sz159599

[新能源]
stocks =

[其它]
# 未归入任何分类的股票自动归入此分类
```

- 每个 `[分类名]` 下的 `stocks` 填写属于该分类的新浪股票代码（逗号分隔）
- 新浪代码格式：`sh`/`sz` + 6位数字，如 `sh688008`
- 未归入任何分类的股票自动归入 `其它`
- 分类的展示顺序与文件中的顺序一致

## 报警示例

**实时异动报警** (30s窗口触发，>=0.5%):

```
==================================================
  ALERT  2026-05-22 14:33:15  📈 上涨
--------------------------------------------------
  澜起科技 (sh688008)
  30s前: 271.50  →  当前: 272.83
  变动: +0.49%
==================================================
```

## 文件结构

```
scripts/
├── main.py              入口脚本，串联全流程
├── login.py              快速登录（Cookie缓存 + headless浏览器 + OCR）
├── config.json            配置文件（gitignore）
├── config.py              配置加载与校验
├── custom.ini             股票分类配置
├── eastmoney_auth.py      会话管理（向后兼容）
├── eastmoney_holdings.py  持仓查询（向后兼容）
├── price_fetcher.py       新浪行情获取（1秒轮询）
├── monitor.py             监控主循环、滚动窗口、分类汇总
├── alert.py               双通道报警调度（控制台+飞书，分类格式）
└── stock_monitor.py       旧版脚本（保留兼容）
```

## 数据来源

- 持仓数据: 东方财富证券交易平台 (jywg.eastmoney.com)
- 实时价格: 新浪财经行情接口 (hq.sinajs.cn)
