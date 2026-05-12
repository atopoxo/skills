# error_analyse.py
import os
import re
import threading
from tqdm import tqdm
from typing import Any, List
from core.function.base_function import *
from core.json.json_parser import get_json_parser
from skills.skill_base import SkillBase

class CppTabCallAnalyseBase(SkillBase):
    def __init__(self, config_path, chat_mgr):
        super().__init__(config_path)
        self.chat_mgr = chat_mgr
        self.code_block_marker = "```"
        self.code_example = self._read_example()
        self.tips = {
            "analyse_prompt": """请帮我分析一下，符合下述规则的可能通过'KGLOG_', 'KGMLOG_', 'KGLogPrintf'进行报错的地方：
                1. 通过调用g_OpenTabFile返回的对象，进行的读取操作。
                2. 通过参数类型ITabFile*传入的变量，进行的读取操作。
                    """,
            "analyse_result": f"""
                重要：
                1.函数定义每行的开头是行号描述，格式为"xx: "，xx为行号
                2.直接返回如下格式的内容，xxx为编号，编号从1开始。
                格式：
                <<<-<<<代码片段xxx
                [
                    {{
                        "error_line": ......,
                        "error_msg": ......,
                        "tab_attribute": ......
                    }},
                    ...
                ]
                >>>->>>
                格式解释：
                - "......": 表示具体内容，内容参照下面的解释
                - "error_line": 可能通过'KGLOG_'或'KGLogPrintf'进行报错的行号（整数）
                - "error_msg": 报错信息（字符串）
                - "tab_attribute": 报错的tab表属性（字符串）
                ...
                {self.code_example}
                """
        }
        self.json_parser = get_json_parser()

    def _read_example(self) -> str:
        file_path = os.path.join(os.getcwd(), "src/skills/cpp_tab_call_analyse/tab_call_example.md")
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _process_worker_batch(self, worker_data: List[Any], session: Any, macros: Any, batch_size: int, pbar: tqdm, progress_lock: threading.Lock):
        count = len(worker_data)
        retry_count = 3
        for i in range(0, count, batch_size):
            batch_items = worker_data[i : i + batch_size]
            real_count = len(batch_items)

            query = self.tips["analyse_prompt"]
            for j, item in enumerate(batch_items):
                global_idx = i + j
                func_info = item['func_info']
                query += f"""
                    #代码片段{global_idx + 1}:
                        {self.code_block_marker}
                        {func_info['func_body']}
                        {self.code_block_marker}
                    """
            query += self.tips["analyse_result"]

            success = False
            for retry in range(retry_count):
                try:
                    generator = self.chat_mgr.chat_stream(None, session, False, [], query, None, None, None, {}, {})
                    content = ''
                    for text in generator():
                        # print(text, end="", flush=True)
                        content += text

                    pattern = r'<<<-<<<代码片段(\d+)\s+(.*?)\s+>>>->>>'
                    matches = re.findall(pattern, content, re.DOTALL)
                    if len(matches) != real_count:
                        print(f"\n[!] 解析失败：期望 {real_count} 个结果，实际 {len(matches)} 个。重试中...")
                        continue
                    for snippet_id, block in matches:
                        index = int(snippet_id) - 1
                        func_info = worker_data[index]['func_info']
                        block = block.strip()
                        if block:
                            block = re.sub(r',\s*}', '}', block)
                            block = re.sub(r',\s*]', ']', block)
                            try:
                                func_info['check_list'] = self.json_parser.parse(block)
                                self._fix_attributes(func_info['check_list'], macros, func_info['path'])
                            except Exception as e:
                                print(f"[ERROR] 解析JSON失败: {e}")
                                print(f"[ERROR] 尝试解析的内容: {block}")
                                func_info['check_list'] = []
                        else:
                            print(f"[WARNING] 代码片段{snippet_id}的block为空")
                            func_info['check_list'] = []
                        success = False
                    success = True
                    break
                except Exception as ex:
                    print(f"\n[!] 处理异常: {ex}")
            if not success:
                print(f"[!] 批次 {i//batch_size + 1} 处理失败，已达到最大重试次数。")
                print(f"{retry_count}次尝试用ai分析代码片段{i + 1}-{i + 1 + real_count}均以失败告终")
            with progress_lock:
                pbar.update(real_count)

    def _fix_attributes(self, check_list: List[Dict], macros: Any, path_list: List[str]):
        for check in check_list:
            tab_attribute = check['tab_attribute']
            cur_micros = macros['global'].get(tab_attribute, {})
            if tab_attribute in cur_micros:
                self._fix_attribute_micro(check, tab_attribute, cur_micros)
            for path in path_list:
                cur_micros = macros['local'].get(path, {})
                if tab_attribute in cur_micros:
                    self._fix_attribute_micro(check, tab_attribute, cur_micros)

    def _fix_attribute_micro(self, check: Dict, tab_attribute: str, cur_micros: Any):
        macro_info = cur_micros[tab_attribute]
        macro_type = macro_info.get('type', '')
        macro_value = macro_info.get('value', '')
        if macro_type:
            if macro_type in ['int', 'short', 'long', 'float', 'double', 'bool', 'char']:
                if macro_value and macro_value.strip():
                    check['tab_attribute'] = f"{tab_attribute} ({macro_type}: {macro_value})"
                else:
                    check['tab_attribute'] = f"{tab_attribute} ({macro_type})"
            elif macro_type == 'string' or 'char' in macro_type:
                if macro_value and macro_value.strip():
                    clean_value = macro_value.strip()
                    # Remove surrounding quotes if present
                    if clean_value.startswith('"') and clean_value.endswith('"'):
                        # Remove the outer quotes
                        clean_value = clean_value[1:-1]
                        # Check if there are still quotes inside (like '"TeamID"')
                        if clean_value.startswith('"') and clean_value.endswith('"'):
                            clean_value = clean_value[1:-1]
                        check['tab_attribute'] = clean_value
                    elif clean_value.startswith("'") and clean_value.endswith("'"):
                        # Remove the outer single quotes
                        clean_value = clean_value[1:-1]
                        # Check if there are still single quotes inside
                        if clean_value.startswith("'") and clean_value.endswith("'"):
                            clean_value = clean_value[1:-1]
                        check['tab_attribute'] = clean_value
                    else:
                        check['tab_attribute'] = f'"{clean_value}"'
                else:
                    check['tab_attribute'] = f'"{tab_attribute}"'
            else:
                check['tab_attribute'] = f"{tab_attribute} ({macro_type})"
        elif macro_value and macro_value.strip():
            clean_value = macro_value.strip()
            # Remove surrounding quotes if present
            if clean_value.startswith('"') and clean_value.endswith('"'):
                # Remove the outer quotes
                clean_value = clean_value[1:-1]
                # Check if there are still quotes inside (like '"TeamID"')
                if clean_value.startswith('"') and clean_value.endswith('"'):
                    clean_value = clean_value[1:-1]
                check['tab_attribute'] = clean_value
            elif clean_value.startswith("'") and clean_value.endswith("'"):
                # Remove the outer single quotes
                clean_value = clean_value[1:-1]
                # Check if there are still single quotes inside
                if clean_value.startswith("'") and clean_value.endswith("'"):
                    clean_value = clean_value[1:-1]
                check['tab_attribute'] = clean_value
            else:
                check['tab_attribute'] = f'"{clean_value}"'