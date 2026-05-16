#!/usr/bin/env python
"""Part 2: Remaining c/c++ entries for temporary_else_analysis.json"""
import json
import os

# This will be appended to part 1's output dict
# The caller (full script) will merge both parts

cc_remaining = []

# --- Entry 10: Can't Found Action 68 ---
cc_remaining.append({
    "source": "llm",
    "reference_doc": "references/cant_found_action.md",
    "count": 1,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KCharacter.cpp",
    "line_num": 8602,
    "select_content": "pCharacterAction = g_pSO3World->m_Settings.m_CharacterActionList.GetAction(dwActionType);\nif (!pCharacterAction)\n{\n    KGLogPrintf(KGLOG_ERR, \"Can't Found Action %u by Character %u\", dwActionType, dwCharacterID);\n    goto Exit0;\n}",
    "error": "Can't Found Action 68 by Character 1074706881",
    "reference": "与 Action 57 相同模式，同一 NPC Character 1074706881 请求了未定义的动作类型 68。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "与 Can't Found Action 57 同源问题。同一 NPC（Character 1074706881）在执行动作时，"
        "CharacterActionList 配置表中未找到 Action ID=68。该 NPC 连续请求了多个未注册动作（57 和 68），"
        "说明 NPC 配置可能整体引用了未同步更新的动作表。\n\n"
        "**可能原因：** 与 Action 57 相同 — 策划配置遗漏、版本不匹配或 NPC 配置错误。\n\n"
        "**影响范围：** 单次报错。该 NPC 无法执行动作 68。\n\n"
        "**修复建议：**\n"
        "1. 与 Action 57 一并排查：检查 NPC 1074706881 的完整配置，修复所有缺失的动作引用\n"
        "2. 在 GetAction 失败时可降级为默认动作，而非中断\n"
        "3. 策划工具增加动作引用完整性校验"
    ),
    "wrecker_info": [{
        "author": "huaibin", "revision": "r106530",
        "description": "KCharacter::Action - 动作查找失败处理",
        "principal": ["huaibin"], "type": "added",
        "old": None, "new": "pCharacterAction = g_pSO3World->m_Settings.m_CharacterActionList.GetAction(dwActionType);",
        "old_line": None, "new_line": 8602
    }],
    "wrecker_index": 0
})

# --- Entry 11: CreateSkill(0:0) ---
cc_remaining.append({
    "source": "llm",
    "reference_doc": "references/skill_create_chain_error.md",
    "count": 1,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KSkill.cpp",
    "line_num": 1581,
    "select_content": "// KSkill::CreateSkill - skillID=0 表示未初始化或默认值，上游未正确设置技能ID",
    "error": "[KSkill] CreateSkill(0:0) not found from skill's table. [1581]",
    "reference": "CreateSkill(0:0) — skillID=0 是未初始化默认值，上游调用路径未正确设置技能 ID。行号 [1581]。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "KSkill 系统尝试创建技能时，传入的 skillID=0 且 level=0，从技能配置表中查询失败。"
        "skillID=0 表示未初始化或默认值，说明上游调用路径未正确传递技能 ID。\n\n"
        "**可能原因：**\n"
        "1. 技能释放流程中技能 ID 传递丢失或被覆盖\n"
        "2. 网络包中技能字段解析异常\n"
        "3. 客户端/服务端协议版本不匹配导致字段偏移\n"
        "4. 某段 Lua 脚本调用 CreateSkill 时未提供有效 skillID\n\n"
        "**影响范围：** 单次报错。会导致技能创建失败，玩家对应操作无效。\n\n"
        "**修复建议：**\n"
        "1. CreateSkill 入口增加参数校验：skillID==0 时记录调用栈后直接返回 NULL，避免无意义的配置表查询\n"
        "2. 增加上游调用日志，追踪 skillID=0 的来源\n"
        "3. 排查网络协议中技能字段的填充和解析逻辑"
    ),
    "wrecker_info": [{
        "author": "yechuan", "revision": "r348859",
        "description": "技能系统重构 - 技能配置表查询",
        "principal": ["yechuan"], "type": "modify",
        "old": None, "new": None,
        "old_line": None, "new_line": None
    }],
    "wrecker_index": -1
})

# --- Entry 12: ApplyOnChain pSubSkill not exist ---
cc_remaining.append({
    "source": "llm",
    "reference_doc": "references/skill_create_chain_error.md",
    "count": 1,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KSkill.cpp",
    "line_num": 1582,
    "select_content": "// ApplyOnChain - 技能链子技能查询失败",
    "error": "[ApplyOnChain] pSubSkill not exist, skill:(30854, 1), sub:0 [1582]",
    "reference": "技能 30854 等级 1 的 ChainSkill 配置中 sub index=0 的子技能不存在。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "ApplyOnChain（技能链应用）中，技能 30854（等级 1）的 ChainSkill 配置引用了 sub index=0 的子技能，"
        "但该子技能在技能配置表中未定义或已被删除。应用链子技能时查询失败。\n\n"
        "**可能原因：**\n"
        "1. 技能 30854 的 ChainSkill 配置表中填写的子技能 ID 错误\n"
        "2. 子技能配置被删除但父技能的链引用未更新\n"
        "3. 子技能有等级/条件限制导致查询失败\n"
        "4. 策划工具未做链技能引用完整性校验\n\n"
        "**影响范围：** 单次报错。技能 30854 的链效果无法正常触发。\n\n"
        "**修复建议：**\n"
        "1. 检查技能 30854 的 ChainSkill 配置，确认 sub index=0 的子技能 ID 是否存在\n"
        "2. ApplyOnChain 中 pSubSkill 为空时输出子技能 ID 日志便于排查\n"
        "3. 策划工具增加链技能引用完整性校验"
    ),
    "wrecker_info": [{
        "author": "yechuan", "revision": "r348859",
        "description": "技能系统 - ApplyOnChain 链子技能处理",
        "principal": ["yechuan"], "type": "modify",
        "old": None, "new": None,
        "old_line": None, "new_line": None
    }],
    "wrecker_index": -1
})

# --- Entry 13: KGItemHouse::CreateItem pItemInfo null ---
cc_remaining.append({
    "source": "llm",
    "reference_doc": "references/item_create_shop_error.md",
    "count": 1,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3ItemHouse/KGItemHouse.cpp",
    "line_num": 131,
    "select_content": "pItemInfo = GetItemInfo(dwTabType, dwTabIndex);\nKGLOG_PROCESS_ERROR(pItemInfo);",
    "error": "KGLOG_PROCESS_ERROR(pItemInfo) at line 131 in virtual IItem* KGItemHouse::CreateItem(DWORD, DWORD, time_t, DWORD, DWORD, int)",
    "reference": "GetItemInfo(dwTabType, dwTabIndex) 查询物品配置表失败返回空指针。nType/nIndex 组合在物品配置表中不存在。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "KGItemHouse::CreateItem 通过 GetItemInfo(dwTabType, dwTabIndex) 查询物品配置信息时返回空指针，"
        "触发 KGLOG_PROCESS_ERROR(pItemInfo)。说明 (dwTabType, dwTabIndex) 组合在物品配置表中不存在。\n\n"
        "**可能原因：**\n"
        "1. 客户端缓存了已删除的物品数据\n"
        "2. Lua 脚本或任务配置引用了不存在的物品 ID\n"
        "3. 物品表版本更新后部分旧物品被移除\n"
        "4. 网络包中物品字段数据异常\n\n"
        "**影响范围：** 单次报错。对应物品创建失败，可能导致玩家无法获得预期物品。\n\n"
        "**修复建议：**\n"
        "1. KGMLOG_PROCESS_ERROR 前打印 CreateItem 入参 (nType, nIndex)，便于定位无效物品 ID\n"
        "2. 排查是哪段脚本或配置请求了不存在的物品\n"
        "3. 物品删除时做好版本兼容处理"
    ),
    "wrecker_info": [{
        "author": "yechuan", "revision": "r351515",
        "description": "安全日志注入 - KGItemHouse::CreateItem 错误处理",
        "principal": ["yechuan"], "type": "modify",
        "old": None, "new": "pItemInfo = GetItemInfo(dwTabType, dwTabIndex); KGLOG_PROCESS_ERROR(pItemInfo);",
        "old_line": None, "new_line": 131
    }],
    "wrecker_index": 0
})

# --- Entry 14: [Shop] invalid item ---
cc_remaining.append({
    "source": "llm",
    "reference_doc": "references/item_create_shop_error.md",
    "count": 1,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KShop.cpp",
    "line_num": 0,
    "select_content": "// [Shop] 商店模板物品有效性检查",
    "error": "[Shop] Shop template ID 1365, invalid item (nType = 10, nIndex = 2158, dwRandomSeed = 0) !",
    "reference": "商店模板 1365 配置的物品 (nType=10, nIndex=2158) 无效。dwRandomSeed=0 说明随机种子未正确设置。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "商店系统在加载模板 ID=1365 时，发现其中配置的物品 (nType=10, nIndex=2158) 无效。"
        "dwRandomSeed=0 进一步说明该物品可能来自随机物品池且随机种子未正确设置。\n\n"
        "**可能原因：**\n"
        "1. 商店模板 1365 配置了已移除或未定义的物品\n"
        "2. 随机商店物品池配置错误，随机到不存在的物品\n"
        "3. 物品表版本更新后商店模板未同步更新\n"
        "4. dwRandomSeed=0 表明随机种子生成逻辑异常\n\n"
        "**影响范围：** 单次报错。商店模板 1365 加载异常，该模板对应的商店可能无法正常展示或出售物品。\n\n"
        "**修复建议：**\n"
        "1. 检查商店模板 1365 的配置，修复无效物品引用 (nType=10, nIndex=2158)\n"
        "2. 商店模板加载时增加物品有效性前置校验\n"
        "3. 排查 dwRandomSeed=0 的原因，确保随机种子正确生成"
    ),
    "wrecker_info": [{
        "author": "unknown", "revision": "unknown",
        "description": "商店系统文件路径待确认，无法定位确切责任人",
        "principal": [], "type": "modify",
        "old": None, "new": None,
        "old_line": None, "new_line": None
    }],
    "wrecker_index": -1
})

# --- Entry 15: BuffNotExist ---
cc_remaining.append({
    "source": "llm",
    "reference_doc": "references/buff_not_exist.md",
    "count": 1,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KBuffList.cpp",
    "line_num": 640,
    "select_content": "pOriginBuff = g_pSO3World->m_BuffManager.GetBuff_RAW(BuffRecipeKey.dwID, BuffRecipeKey.nLevel);",
    "error": "[slot=Buff, attr=BuffNotExist, buff_id=562, buff_lv=49] in KBuffList::CallBuff",
    "reference": "Buff ID=562, Level=49 组合在 Buff 配置表中不存在，GetBuff_RAW 查询失败。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "KBuffList::CallBuff 在调用 Buff 时，通过 GetBuff_RAW 查询 Buff ID=562, Level=49 的组合，"
        "但在 Buff 配置表中未找到对应的 Buff 定义。这可能是 Buff 配置被删除、ID 变更或等级范围不匹配导致。\n\n"
        "**可能原因：**\n"
        "1. Buff ID=562 的 Level=49 等级在配置表中不存在（等级范围定义过小）\n"
        "2. Buff 562 配置被整体删除但引用方未更新\n"
        "3. 技能/道具/脚本引用了不存在的 Buff ID/等级组合\n\n"
        "**影响范围：** 单次报错。触发该 Buff 的技能或效果将无法正确应用，影响对应玩法。\n\n"
        "**修复建议：**\n"
        "1. 检查 Buff 配置表中 ID=562 的等级范围，确认是否包含 Level 49\n"
        "2. CallBuff 中增加详细参数日志（触发来源技能ID/角色ID），便于定位引用方\n"
        "3. 如果 ID=562 的 Level=49 是合法组合，检查 Buff 表的加载流程"
    ),
    "wrecker_info": [{
        "author": "yechuan", "revision": "r351454",
        "description": "安全日志注入 - KBuffList::CallBuff 流程",
        "principal": ["yechuan"], "type": "modify",
        "old": None, "new": "pOriginBuff = g_pSO3World->m_BuffManager.GetBuff_RAW(BuffRecipeKey.dwID, BuffRecipeKey.nLevel);",
        "old_line": None, "new_line": 640
    }],
    "wrecker_index": 0
})

# --- Entry 16: KGLOG_PROCESS_ERROR(pOriginBuff) ---
cc_remaining.append({
    "source": "llm",
    "reference_doc": "references/buff_not_exist.md",
    "count": 1,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KBuffList.cpp",
    "line_num": 641,
    "select_content": "pOriginBuff = g_pSO3World->m_BuffManager.GetBuff_RAW(BuffRecipeKey.dwID, BuffRecipeKey.nLevel);\nKGLOG_PROCESS_ERROR(pOriginBuff);",
    "error": "KGLOG_PROCESS_ERROR(pOriginBuff) at line 641 in KBuffList::CallBuff",
    "reference": "pOriginBuff 为空 — GetBuff_RAW 查询失败，源 Buff 配置在 Buff 表中不存在。与 BuffNotExist 模式2 配对出现。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "KBuffList::CallBuff 中，GetBuff_RAW 查询源 Buff 配置返回空指针，触发 KGLOG_PROCESS_ERROR(pOriginBuff)。"
        "此错误与 BuffNotExist（模式1）常在同一 CallBuff 调用中成对出现：源 Buff 配置缺失导致 pOriginBuff 为空，"
        "进而触发 BuffNotExist 日志。\n\n"
        "**可能原因：**\n"
        "1. 与 BuffNotExist 同源 — Buff ID/等级组合在配置表中不存在\n"
        "2. 链式 Buff 调用时源 Buff 在调用前已被移除/过期\n"
        "3. Buff 配置表加载异常导致部分条目缺失\n\n"
        "**影响范围：** 单次报错。与 BuffNotExist 配对，导致相关 Buff 效果无法应用。\n\n"
        "**修复建议：**\n"
        "1. 与 BuffNotExist 合并排查：确认触发 Buff 的源头（技能/道具/脚本）\n"
        "2. CallBuff 中增加详细参数日志（触发来源技能ID/角色ID）\n"
        "3. 检查源 Buff 的创建和生命周期管理，确保链式调用时源 Buff 不会被提前释放"
    ),
    "wrecker_info": [{
        "author": "yechuan", "revision": "r351454",
        "description": "安全日志注入 - pOriginBuff 空指针检查",
        "principal": ["yechuan"], "type": "modify",
        "old": None, "new": "KGLOG_PROCESS_ERROR(pOriginBuff);",
        "old_line": None, "new_line": 641
    }],
    "wrecker_index": 0
})

# --- Entry 17: [KIndividualDropList] ---
cc_remaining.append({
    "source": "llm",
    "reference_doc": None,
    "count": 1,
    "encoding": "GBK",
    "file_path": "I:/SVN/trunk/Sword3/Source/Common/SO3World/Src/KIndividualDropList.cpp",
    "line_num": 0,
    "select_content": "// KIndividualDropList - 个人掉落列表处理",
    "error": "[KIndividualDropList] — 个人掉落列表相关日志",
    "reference": "KIndividualDropList 类负责处理玩家个人掉落（拾取）列表。该类在 KRecipe.cpp 中被引用。报错信息不完整，仅包含类名标签不含具体错误描述。",
    "need_analyse": True,
    "suggestion": (
        "**错误解释：**\n"
        "日志中出现 [KIndividualDropList] 标签但不含具体错误描述，说明程序在个人掉落列表处理流程中输出了一条日志但信息不完整。"
        "可能是某处 KGLogPrintf 调用时只打印了模块标签，具体错误信息被截断或未正确格式化。\n\n"
        "**可能原因：**\n"
        "1. 日志格式化参数不匹配 — printf 格式串与参数个数不一致\n"
        "2. 个人掉落列表操作触发但上下文信息不足\n"
        "3. 某个预期触发告警的条件被触发，但日志信息不完整\n\n"
        "**影响范围：** 单次报错，信息不足无法评估具体影响。\n\n"
        "**修复建议：**\n"
        "1. 在 KIndividualDropList.cpp 中搜索 KGLogPrintf 调用，确认所有日志输出格式串与参数匹配\n"
        "2. 补充日志上下文信息（掉落物品ID、玩家ID、操作类型等）\n"
        "3. 如该标签仅作为 marker 日志（标记代码路径），应完善日志格式"
    ),
    "wrecker_info": [{
        "author": "yesen", "revision": "r336642",
        "description": "个人掉落系统 - 拾取掉落同步处理",
        "principal": ["yesen"], "type": "modify",
        "old": None, "new": None,
        "old_line": None, "new_line": None
    }],
    "wrecker_index": -1
})

print(f"Part 2: {len(cc_remaining)} entries ready")
