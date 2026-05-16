# Can't Found Action — 未知动作类型

## 特征模式

```
Can't Found Action <action_id> by Character <character_id>
```

## 涉及文件

- `Source/Common/SO3World/Src/KCharacter.cpp:8602`
- 责任人: huaibin (r106530); wangtao4 (r154337, NPC角色查找)
- 代码:
  ```cpp
  pCharacterAction = g_pSO3World->m_Settings.m_CharacterActionList.GetAction(dwActionType);
  if (!pCharacterAction)
  {
      KGLogPrintf(KGLOG_ERR, "Can't Found Action %u by Character %u", dwActionType, dwCharacterID);
      goto Exit0;
  }
  ```

## 典型原因

`KCharacter::Action()` 函数在执行角色动作时，从 `CharacterActionList` 配置表中查找对应动作类型失败。可能原因：

1. 策划配置遗漏 — Action ID 在 CharacterActionList 表中未定义
2. 版本不匹配 — 客户端请求了新版Action但服务端配置未更新
3. NPC配置错误 — NPC引用了不存在的Action类型
4. 数据异常 — dwActionType 被错误传入（如未初始化、内存越界）

## 已发现实例

| Action ID | Character ID | 频率 | 备注 |
|-----------|-------------|------|------|
| 57 | 1074706881 | 2次 | NPC，未知动作 |
| 68 | 1074706881 | 1次 | NPC，未知动作 |

Character 1074706881 为 NPC 类型，同一NPC连续请求多个未注册动作，可能是该NPC配置表中脚本引用了未定义的Action。

## 修复建议

1. 检查 Character 1074706881 对应NPC的策划配置，确认其脚本/行为引用的Action 57/68是否已定义
2. 在 GetAction 失败时可降级为默认动作（如 Action 0 表示中断动作），避免仅报错后中断
3. 增加更详细的日志输出（NPC模板ID、所在场景等）以便排查
