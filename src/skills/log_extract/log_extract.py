# log_extract.py
import re
import glob
import os
import datetime
from typing import List, Dict, Any, Tuple
from core.function.base_function import *
from skills.skill_base import SkillBase

@singleton
class LogExtract(SkillBase):
    def __init__(self, config_path):
        super().__init__(config_path)
        self.invalid_path_chars = set('<>:"|?*')

    def extract(self, log_paths: list, encoding: str) -> List[Dict]:
        count = 0
        errors = {
            "lua": [],
            "lua_call": [],
            "tab_load": [],
            "else": []
        }
        try:
            for log_path in log_paths:
                content = get_file_content(log_path, encoding=encoding)
                # 第一步：使用extract_rule1提取，然后从content中剔除匹配的部分
                matched_positions1 = self.extract_rule1(errors["lua"], content, encoding)
                content = self.__remove_matches_by_positions(content, matched_positions1)

                # 第二步：使用extract_rule2提取，然后从content中剔除匹配的部分
                matched_positions2 = self.extract_rule2(errors["lua"], content, encoding)
                content = self.__remove_matches_by_positions(content, matched_positions2)

                # 第三步：使用extract_rule3提取，然后从content中剔除匹配的部分
                matched_positions3 = self.extract_rule3(errors["lua_call"], content, encoding)
                content = self.__remove_matches_by_positions(content, matched_positions3)

                # 第四步：使用extract_rule4从剩余的content中提取
                matched_positions4 = self.extract_rule4(errors["tab_load"], content, encoding, K=5)
                content = self.__remove_matches_by_positions(content, matched_positions4)

                # 第五步：使用extract_rule_else从剩余的content中提取
                matched_positions5 = self.extract_rule_else(errors["else"], content, encoding, K=5)
                content = self.__remove_matches_by_positions(content, matched_positions5)

            for key in errors:
                count += len(errors[key])

        except Exception as ex:
            print(f"读取日志文件失败: {ex}")
        print(f"[*] LogExtract 提取出 {len(errors)} 条结构化错误信息")
        return (errors, count)
    
    def extract_rule1(self, errors: List[Any], content: str, encoding: str):
        # 修改正则表达式，从时间戳开始匹配
        error_block_pattern = re.compile(
            r'\d{8}-\d{6},\d{3}<ERROR:[^>]+>:\s*\[Lua\]\s*(.*?)(?=\d{8}-\d{6},\d{3}<|$)',
            re.DOTALL
        )
        path_line_pattern = re.compile(
            r'^\[string\s+"([^"]+)"\]:(\d+):\s*(.*)$',
            re.IGNORECASE | re.DOTALL
        )
        error_path_pattern = re.compile(
            r'.*script:\s*(\S+)',
            re.IGNORECASE
        )
        # 使用finditer获取匹配对象，包括位置信息
        matches = list(error_block_pattern.finditer(content))
        matched_positions = []  # 记录匹配位置 (start, end)

        for index, match_obj in enumerate(matches):
            block = match_obj.group(1).strip()
            if not block:
                continue
            path = "Unknown"
            line_num = 0
            block_match = path_line_pattern.search(block)
            if block_match:
                path = block_match.group(1)
                line_num = int(block_match.group(2))
                next_match_obj = None
                if index + 1 < len(matches):
                    next_match_obj = matches[index + 1]
                    next_block = next_match_obj.group(1).strip()
                    if next_block:
                        error_path_match = error_path_pattern.search(next_block)
                        if error_path_match:
                            extracted_script_path = error_path_match.group(1).strip()
                            clean_path = self.__get_valid_path(path, encoding)
                            if clean_path in extracted_script_path:
                                path = extracted_script_path
                            else:
                                path = clean_path
                    else:
                        next_match_obj = None
                else:
                    next_match_obj = None
                path = self.__fix_path(path)
                errors.append({
                    "file": path,
                    "line_number": line_num,
                    "error": block_match.group(3),
                    'reference_need': True
                })
                # 记录当前匹配的位置（包含时间戳）
                matched_positions.append((match_obj.start(), match_obj.end()))
                # 如果使用了下一个匹配块，也记录它的位置
                if next_match_obj:
                    matched_positions.append((next_match_obj.start(), next_match_obj.end()))

        return matched_positions   

    def extract_rule2(self, errors: List[Any], content: str, encoding: str):
        error_block_pattern = re.compile(
            r'\d{8}-\d{6},\d{3}<ERROR:[^>]+>:\s*(.*?)(?=\d{8}-\d{6},\d{3}<|$)',
            re.DOTALL
        )
        path_line_pattern = re.compile(
            r'^\s*\[([^\]]+)\]:(\d+):\s*(.*)',
            re.MULTILINE
        )
        # 使用finditer获取匹配对象，包括位置信息
        matches = list(error_block_pattern.finditer(content))
        matched_positions = []  # 记录匹配位置 (start, end)

        for match_obj in matches:
            block = match_obj.group(1).strip()
            if not block:
                continue
            lines = block.splitlines()
            target_line_content = None
            for i, line in enumerate(lines):
                if "stack traceback:" in line:
                    if i + 1 < len(lines):
                        target_line_content = lines[i + 1].strip()
                    break
            if not target_line_content:
                continue
            if target_line_content:
                match = path_line_pattern.search(target_line_content)
                if match:
                    path = match.group(1)
                    line_num = int(match.group(2))
                    error_detail = block
                    path = self.__fix_path(path)
                    errors.append({
                        "file": path,
                        "line_number": line_num,
                        "error": error_detail,
                        'reference_need': True
                    })
                    # 记录匹配的位置
                    matched_positions.append((match_obj.start(), match_obj.end()))

        return matched_positions
    
    def extract_rule3(self, errors: List[Any], content: str, encoding: str):
        """
        提取包含'ERROR'的'KGLOG_PROCESS_ERROR(nTopIndex == X)'中的数字X和函数名

        示例日志:
        20260412-234227,019<ERROR:06101>: KGLOG_PROCESS_ERROR(nTopIndex == 3) at line 3642 in int KCharacter::LuaIsHaveBuffByOwner(lua_State*)
        20260412-234227,019<ERROR:06101>: KGLOG_PROCESS_ERROR(nTopIndex == 2) at line 3642 in bool playser::LuaIsOK(lua_State*)
        20260412-234227,019<ERROR:06101>: KGLOG_PROCESS_ERROR(nTopIndex == 2) at line 3642 in void playser::LuaIsFailed(lua_State*, int)

        提取结果:
        第一个示例: {"expected_params": "3", "line_number": 3642, "class_name": "KCharacter", "function_name": "IsHaveBuffByOwner"}
        第二个示例: {"expected_params": "2", "line_number": 3642, "class_name": "playser", "function_name": "IsOK"}
        第三个示例: {"expected_params": "2", "line_number": 3642, "class_name": "playser", "function_name": "IsFailed"}
        """
        # 匹配包含ERROR的KGLOG_PROCESS_ERROR错误
        # 使用更灵活的正则表达式处理各种空格变化
        # 支持多种参数类型: (lua_State*), (lua_State*, int), 或其他类型
        # 支持多种返回类型: int, bool, void 等
        error_pattern = re.compile(
            r'\d{8}-\d{6},\d{3}<ERROR:[^>]+>:\s*KGLOG_PROCESS_ERROR\s*\(\s*nTopIndex\s*==\s*(\d+)\s*\).*?at\s+line\s+(\d+).*?in\s+\w+\s+(\w+)::Lua(\w+)\s*\([^)]*\)',
            re.IGNORECASE | re.DOTALL
        )

        # 使用finditer获取匹配对象，包括位置信息
        matches = list(error_pattern.finditer(content))
        matched_positions = []  # 记录匹配位置 (start, end)

        for match_obj in matches:
            expected_params = match_obj.group(1)  # 提取的数字
            line_num = match_obj.group(2)      # 提取的行号
            class_name = match_obj.group(3)       # 提取的类名
            function_name = match_obj.group(4)    # 提取的函数名

            errors.append({
                "expected_params": int(expected_params),
                "line_num": int(line_num),
                "class_name": class_name,
                "function_name": function_name
            })
            # 记录匹配的位置
            matched_positions.append((match_obj.start(), match_obj.end()))

        return matched_positions

    def extract_rule4(self, errors: List[Any], content: str, encoding: str, K: int = 5):
        error_pattern = re.compile(
            r'\d{8}-\d{6},\d{3}<(ERROR|DEBUG|INFO|WARN):[^>]+>:\s*KGLOG_PROCESS_ERROR\([^)]+\)\s+at\s+line\s+(\d+)\s+in\s+\w+\s+(\w+)::([^\(]+)\s*\([^)]*\)',
            re.IGNORECASE | re.DOTALL
        )
        matches = list(error_pattern.finditer(content))
        matched_positions = []
        lines = content.splitlines()

        for match_obj in matches:
            log_level = match_obj.group(1)  # 日志级别：ERROR、DEBUG等
            line_num = match_obj.group(2)   # 行号
            class_name = match_obj.group(3)  # 类名
            func_name = match_obj.group(4)  # 函数名
            full_match = match_obj.group(0)  # 完整匹配
            if "at line 37 in BOOL KIndividualDropList::Init(char*)" in full_match:
                tt = 0
                tt += 1
            if "nTopIndex" in full_match and func_name.startswith("Lua"):
                continue

            full_func_name = f"{class_name}::{func_name}"
            error_start = full_match.find("KGLOG_PROCESS_ERROR(")
            relative_paths = []
            flag = False

            if error_start != -1:
                error_end = full_match.find(") at line", error_start)
                if error_end != -1:
                    error_msg = full_match[error_start:error_end + 1]
                else:
                    error_msg = "KGLOG_PROCESS_ERROR(...)"

                match_start = match_obj.start()
                text_before_match = content[:match_start]
                cur_line_num = text_before_match.count('\n')

                start_line = max(0, cur_line_num - K)
                end_line = min(len(lines), cur_line_num + K)
                for i in range(start_line, end_line):
                    if i == cur_line_num:
                        continue
                    line = lines[i]
                    # [KIndividualDropList] Failed to open file "xxx.tab" !
                    failed_open_pattern = r'Failed to open file\s+"([^"]+\.[a-zA-Z0-9]+)"\s*!'
                    # 包含常见文件扩展名的路径模式
                    common_extensions = ['lua', 'tab', 'txt', 'csv', 'json', 'xml', 'ini', 'cfg', 'dat']
                    ext_pattern = r'([^"\s]+\.(?:' + '|'.join(common_extensions) + '))'
                    patterns = [failed_open_pattern, ext_pattern]
                    flag = False
                    for pattern in patterns:
                        for sub_match in re.finditer(pattern, line, re.IGNORECASE):
                            match_path = sub_match.group(1)
                            normalized_path = match_path.replace("\\", "/")
                            # 过滤掉不像是路径的匹配（太短或包含非法字符）
                            if len(normalized_path) > 5 and '.' in normalized_path and not any(char in normalized_path for char in self.invalid_path_chars):
                                clean_path = self.__get_valid_path(normalized_path, encoding)
                                if clean_path and clean_path not in relative_paths:
                                    relative_paths.append(clean_path)
                                    flag = True
                                    # 从 match_start 偏移定位当前行
                                    line_start = match_start
                                    delta = i - cur_line_num
                                    if delta > 0:
                                        for _ in range(delta):
                                            line_start = content.index('\n', line_start) + 1
                                    elif delta < 0:
                                        for _ in range(-delta):
                                            line_start = content.rindex('\n', 0, line_start - 1) + 1
                                    matched_positions.append((line_start + sub_match.start(), line_start + sub_match.end()))
                                    break
                        if flag:
                            break
                    if flag:
                        break
            else:
                error_msg = "KGLOG_PROCESS_ERROR(...)"
            errors.append({
                "func_name": full_func_name,
                "line_num": int(line_num),
                "error_msg": error_msg,
                "relative_paths": relative_paths  # 添加提取的相对路径
            })
            matched_positions.append((match_obj.start(), match_obj.end()))
        return matched_positions

    def extract_rule_else(self, errors: List[Any], content: str, encoding: str, K: int = 5):
        """提取规则1-4未覆盖的剩余 ERROR 行."""
        catchall_pattern = re.compile(
            r'\d{8}-\d{6},\d{3}<ERROR:\d+>:\s*(.*?)(?=\d{8}-\d{6},\d{3}<|$)',
            re.DOTALL
        )
        matched_positions = []
        for match_obj in catchall_pattern.finditer(content):
            errors.append({"content": match_obj.group(1)})
            matched_positions.append((match_obj.start(), match_obj.end()))
        return matched_positions
    
    def get_unique_errors(self, script_base_dir: str, errors: List[Dict], encoding: str) -> Any:
        (lua_result, lua_count) = self._get_lua_unique_errors(script_base_dir, errors["lua"], encoding)
        (lua_call_result, lua_call_count) = self._get_lua_call_unique_errors(script_base_dir, errors["lua_call"], encoding)
        (tab_load_result, tab_load_count) = self._get_tab_load_unique_errors(script_base_dir, errors["tab_load"], encoding)
        (else_result, else_count) = self._get_else_unique_errors(errors.get("else", []))
        result = {
            "lua": lua_result,
            "lua_call": lua_call_result,
            "tab_load": tab_load_result,
            "else": else_result
        }
        count = lua_count + lua_call_count + tab_load_count + else_count
        return (result, count)
    
    def _get_lua_unique_errors(self, script_base_dir: str, errors: List[Dict], encoding: str) -> Any:
        results: Dict[str, Dict[int, List[str]]] = {}
        result_count = 0
        for item in errors:
            current_path = item.get("file")
            line_num = item.get("line_number")
            error_msg = item.get("error")
            reference_need = item.get('reference_need')
            if not current_path or line_num == 0:
                continue
            target_paths = self.__get_valid_paths(script_base_dir, current_path, encoding)
            for real_file_path in target_paths:
                target_key = real_file_path
                existing_key = None
                for k in results.keys():
                    if target_key.startswith(k):
                        results[target_key] = results.pop(k)
                        existing_key = target_key
                        break
                    elif k.startswith(target_key):
                        existing_key = k
                        break
                if existing_key:
                    target_key = existing_key
                elif target_key not in results:
                    results[target_key] = {}
                else:
                    pass

                if line_num not in results[target_key]:
                    results[target_key][line_num] = {
                        "error": []
                    }
                error_exist = False
                line_error = results[target_key][line_num]
                for error_data in line_error['error']:
                    if error_msg in error_data:
                        error_exist = True
                        break
                if error_exist is False:
                    line_error['error'].append(error_msg)
                    line_error['reference_need'] = reference_need
                    result_count += 1
        return (results, result_count)
    
    def _get_lua_call_unique_errors(self, script_base_dir: str, errors: List[Dict], encoding: str) -> Any:
        results: Dict[str, Dict[int, List[str]]] = {}
        result_count = 0
        for item in errors:
            class_name = item.get("class_name")
            function_name = item.get("function_name")
            line_num = item.get("line_num")
            expected_params = item.get('expected_params')
            if not function_name or line_num == 0:
                continue
            class_result = None
            if class_name not in results:
                results[class_name] = {}
            class_result = results[class_name]
            if function_name not in class_result:
                class_result[function_name] = {}
            function_result = class_result[function_name]
            if line_num not in function_result:
                function_result[line_num] = {
                    "expected_params": expected_params
                }
            result_count += 1
        return (results, result_count)
    
    def _get_tab_load_unique_errors(self, script_base_dir: str, errors: List[Dict], encoding: str) -> Any:
        results: Dict[str, Dict[int, Dict]] = {}
        result_count = 0
        for item in errors:
            func_name = item.get("func_name")
            line_num = item.get("line_num")
            error_msg = item.get('error_msg')
            relative_paths = item.get('relative_paths', [])
            if not func_name or line_num == 0:
                continue
            if func_name not in results:
                results[func_name] = {}
            function_result = results[func_name]
            if line_num not in function_result:
                function_result[line_num] = {
                    "error_msgs": [],
                    "relative_paths": set()  # 使用set避免重复
                }
            line_data = function_result[line_num]
            if error_msg not in line_data["error_msgs"]:
                line_data["error_msgs"].append(error_msg)
                # 添加相对路径
                for path in relative_paths:
                    line_data["relative_paths"].add(path)
                result_count += 1

        # 将set转换回list
        for func_name in results:
            for line_num in results[func_name]:
                results[func_name][line_num]["relative_paths"] = list(results[func_name][line_num]["relative_paths"])

        return (results, result_count)

    def _get_else_unique_errors(self, errors: List[Dict]) -> Any:
        results = []
        count = 0
        seen = set()
        for item in errors:
            content = item.get("content", "")
            if content and content not in seen:
                seen.add(content)
                results.append(content)
                count += 1
        return (results, count)

    def save_remain_log(self, else_result: list, encoding: str) -> str:
        """将 unique_errors['else'] 存入 .temporary_results/ 目录."""
        output_dir = os.path.join(os.getcwd(), ".temporary_results")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        file_path = os.path.join(output_dir, f"temporary_else_{timestamp}.json")
        try:
            self.json_parser.write_to_file(else_result, file_path, ensure_ascii=False, indent=4, encoding=encoding)
            print(f"[*] else 去重结果已保存至: {file_path}")
            return file_path
        except Exception as ex:
            print(f"[!] 保存 else 结果失败: {ex}")
            return ""

    def __fix_path(self, current_path: str) -> str:
        normalized_path = current_path.replace("\\", "/")
        allowed_prefixes = ["center_scripts", "battlefield_scripts", "arena_scripts"]
        is_valid_start = any(normalized_path.startswith(prefix) for prefix in allowed_prefixes)
        if is_valid_start:
            return os.path.join("server", normalized_path).replace("\\", "/")
        else:
            return os.path.join("client", normalized_path).replace("\\", "/")
    
    def __get_valid_paths(self, script_base_dir: str, rel_path: str, encoding: str) -> List[str]:
        results: List[str] = []
        clean_path = self.__get_valid_path(rel_path, encoding)
        full_partial_path = os.path.join(script_base_dir, clean_path)
        if os.path.isfile(full_partial_path):
            results.append(full_partial_path)
        elif os.path.isdir(full_partial_path):
            pattern = glob.escape(full_partial_path) + "/**/*"
            found_files = glob.glob(pattern, recursive=True)
            results = [f for f in found_files if os.path.isfile(f)]
        else:
            dir_pattern = glob.escape(full_partial_path) + "*"
            potential_path_list = glob.glob(dir_pattern)
            for matched_path in potential_path_list:
                if os.path.isdir(matched_path):
                    file_pattern = glob.escape(matched_path) + "/**/*"
                    found_files = glob.glob(file_pattern, recursive=True)
                    results.extend([f for f in found_files if os.path.isfile(f)])
                else:
                    results.append(matched_path)
        if results:
            results = [path.replace("\\", "/") for path in results]
        return results
    
    def __get_valid_path(self, rel_path: str, encoding: str) -> str:
        clean_path = rel_path
        while clean_path:
            try:
                clean_path.encode(encoding)
                if clean_path.endswith('.') or any(char in clean_path for char in self.invalid_path_chars):
                    clean_path = clean_path[:-1]
                    continue
                break
            except UnicodeEncodeError:
                clean_path = clean_path[:-1]
        return clean_path

    def __remove_matches_by_positions(self, content: str, positions: List[Tuple[int, int]]) -> str:
        """
        根据位置列表从字符串中移除匹配的内容

        Args:
            content: 原始字符串
            positions: 位置列表，每个元素是(start, end)元组

        Returns:
            移除匹配内容后的新字符串
        """
        if not positions:
            return content

        # 按起始位置排序
        sorted_positions = sorted(positions, key=lambda x: x[0])

        # 构建新字符串
        result_parts = []
        last_end = 0

        for start, end in sorted_positions:
            # 添加前一个匹配之后到当前匹配之前的内容
            if start > last_end:
                result_parts.append(content[last_end:start])
            # 跳过当前匹配的内容
            last_end = end

        # 添加最后一个匹配之后的内容
        if last_end < len(content):
            result_parts.append(content[last_end:])

        return ''.join(result_parts)