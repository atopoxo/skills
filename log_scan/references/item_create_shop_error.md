# 物品创建与商店配置错误

## 特征模式

### 模式1: KGItemHouse::CreateItem 物品信息为空

```
KGLOG_PROCESS_ERROR(pItemInfo) at line 131 in virtual IItem* KGItemHouse::CreateItem(DWORD, DWORD, time_t, DWORD, DWORD, int)
```

### 模式2: Shop 模板无效物品

```
[Shop] Shop template ID <id>, invalid item (nType = <type>, nIndex = <index>, dwRandomSeed = <seed>) !
```

## 涉及文件

- `Source/Common/SO3World/Src/KGItemHouse.cpp:131`
- 商店系统文件（待确认）

## 典型原因

### pItemInfo 为空
- CreateItem 的前两个 DWORD 参数 (nType, nIndex) 组合在物品配置表中不存在
- 客户端缓存了已删除的物品数据
- Lua 脚本或任务配置引用不存在的物品 ID

### Shop 模板无效物品
- 商店模板配置了已移除或未定义的物品
- 随机商店物品池配置错误，随机到不存在的物品
- 物品表版本更新后商店模板未同步更新
- dwRandomSeed=0 说明随机种子未正确设置

## 已发现实例

| 模式 | 参数 | 频率 |
|------|------|------|
| pItemInfo | 待确认 | 1次 |
| Shop invalid item | template=1365, nType=10, nIndex=2158, seed=0 | 1次 |

## 修复建议

1. KGMLOG_PROCESS_ERROR 前打印 CreateItem 入参 (nType, nIndex)，便于定位无效物品 ID
2. 检查商店模板 1365 配置，修复无效物品引用
3. 商店模板加载时增加物品有效性校验
