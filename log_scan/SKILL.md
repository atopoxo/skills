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

1. **读取输出格式规范**：在处理前必须读取 `assets/error_output_format.json`（function call 格式的输出规范，供大模型理解并输出结构化结果），记录每种分类（`tab_load`、`lua_call`、`lua`、`c/c++`）所需的属性字段及其类型/描述，同时参考 `assets/error_output_example.json` 的样例输出。输出格式中四类错误说明：
   - `tab_load` — 表格相关错误
   - `lua_call` — lua调用c/c++接口参数个数不匹配错误
   - `lua` — lua自身相关错误
   - `c/c++` — c/c++代码相关报错
2. **分类归纳**：将每条报错按上述四类归类。归类原则：
   - 涉及 `.tab` 配置表数据校验失败、表字段值超出范围、配置项缺失的 → `tab_load`
   - Lua 远程调用（`AcceptC2SRemoteLuaCall`）且属于正常交互行为的 → `lua`（标记为安全、无需告警）
   - C/C++ 代码中的 `KGLOG_PROCESS_ERROR`、`MLogProcessError`、`Can't Found Action`、技能/Buff/物品创建失败等 → `c/c++`
   - `lua_call` 分类仅用于 C 接口参数个数不匹配场景，temporary_else 中极少出现
3. **分析原因**：结合报错信息中的函数名、行号、条件表达式推断可能原因。**优先参考 `references/` 目录中已有的经验文档**，避免重复分析。**如果涉及读取源文件内容，调用 `ElseAnalyzer.read_files()` 方法**，由该方法记录待读取文件并开启最多 16 个线程并行读取
4. **关联责任人**：参考 `scripts/custom_config.json` 中 `cpp_source` 指明的 C/C++ 代码路径和 `script_map` 指明的脚本/.tab 路径定位源文件，优先通过 `svn diff` 查找最近修改该文件/行的人员，若 diff 无法定位再回退使用 `svn blame` 获取责任人。调用 `scripts/src/skills/find_wrecker/find_wrecker.py` 的 `get_principal` 获取主责人。**SVN 操作统一通过 `ElseAnalyzer.svn_query()` 方法执行**，由该方法记录待查询文件并开启最多 16 个线程并行执行 SVN 查询
5. **生成结构化 JSON**：按 `assets/error_output_format.json` 和 `assets/error_output_example.json` 规范格式化输出，每条记录需包含：
   - `source`: 标记为 `"llm"`（大模型分析结果）
   - `reference_doc`: 引用的 references 文档相对路径，无则为 `null`
   - 对应分类的所有必填字段（参考 format 定义）
   - 输出文件命名为 `temporary_else_analysis.json`，保存到 `scripts/.results/` 下**当前这次运行对应的** `final_result_{timestamp}` 目录中

**ElseAnalyzer 调用方式**：

```python
import sys
sys.path.insert(0, r"scripts\src")

from skills.else_analyzer.else_analyzer import ElseAnalyzer
from core.json.json_parser import get_json_parser

config_path = r"scripts\custom_config.json"
analyzer = ElseAnalyzer(config_path)

# 并行读取文件
file_paths = [r"z:/trunk/server/scripts/xxx.lua", r"i:/SVN/trunk/Sword3/Source/xxx.cpp"]
file_contents = analyzer.read_files(file_paths, encoding='gbk', max_workers=16)
# 返回: {file_path: [line1, line2, ...]}

# 并行 SVN 查询
svn_info = analyzer.svn_query(file_paths, encoding='gbk', max_workers=16)
# 返回: {file_path: [{author, revision, description, principal}, ...]}
```

### 输出强制规范

以下三条为强制性要求，输出 JSON 时逐条校验：

1. **`source` 为 `"llm"` 时 `need_analyse` 必须为 `true`**：大模型产出的分析结果默认仍需进一步分析，不可设为 `false`。仅当 `source` 为 `"analyzer"`（工具自动分析）时 `need_analyse` 才可为 `false`。

2. **`suggestion` 中禁止出现"参见 references/xxx"等引用式写法**：必须将参考文档中的分析结论、原因、修复方案完整展开写入 `suggestion` 字段。每一条 suggestion 应是独立可读的完整分析，包含：错误原因解释、影响范围评估、具体修复步骤（含代码示例或配置修改方式）。即使是已由经验文档覆盖的已知模式，也必须将经验文档内容全文展开，不得偷懒引用。

3. **`wrecker_info` 不能为空数组**：每一条输出记录必须至少包含一条 SVN 相关记录。若 `svn blame` / `svn diff` 均无法定位到具体提交者，则填入一条占位记录：`{"author": "unknown", "revision": "unknown", "description": "无法定位责任人", "principal": [], "type": "modify", "old": null, "new": null, "old_line": null, "new_line": null}`，并将 `wrecker_index` 设为 `-1`。

### 5. 合并报错结果到最终报告

完成 temporary_else 分析和输出后，将大模型分析结果合并到最终报告。调用 `scripts/src/skills/merge_result/merge_result.py` 中的 `MergeResult` 类执行合并：

```python
import sys
import os
sys.path.insert(0, r"scripts\src")

from skills.merge_result.merge_result import MergeResult

cwd = r"scripts"  # 工作目录，包含 .temporary_results/
result_dir = r"scripts\.results\final_result_{timestamp}"  # 当前这次运行对应的目录
product_dir = r"z:/trunk"  # 产品目录，从 custom_config.json 的 script_map 中获取

# 计算 C/C++ 源码公共父目录（与 analyzer.py 步骤 7 一致）
import json
with open(r"scripts\custom_config.json", 'r', encoding='utf-8') as f:
    config = json.load(f)
cpp_roots = [src['root'] for src in config.get('cpp_source', [])]
cpp_source_dir = os.path.commonpath(cpp_roots) if cpp_roots else ''

merger = MergeResult(cwd)
merged = merger.merge_result(result_dir)

if merged:
    # 合并成功后，仿照 analyzer.py 步骤 7 重新生成 HTML 报告
    # context_result 从合并后的 total.json 读入，current_step=8
    merger.regenerate_report(result_dir, [product_dir, cpp_source_dir], encoding='gbk')
```

合并与重新生成原则：
- 对 4 个 category（`tab_load`、`lua_call`、`lua`、`c/c++`）逐一将 temporary_else_analysis 的数组合并到 temporary_svn 对应数组末尾
- `temporary_svn_*.json` 与 `total.json` 内容一致（均为 analyzer.py 步骤 7 的输出产物），因此合并后直接覆盖 total.json 不会丢失已有数据
- 合并后调用 `regenerate_report` 重新生成 HTML 报告：从合并后的 total.json 读取 context_result，以 `current_step=8` 调用 `ResultGenerate.save()`，`product_dir` 参数传入 `[product_dir, cpp_source_dir]`（列表格式），其余参数（`encoding`、`result_dir`、`root_html_path`）与 analyzer.py 中 `analyse_log_file` 步骤 7 一致
- 如无需合并（无 temporary_else 文件或全为空），`merge_result` 返回 False，跳过重新生成

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
| 输出格式规范（function call） | `assets/error_output_format.json` |
| 输出格式样例 | `assets/error_output_example.json` |
| 可扩展 skill 脚本 | `scripts/src/skills/` |
| Skill 基类 | `scripts/src/skills/skill_base.py` |
| temporary_else 并行文件/SVN 工具 | `scripts/src/skills/else_analyzer/` |
| 依赖列表 | `scripts/requirements.txt` |

## custom_config.json 关键字段

- **`script_map`**：版本名 → 产品目录路径的映射（如 `"bvt": "z:/trunk"`），用于定位 Lua 脚本和 .tab 表
- **`cpp_source`**：C/C++ 源码根目录列表，每项含 `root`（路径）和 `black_list`（排除目录）
- **`base_url`**：结果 HTML 的外部访问基地址
- **`svn.use_svn`**：是否启用 SVN blame 查询责任人
- **`server_whole_log_path`**：服务端完整日志路径
