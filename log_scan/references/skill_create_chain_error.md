# 技能创建与链子技能错误

## 特征模式

### 模式1: CreateSkill 参数全零

```
[KSkill] CreateSkill(0:0) not found from skill's table. [<line>]
```

### 模式2: ApplyOnChain 子技能不存在

```
[ApplyOnChain] pSubSkill not exist, skill:(<id>, <lv>), sub:<index> [<line>]
```

## 涉及文件

- 技能系统文件（预估 `Source/Common/SO3World/Src/KSkill.cpp`）
- 行号 [1581] 和 [1582] 相邻，可能在同一源文件中

## 典型原因

### CreateSkill(0:0)
- skillID=0 表示未初始化或默认值，上游调用路径未正确设置技能 ID
- 技能释放流程中技能 ID 传递丢失或被覆盖
- 网络包中技能字段解析异常

### ApplyOnChain pSubSkill 不存在
- 技能 ChainSkill 配置表引用的子技能 ID 未被定义或已被删除
- 策划填写链数据时填写了错误的子技能 ID
- 子技能有等级/条件限制导致查询失败

## 已发现实例

| 模式 | 技能ID | 技能等级 | 子技能索引 | 频率 |
|------|--------|---------|-----------|------|
| CreateSkill(0:0) | 0 | 0 | - | 1次 |
| pSubSkill not exist | 30854 | 1 | 0 | 1次 |

## 修复建议

1. CreateSkill 入口增加参数校验：skillID==0 时记录调用栈后返回 NULL
2. 检查技能 30854 的 ChainSkill 配置，确认 sub index=0 的子技能 ID 是否存在
3. 在 ApplyOnChain 中 pSubSkill 为空时输出子技能 ID 日志
4. 策划工具增加链技能引用完整性校验
