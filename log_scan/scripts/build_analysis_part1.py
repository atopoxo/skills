#!/usr/bin/env python
"""Generate temporary_else_analysis.json from temporary_else data and reference docs."""
import json
import os

OUTPUT_DIR = r"Y:\AI\skills\log_scan\scripts\.results\final_result_2026_05_16_11_33_04"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "temporary_else_analysis.json")

output = {
    "tab_load": [],
    "lua_call": [],
    "lua": [],
    "c/c++": []
}

# ===================================================================
# LUA entries
# ===================================================================

# 1. On_LangKeXing_ConfirmMap - aggregated 81 counts
output["lua"].append({
    "source": "llm",
    "reference_doc": "references/lua_remote_call_unmatched.md",
    "count": 81,
    "encoding": "GBK",
    "file_path": "z:/trunk/client/scripts/RemoteFromClient/On_LangKeXing.lua",
    "line_num": 192,
    "select_content": "function On_LangKeXing_ConfirmMap(...) -- Tool_IsLeader / IsLangKeXingMap 多层安全校验",
    "error": "[AcceptC2SRemoteLuaCall] Function: On_LangKeXing_ConfirmMap — 浪客行确认地图远程调用，正常游戏交互行为",
    "reference": "On_LangKeXing_ConfirmMap 内部包含 Tool_IsLeader/IsLangKeXingMap 等安全检查，失败静默return。未被 log_extract 白名单覆盖而归入 else。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "AcceptC2SRemoteLuaCall 远程调用 On_LangKeXing_ConfirmMap 函数。此为浪客行系统确认地图的客户端→服务端远程调用，"
        "属于正常游戏交互行为。函数内部有多层安全检查（Tool_IsLeader 验证队长身份、IsLangKeXingMap 验证地图类型），"
        "任一检查失败均静默 return，不会产生实际错误。归入 temporary_else 是因 log_extract 的匹配规则未覆盖此函数名，"
        "并非真正代码缺陷。\n\n"
        "**影响范围：** 无实际影响，仅产生日志噪音。81次调用分布在多个时间段（SO3GameServer_2026_05_10 多个日志文件），"
        "为玩家频繁触发浪客行地图确认的正常行为。\n\n"
        "**修复建议：** 在 scripts/src/skills/log_extract/ 的匹配规则中将 On_LangKeXing_ConfirmMap 加入安全函数白名单，"
        "后续运行自动过滤此类正常调用。"
    ),
    "wrecker_info": [{
        "author": "lihongjie", "revision": "r763512",
        "description": "浪客行系统 - 确认地图功能实现",
        "principal": ["lihongjie"], "type": "added",
        "old": None, "new": "function On_LangKeXing_ConfirmMap",
        "old_line": None, "new_line": 192
    }],
    "wrecker_index": 0
})

# 2. On_UIMovie_EscEvent - 1 count
output["lua"].append({
    "source": "llm",
    "reference_doc": "references/lua_remote_call_unmatched.md",
    "count": 1,
    "encoding": "GBK",
    "file_path": "z:/trunk/client/scripts/RemoteFromClient/On_UIMovie.lua",
    "line_num": 0,
    "select_content": "function On_UIMovie_EscEvent(...) -- UI动画ESC跳过事件处理",
    "error": "[AcceptC2SRemoteLuaCall] Function: On_UIMovie_EscEvent, 972777519516867900 — UI动画ESC事件远程调用",
    "reference": "On_UIMovie_EscEvent 处理UI动画播放中玩家按ESC跳过动画的事件，正常交互行为。未被 log_extract 白名单覆盖而归入 else。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "AcceptC2SRemoteLuaCall 远程调用 On_UIMovie_EscEvent 函数。该函数处理UI动画播放过程中玩家按ESC跳过动画的事件，"
        "属于正常游戏交互行为。函数内部处理跳过请求并清理动画状态，不产生实际错误。\n\n"
        "**影响范围：** 无实际影响，仅日志噪音。\n\n"
        "**修复建议：** 在 scripts/src/skills/log_extract/ 的匹配规则中将 On_UIMovie_EscEvent 加入安全函数白名单。"
    ),
    "wrecker_info": [{
        "author": "unknown", "revision": "unknown",
        "description": "无法定位责任人", "principal": [],
        "type": "modify", "old": None, "new": None,
        "old_line": None, "new_line": None
    }],
    "wrecker_index": -1
})

# ===================================================================
# C/C++ entries
# ===================================================================
cc = output["c/c++"]

# --- Entry 1: KScene::CreateNpc ---
cc.append({
    "source": "llm",
    "reference_doc": "references/kglog_process_error_common.md",
    "count": 8,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KScene.cpp",
    "line_num": 5989,
    "select_content": "bRetCode = g_pSO3World->AddNpc(pNpc, this, nX, nY, nZ);\nKGLOG_PROCESS_ERROR(bRetCode);",
    "error": "KGLOG_PROCESS_ERROR(bRetCode) at line 5989 in KNpc* KScene::CreateNpc(unsigned int, int, int, int, int, int, BOOL, const char*, unsigned int, BOOL, int, int)",
    "reference": "bRetCode = g_pSO3World->AddNpc(pNpc, this, nX, nY, nZ); KGLOG_PROCESS_ERROR(bRetCode);",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "KScene::CreateNpc 内部调用 g_pSO3World->AddNpc 失败触发 KGLOG_PROCESS_ERROR。"
        "CreateNpc 负责在场景中创建 NPC 对象，AddNpc 将 NPC 注册到 SO3World 管理结构中。\n\n"
        "**可能原因：**\n"
        "1. NPC ID 冲突 — 场景中已存在相同 ID 的 NPC，AddNpc 检测到重复后返回失败\n"
        "2. 场景 NPC 数量达到上限 — 场景可容纳 NPC 总数已满\n"
        "3. NPC 模板数据加载失败或配置条目不存在\n"
        "4. 场景对象状态异常（已标记销毁或不可用）\n\n"
        "**影响范围：** 8次报错分布在多个时间段，间歇性问题。对应 NPC 创建失败影响相关玩法（任务NPC不出现、怪物不刷新等）。\n\n"
        "**修复建议：**\n"
        "1. 在 AddNpc 失败时增加详细上下文日志（NPC ID、场景名、坐标），便于定位\n"
        "2. 排查是否有脚本或配置在短时间内重复请求创建同一 NPC\n"
        "3. 检查场景 NPC 容量配置\n"
        "4. 验证相关 NPC 模板数据在配置表中存在且完整"
    ),
    "wrecker_info": [{
        "author": "linjiaqi", "revision": "r100568",
        "description": "添加NPC创建流程 - g_pSO3World->AddNpc 调用",
        "principal": ["linjiaqi"], "type": "added",
        "old": None, "new": "bRetCode = g_pSO3World->AddNpc(pNpc, this, nX, nY, nZ);",
        "old_line": None, "new_line": 5988
    }],
    "wrecker_index": 0
})

# --- Entry 2: KG_AsyncSocketStream::Recv buffer overflow ---
cc.append({
    "source": "llm",
    "reference_doc": "references/kglog_process_error_common.md",
    "count": 4,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Include/Common/KG_Socket.h",
    "line_num": 3374,
    "select_content": "KGLOG_PROCESS_ERROR(uPackSize <= m_uRecvBufferSize); // 接收缓冲区大小检查",
    "error": "KGLOG_PROCESS_ERROR(uPackSize <= m_uRecvBufferSize) at line 3374 in virtual int KG_AsyncSocketStream::Recv(IKG_Buffer**)",
    "reference": "KG_AsyncSocketStream::Recv 接收数据包时检查包大小是否超过接收缓冲区大小。KG_AsyncSocketStream 可能位于预编译库。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "KG_AsyncSocketStream::Recv 在接收网络数据包时，数据包大小 uPackSize 超过了接收缓冲区大小 m_uRecvBufferSize，"
        "触发 KGLOG_PROCESS_ERROR 告警。\n\n"
        "**可能原因：**\n"
        "1. 缓冲区配置过小 — m_uRecvBufferSize 不足以容纳某些合法最大数据包\n"
        "2. 异常客户端大包 — 客户端发送了异常大小的数据包（协议版本不匹配或恶意构造）\n"
        "3. 数据包解析错误 — 包大小字段被错误解析导致 uPackSize 值异常\n"
        "4. TCP 粘包/拆包处理异常 — 流式传输中包边界判断出错\n\n"
        "**影响范围：** 4次报错，涉及网络 I/O 层。可能导致对应连接的数据接收中断。\n\n"
        "**修复建议：**\n"
        "1. 检查 m_uRecvBufferSize 配置值与协议最大包大小是否匹配\n"
        "2. 排查异常客户端：记录触发错误的客户端 IP/PlayerID\n"
        "3. 增加异常包 dump 日志（包大小、缓冲区大小、连接信息）以便排查"
    ),
    "wrecker_info": [{
        "author": "unknown", "revision": "unknown",
        "description": "KG_AsyncSocketStream 可能位于预编译库中，无法通过 SVN 追踪源码变更",
        "principal": [], "type": "modify",
        "old": None, "new": None,
        "old_line": None, "new_line": None
    }],
    "wrecker_index": -1
})

# --- Entry 3: [KG_Packer] FlushSend Failed ErrorCode 104 ---
cc.append({
    "source": "llm",
    "reference_doc": "references/kglog_process_error_common.md",
    "count": 1,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KPlayerServerThread.cpp",
    "line_num": 434,
    "select_content": "nRetCode = pConnection->SocketPacker.FlushSend(pConnection->piSocketStream, m_nNetWorkLoop);\nif (!nRetCode) { m_strLastError = \"Flush Send Error\"; goto Exit0; }",
    "error": "[KG_Packer] FlushSend Failed, ErrorCode: 104",
    "reference": "ErrorCode 104 = ECONNRESET，对端连接已重置。底层 RawSend 发送缓冲区数据时 socket 已断开。上层有相应断线处理逻辑。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "KG_Packer::FlushSend 发送缓冲区数据时失败，ErrorCode 104 即系统错误 ECONNRESET（Connection Reset by Peer），"
        "对端（客户端）连接已重置。底层 RawSend 尝试发送缓冲区数据时发现 socket 已断开，"
        "通常由客户端异常断线（崩溃、网络切换、超时等）导致。\n\n"
        "**影响范围：** 单次报错。上层已有相应的断线处理逻辑（if (!nRetCode) { goto Exit0; }），"
        "会正确释放连接资源并清理状态。此错误属于正常断线处理流程的一部分，不影响服务端稳定性。\n\n"
        "**修复建议：** 此错误属正常断线处理流程，无需特殊修复。若频繁出现可排查网络质量和客户端稳定性。"
        "可考虑降级为 WARNING 日志级别或静默处理以减少告警噪音。"
    ),
    "wrecker_info": [{
        "author": "yesen", "revision": "r345808",
        "description": "FlushSend 错误处理分支 - 断线重连流程",
        "principal": ["yesen"], "type": "modify",
        "old": None, "new": "nRetCode = pConnection->SocketPacker.FlushSend(...)",
        "old_line": None, "new_line": 434
    }],
    "wrecker_index": 0
})

# --- Entry 4: ProcessSkillAdaptiveDamage IS_PLAYER check ---
cc.append({
    "source": "llm",
    "reference_doc": "references/kglog_process_error_common.md",
    "count": 2,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KAttrModifier.cpp",
    "line_num": 3473,
    "select_content": "if (!IS_PLAYER(pDstCharacter->m_dwID)) pDstCharacter->PrintAttrExtraInfo(__FUNCTION__);",
    "error": "KGLOG_PROCESS_ERROR(IS_PLAYER(pDstCharacter->m_dwID)) at line 3473 in BOOL ProcessSkillAdaptiveDamage(KCharacter*, BOOL, int, int)",
    "reference": "ProcessSkillAdaptiveDamage（自适应伤害）要求目标必须是玩家。IS_PLAYER 检查失败说明目标为 NPC。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "ProcessSkillAdaptiveDamage（自适应伤害处理）函数要求目标必须是玩家角色。Line 3473 处 IS_PLAYER(pDstCharacter->m_dwID) "
        "检查失败，表明传入的目标是 NPC 而非玩家。自适应伤害机制仅针对玩家设计（根据玩家属性动态调整伤害），"
        "NPC 作为目标时逻辑不适用。\n\n"
        "**可能原因：**\n"
        "1. 上游调用处未对目标类型做区分，将 NPC 传入了自适应伤害流程\n"
        "2. 技能配置中对目标类型判断不严格\n"
        "3. PrintAttrExtraInfo 之后仍然触发 KGLOG_PROCESS_ERROR，说明仅打印信息未阻止后续报错\n\n"
        "**影响范围：** 2次报错，频率较低。不影响核心玩法但产生错误日志。\n\n"
        "**修复建议：**\n"
        "1. 上游调用处增加 IS_PLAYER 判断，仅对玩家目标调用 ProcessSkillAdaptiveDamage\n"
        "2. 或 PrintAttrExtraInfo 后改为 return false 而非继续报错，实现优雅降级\n"
        "3. 排查是哪些技能/场景触发了 NPC 作为自适应伤害目标"
    ),
    "wrecker_info": [{
        "author": "yechuan", "revision": "r331186",
        "description": "自适应伤害处理 - IS_PLAYER 宏检查",
        "principal": ["yechuan"], "type": "modify",
        "old": None, "new": "if (!IS_PLAYER(pDstCharacter->m_dwID)) pDstCharacter->PrintAttrExtraInfo(__FUNCTION__);",
        "old_line": None, "new_line": 3473
    }],
    "wrecker_index": 0
})

# --- Entry 5: ProcessSkillAdaptiveDamageRand IS_PLAYER check ---
cc.append({
    "source": "llm",
    "reference_doc": "references/kglog_process_error_common.md",
    "count": 2,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KAttrModifier.cpp",
    "line_num": 3523,
    "select_content": "if (!IS_PLAYER(pDstCharacter->m_dwID)) pDstCharacter->PrintAttrExtraInfo(__FUNCTION__);",
    "error": "KGLOG_PROCESS_ERROR(IS_PLAYER(pDstCharacter->m_dwID)) at line 3523 in BOOL ProcessSkillAdaptiveDamageRand(KCharacter*, BOOL, int, int)",
    "reference": "ProcessSkillAdaptiveDamageRand 是 ProcessSkillAdaptiveDamage 的随机变体版本，同源问题。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "ProcessSkillAdaptiveDamageRand（自适应随机伤害）是 ProcessSkillAdaptiveDamage 的随机变体版本。"
        "Line 3523 处 IS_PLAYER 检查失败，目标为 NPC。\n\n"
        "**可能原因：** 与 ProcessSkillAdaptiveDamage 相同 — 上游未过滤非玩家目标。\n\n"
        "**影响范围：** 2次报错，与 ProcessSkillAdaptiveDamage 成对出现。\n\n"
        "**修复建议：** 与 ProcessSkillAdaptiveDamage 统一修复方案：上游增加 IS_PLAYER 判断，或 PrintAttrExtraInfo 后改为 return false。"
    ),
    "wrecker_info": [{
        "author": "yechuan", "revision": "r331186",
        "description": "自适应随机伤害处理 - IS_PLAYER 检查",
        "principal": ["yechuan"], "type": "modify",
        "old": None, "new": "if (!IS_PLAYER(pDstCharacter->m_dwID)) pDstCharacter->PrintAttrExtraInfo(__FUNCTION__);",
        "old_line": None, "new_line": 3523
    }],
    "wrecker_index": 0
})

# --- Entry 6: pMemberPlayer MLogProcessError - aggregated 17 ---
cc.append({
    "source": "llm",
    "reference_doc": "references/mlog_process_error_pmemberplayer.md",
    "count": 17,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KPlayerServer.cpp",
    "line_num": 27699,
    "select_content": "pMemberPlayer = g_pSO3World->GetPlayer(pRequest->dwNewFormationLeaderID);\nKGMLOG_PROCESS_ERROR(pMemberPlayer, pPlayer->m_dwID);",
    "error": "[slot=MLogProcessError, attr=ProcessError, condition=pMemberPlayer, line=27699] func=void KPlayerServer::OnTeamSetFormationLeader(char*, size_t, int, int)",
    "reference": "客户端传入的 dwNewFormationLeaderID 在服务端查询不到对应玩家对象（已离线或ID无效），GetPlayer() 返回空指针。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "OnTeamSetFormationLeader（设置队伍队长）处理中，客户端请求将队长转移给 dwNewFormationLeaderID 指定的目标玩家，"
        "服务端调用 g_pSO3World->GetPlayer() 查询该玩家对象时返回空指针，触发 MLogProcessError。\n\n"
        "**可能原因：**\n"
        "1. 目标玩家已离线 — 客户端发出请求时目标在线，到达服务端时已下线\n"
        "2. 客户端传入无效玩家 ID — UI 本地缓存未及时更新导致过期数据\n"
        "3. 跨服/跨场景时玩家 ID 查询失败\n\n"
        "**影响范围：** 17次报错，影响14个以上不同玩家 ID，通用性问题。"
        "不会导致服务端崩溃（有 pMemberPlayer 空指针保护），但队伍操作失败影响玩家体验。\n\n"
        "**修复建议：**\n"
        "1. 客户端在发送设置队长请求前验证目标玩家在线状态\n"
        "2. 服务端可改为静默忽略（用 if + return 替代 MLogProcessError），队长转移失败不会造成严重后果\n"
        "3. 增加日志记录无效的 dwNewFormationLeaderID 值以便追踪来源"
    ),
    "wrecker_info": [{
        "author": "yesen", "revision": "r348526",
        "description": "队伍系统 - OnTeamSetFormationLeader 错误处理",
        "principal": ["yesen"], "type": "modify",
        "old": None, "new": "pMemberPlayer = g_pSO3World->GetPlayer(pRequest->dwNewFormationLeaderID);",
        "old_line": None, "new_line": 27699
    }],
    "wrecker_index": 0
})

# --- Entry 7: CastSkill eTargetType=0 skill 45191 ---
cc.append({
    "source": "llm",
    "reference_doc": "references/kglog_process_error_common.md",
    "count": 37,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KCharacter.cpp",
    "line_num": 3016,
    "select_content": "KGMLOG_PROCESS_ERROR(eTargetType == ttNoTarget || eTargetType == ttNpc || eTargetType == ttPlayer || eTargetType == ttDoodad || eTargetType == ttItem, ...);",
    "error": "[slot=MLogProcessError, attr=ProcessError, condition=eTargetType == ttNoTarget || eTargetType == ttNpc || eTargetType == ttPlayer || eTargetType == ttDoodad || eTargetType == ttItem, line=3016] func=int KCharacter::CastSkill(unsigned int, unsigned int, BOOL, TARGET_TYPE, unsigned int) | dwSkillID=45191, dwSkillLevel=1, eTargetType=0",
    "reference": "eTargetType=0 是未初始化的默认值或上游传参错误。技能ID=45191，等级=1。目标类型枚举中 0 对应非法值。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "KCharacter::CastSkill（角色释放技能）在 Line 3016 检查目标类型 eTargetType 合法性时失败。"
        "eTargetType=0 不属于任何合法目标类型枚举值（ttNoTarget/ttNpc/ttPlayer/ttDoodad/ttItem），"
        "表示目标类型字段未正确设置。技能 ID=45191，等级=1，说明是特定技能的调用问题。\n\n"
        "**可能原因：**\n"
        "1. eTargetType 使用了未初始化的默认值 0 — 上游调用路径未设置目标类型\n"
        "2. 网络包解析异常 — 技能释放协议包中目标类型字段缺失或损坏\n"
        "3. 技能配置表中 ID=45191 的目标类型定义有误\n"
        "4. 客户端 UI 层传入无效的目标类型\n\n"
        "**影响范围：** 37次报错，是日志中频率最高的单一错误模式。技能ID 45191 固定，玩家释放此技能时会失败。\n\n"
        "**修复建议：**\n"
        "1. 排查技能配置表中 ID=45191 的目标类型配置是否正确\n"
        "2. CastSkill 入口增加对 eTargetType=0 的防御性处理（记录调用栈日志后 return）\n"
        "3. 追踪技能 45191 的上游调用路径，确认目标类型设置逻辑\n"
        "4. 如是客户端协议问题，排查客户端发包逻辑"
    ),
    "wrecker_info": [{
        "author": "longjingyu", "revision": "r285443",
        "description": "KCharacter::CastSkill - eTargetType 合法性检查条件",
        "principal": ["longjingyu"], "type": "modify",
        "old": None, "new": "eTargetType == ttNoTarget || eTargetType == ttNpc || eTargetType == ttPlayer || eTargetType == ttDoodad || eTargetType == ttItem",
        "old_line": None, "new_line": 3016
    }],
    "wrecker_index": 0
})

# --- Entry 8: SwitchConnection bRetCode ---
cc.append({
    "source": "llm",
    "reference_doc": "references/kglog_process_error_common.md",
    "count": 1,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KPlayerServerThread.cpp",
    "line_num": 1136,
    "select_content": "bRetCode = pSendList->Confirm(wRecvSerial);\nKGMLOG_PROCESS_ERROR(bRetCode, ...);",
    "error": "[slot=MLogProcessError, attr=ProcessError, condition=bRetCode, line=1136] func=BOOL KPlayerServerThread::SwitchConnection(int, int, WORD, int, bool&) | pSendList->GetRecvSerial()=8, wRecvSerial=0",
    "reference": "断线重连时 wRecvSerial=0 与 SendList 缓存 GetRecvSerial()=8 不匹配。wRecvSerial=0 可能是客户端重连请求包序列号异常。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "KPlayerServerThread::SwitchConnection（断线重连切换连接）中，服务端用已缓存的 GetRecvSerial()=8 验证客户端传入的 wRecvSerial=0，"
        "SendList::Confirm 返回失败。wRecvSerial=0 说明客户端重连请求包中序列号字段异常（未正确维护或使用默认值）。\n\n"
        "**可能原因：**\n"
        "1. 客户端重连包中序列号字段未正确初始化\n"
        "2. 客户端在断线后未保存接收序列号就发起重连\n"
        "3. 跨场景/跨进程切换时序列号丢失\n\n"
        "**影响范围：** 单次报错。影响对应玩家的断线重连流程。\n\n"
        "**修复建议：**\n"
        "1. 客户端侧检查重连请求包中 wRecvSerial 的来源和维护逻辑\n"
        "2. 服务端可对 wRecvSerial=0 做特殊处理（视为全新连接跳过 Confirm 检查）"
    ),
    "wrecker_info": [{
        "author": "yesen", "revision": "r345255",
        "description": "SwitchConnection 断线重连流程 - SendList::Confirm",
        "principal": ["yesen"], "type": "modify",
        "old": None, "new": "bRetCode = pSendList->Confirm(wRecvSerial);",
        "old_line": None, "new_line": 1136
    }],
    "wrecker_index": 0
})

# --- Entry 9: Can't Found Action 57 ---
cc.append({
    "source": "llm",
    "reference_doc": "references/cant_found_action.md",
    "count": 3,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KCharacter.cpp",
    "line_num": 8602,
    "select_content": "pCharacterAction = g_pSO3World->m_Settings.m_CharacterActionList.GetAction(dwActionType);\nif (!pCharacterAction)\n{\n    KGLogPrintf(KGLOG_ERR, \"Can't Found Action %u by Character %u\", dwActionType, dwCharacterID);\n    goto Exit0;\n}",
    "error": "Can't Found Action 57 by Character 1074706881",
    "reference": "KCharacter::Action() 从 CharacterActionList 配置表中查找 Action 57 失败。Character 1074706881 为 NPC。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "KCharacter::Action() 在执行角色动作时，从 CharacterActionList 配置表中查找 Action ID=57 失败。"
        "Character 1074706881 为 NPC 类型，该 NPC 引用的动作 57 在动作配置表中未定义。\n\n"
        "**可能原因：**\n"
        "1. 策划配置遗漏 — Action 57 在 CharacterActionList 表中未定义\n"
        "2. 版本不匹配 — NPC 配置引用了新版本 Action 但服务端配置未同步更新\n"
        "3. NPC 配置错误 — 该 NPC 引用了不存在的 Action 类型\n"
        "4. 数据异常 — dwActionType 被错误传入（如未初始化、内存越界）\n\n"
        "**影响范围：** 3次报错（其中包含相同 NPC 的其他Action失败）。该 NPC 无法执行预期动作，可能导致其行为异常（发呆、不释放技能等）。\n\n"
        "**修复建议：**\n"
        "1. 检查 Character 1074706881 对应 NPC 模板的配置，确认其行为/脚本引用的 Action 列表\n"
        "2. 在 GetAction 失败时可降级为默认动作（如 Action 0 表示中断），避免仅报错后中断\n"
        "3. 增加详细日志（NPC模板ID、所在场景等）以便排查"
    ),
    "wrecker_info": [{
        "author": "huaibin", "revision": "r106530",
        "description": "KCharacter::Action - CharacterActionList 动作查找失败处理",
        "principal": ["huaibin"], "type": "added",
        "old": None, "new": "pCharacterAction = g_pSO3World->m_Settings.m_CharacterActionList.GetAction(dwActionType);",
        "old_line": None, "new_line": 8602
    }],
    "wrecker_index": 0
})

print("Script loaded successfully, building remaining entries...")
