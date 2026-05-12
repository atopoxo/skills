# KGLOG_PROCESS_ERROR 常见模式

## 模式1: KScene::CreateNpc 失败

```
KGLOG_PROCESS_ERROR(bRetCode) at line 5989 in KNpc* KScene::CreateNpc(...)
```

- **文件**: `Source/Common/SO3World/Src/KScene.cpp`
- **责任人**: linjiaqi (r100568)
- **代码**: `bRetCode = g_pSO3World->AddNpc(pNpc, this, nX, nY, nZ);`
- **原因**: AddNpc返回失败 — NPC ID冲突、场景NPC数量上限、NPC资源未正确加载
- **建议**: 增加AddNpc失败时的详细上下文日志（NPC ID、坐标、场景名），排查重复创建

## 模式2: ProcessSkillAdaptiveDamage 非玩家目标

```
KGLOG_PROCESS_ERROR(IS_PLAYER(pDstCharacter->m_dwID)) at line 3473 in ProcessSkillAdaptiveDamage
KGLOG_PROCESS_ERROR(IS_PLAYER(pDstCharacter->m_dwID)) at line 3523 in ProcessSkillAdaptiveDamageRand
```

- **文件**: `Source/Common/SO3World/Src/KAttrModifier.cpp`
- **责任人**: yechuan (r331186)
- **代码**: `if (!IS_PLAYER(pDstCharacter->m_dwID)) pDstCharacter->PrintAttrExtraInfo(__FUNCTION__);` 后仍报错
- **原因**: 自适应伤害函数被传入NPC作为目标，该类伤害仅对玩家有效
- **建议**: 上游调用处增加IS_PLAYER判断，或PrintAttrExtraInfo后改为return而非报错

## 模式3: KG_AsyncSocketStream::Recv 缓冲区溢出

```
KGLOG_PROCESS_ERROR(uPackSize <= m_uRecvBufferSize) at line 3374 in KG_AsyncSocketStream::Recv(...)
```

- **文件**: KG_AsyncSocketStream（`Include/Common/KG_Socket.h` 预估，具体实现可能在预编译库中）
- **原因**: 接收到的数据包大小超过缓冲区大小
- **建议**: 检查缓冲区配置，排查异常客户端大包

## 模式4: CastSkill eTargetType=0 无效目标

```
[slot=MLogProcessError, condition=eTargetType == ttNoTarget || ..., line=3016]
func=int KCharacter::CastSkill(...) | dwSkillID=45191, dwSkillLevel=1, eTargetType=0
```

- **文件**: `Source/Common/SO3World/Src/KCharacter.cpp`
- **责任人**: longjingyu (r285443, 条件), yechuan (r284091, 宏)
- **原因**: eTargetType=0是未初始化的默认值或上游传参错误
- **建议**: 追踪技能45191的配置，在CastSkill入口增加对eTargetType=0的防御性处理
