# AcceptC2SRemoteLuaCall 未匹配报错

## 特征模式

```
[AcceptC2SRemoteLuaCall] Function: <func_name>, <player_id>
```

## 已发现的高频函数

| 函数 | 频率 | 责任人 | 文件 |
|------|------|--------|------|
| `On_LangKeXing_ConfirmMap` | 极高 | lihongjie (r763512) | `client/scripts/RemoteFromClient/On_LangKeXing.lua:192` |
| `On_UIMovie_EscEvent` | 低 | 待确认 | `client/scripts/RemoteFromClient/On_UIMovie.lua` |

## 典型原因

这些Lua远程调用属于正常游戏行为，函数内部有多层检查（如 `Tool_IsLeader`、`IsLangKeXingMap` 等），检查失败会静默return，不会产生显式错误。但由于未被 log_extract 的匹配规则覆盖，被归入 "else" 类别。

## 处理建议

1. 在 `scripts/src/skills/log_extract/` 中更新匹配规则，将已知安全的远程调用函数加入**白名单**
2. 白名单函数列表：
   - `On_LangKeXing_ConfirmMap` — 浪客行确认地图（正常交互）
   - `On_UIMovie_EscEvent` — UI动画ESC事件（正常交互）
3. 新增函数时先分析是否属于正常行为再决定加入白名单
