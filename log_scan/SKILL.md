---
name: log-scan
description: 通过分析剑网三服务端日志，自动定位 Lua 脚本、.tab 配置表、C/C++ 代码中的潜在问题，输出结构化分析报告。触发条件：用户请求分析剑网三日志、检查服务端报错、或提到 log_scan / 日志扫描。
---

# Log Scan — 剑网三日志问题分析

> **技能根目录**：`Y:\AI\skills\log_scan`。下文中所有相对路径均基于此目录。

通过检查剑网三（JX3）服务端日志，自动定位 Lua 脚本、.tab 配置表、C/C++ 代码中的潜在问题，并输出结构化分析报告。

## 触发条件

当用户请求分析剑网三日志、检查服务端报错、或提到 log_scan / 日志扫描 时使用本 skill。

## 核心流程

### 1. 运行 analyzer.py 主分析

默认首先执行：

```bash
python scripts/src/analyzer.py
```

**执行前必须记录当前时间**（精确到秒），用于后续定位 `scripts/.results/` 下的输出目录。结果目录命名格式为 `final_result_{timestamp}`，你需要在其中找到时间戳晚于记录时间的最新目录。

**执行过程中须实时查看 analyzer.py 的标准输出**，其每一步均有 `[时间戳] 步骤N: ...` 格式的打印日志，通过实时捕获这些输出了解当前进度及中间统计信息（如发现多少处报错、独一无二报错数量等），以便在出错或卡住时及时介入。

analyzer.py 的完整分析流程（7 步）：
1. 从代码库提取函数信息和 .tab 表信息
2. 解析日志，提取错误
3. 检查脚本调用 tab 接口参数、C 接口参数、分析上下文引用
4. 大模型分析改进建议
5. 查询 SVN 责任人
6. 分析 SVN 责任人归属
7. 输出最终 HTML 报告到 `scripts/.results/final_result_{timestamp}/`

### 2. 处理 temporary_else 遗留报错

`analyzer.py` 的 `run()` 调用 `analyse_log_file` 时 `temporary_file_path` 参数不为 None（已传入历史临时文件做断点续跑），因此无需监控增量，直接使用 `scripts/.temporary_results/` 目录中**时间戳最新**的 `temporary_else_*.json` 文件即可。

`temporary_else_*.json` 包含未能归类到已知模式的"其他"报错，结构为 JSON 数组，每项是一条原始日志行。对于这些报错，你需要：

1. **分类归纳**：按报错类型（`KGLOG_PROCESS_ERROR`、`[slot=MLogProcessError]`、Lua 远程调用、网络错误等）归类
2. **分析原因**：结合报错信息中的函数名、行号、条件表达式推断可能原因
3. **关联责任人**：参考 `scripts/custom_config.json` 中 `cpp_source` 指明的 C/C++ 代码路径和 `script_map` 指明的脚本/.tab 路径定位源文件，优先通过 `svn diff` 查找最近修改该文件/行的人员，若 diff 无法定位再回退使用 `svn blame` 获取责任人
4. **生成结构化 JSON**：输出到 `scripts/.results/` 下**当前这次运行对应的** `final_result_{timestamp}` 目录中

### 3. 经验文档管理

`references/` 目录用于存放已知报错模式的经验文档。初始为空。

对于每次新发现的报错类型：
- 归纳整理该报错的特征（匹配模式、涉及的函数/文件、典型原因）
- 将经验写入 `references/` 目录，文件按报错类别命名（如 `kglog_process_error.md`、`lua_remote_call.md` 等）
- 后续分析遇到同类报错时，**优先参考已有经验文档**，避免重复分析

### 4. 高频问题自动化

如果某类问题频繁出现（在同一 session 或跨多次运行中反复命中），应将其分析逻辑实现为独立的 Python 脚本，放入 `scripts/src/skills/` 目录。

实现要求：
- 继承或遵循 `scripts/src/skills/skill_base.py` 中的基类约定
- 对外的入口函数接口与现有 skills（如 `error_analyse`、`tab_error_finder`、`cpp_error_analyse` 等）保持一致
- 完成后在 `analyzer.py` 中按需集成调用

## 关键路径速查

| 用途 | 路径 |
|------|------|
| 主入口脚本 | `scripts/src/analyzer.py` |
| 自定义配置（代码路径、脚本路径） | `scripts/custom_config.json` |
| 临时中间结果 | `scripts/.temporary_results/` |
| 最终报告输出 | `scripts/.results/final_result_{timestamp}/` |
| 经验文档库 | `references/` |
| 可扩展 skill 脚本 | `scripts/src/skills/` |
| Skill 基类 | `scripts/src/skills/skill_base.py` |
| 依赖列表 | `scripts/requirements.txt` |

## custom_config.json 关键字段

- **`script_map`**：版本名 → 产品目录路径的映射（如 `"bvt": "z:/trunk"`），用于定位 Lua 脚本和 .tab 表
- **`cpp_source`**：C/C++ 源码根目录列表，每项含 `root`（路径）和 `black_list`（排除目录）
- **`base_url`**：结果 HTML 的外部访问基地址
- **`svn.use_svn`**：是否启用 SVN blame 查询责任人
- **`server_whole_log_path`**：服务端完整日志路径
