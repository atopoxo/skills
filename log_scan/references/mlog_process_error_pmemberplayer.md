# MLogProcessError: pMemberPlayer 为空

## 特征模式

```
[slot=MLogProcessError, attr=ProcessError, condition=pMemberPlayer, line=27699]
func=void KPlayerServer::OnTeamSetFormationLeader(char*, size_t, int, int)
| pPlayer->m_dwID=<player_id>
```

## 涉及文件

- `Source/Common/SO3World/Src/KPlayerServer.cpp` line 27699
- 责任人: yesen (r348526)
- 代码:
  ```cpp
  pMemberPlayer = g_pSO3World->GetPlayer(pRequest->dwNewFormationLeaderID);
  KGMLOG_PROCESS_ERROR(pMemberPlayer, pPlayer->m_dwID);
  ```

## 典型原因

客户端传入的 `dwNewFormationLeaderID` 在服务端查询不到对应玩家对象（已离线或ID无效），导致 `g_pSO3World->GetPlayer()` 返回空指针。影响13个以上不同玩家ID，说明是通用性问题而非个别数据异常。

## 修复建议

1. 客户端在发送设置队长请求前验证目标玩家是否在线
2. 服务端可改为静默忽略（用 if + return 替代 MLogProcessError）
3. 增加日志记录无效的 `dwNewFormationLeaderID` 值以便追踪来源
