# Buff 不存在及来源为空

## 特征模式

### 模式1: BuffNotExist

```
[slot=Buff, attr=BuffNotExist, buff_id=<id>, buff_lv=<lv>] in KBuffList::CallBuff
```

### 模式2: pOriginBuff 为空

```
KGLOG_PROCESS_ERROR(pOriginBuff) at line 641 in KBuffList::CallBuff
```

## 涉及文件

- `Source/Common/SO3World/Src/KBuffList.cpp` line 641
- 责任人: 待确认

## 典型原因

1. Buff ID/等级组合在 Buff 配置表中不存在（配置删除或ID变更）
2. 技能/道具/脚本配置引用了不存在的 Buff
3. Buff 等级超出该 Buff 定义的等级范围
4. 链式 Buff 调用时源 Buff 在调用前已被移除/过期

模式1和模式2常在同一次 CallBuff 调用中成对出现：源 Buff 配置缺失导致 pOriginBuff 为空。

## 已发现实例

| Buff ID | Buff LV | 频率 | 备注 |
|---------|---------|------|------|
| 562 | 49 | 1次 | BuffNotExist |

## 修复建议

1. 检查 Buff 配置表中是否存在问题 Buff 的 ID/等级定义，修复引用方配置
2. CallBuff 中增加详细参数日志（触发来源技能ID/角色ID），便于定位
3. 检查源 Buff 的创建和生命周期管理，确保链式调用时源 Buff 不会被提前释放
