#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从C/C++源代码中提取函数名和函数体，输出为JSON格式
支持三种函数名格式：
1. KCoinShop::KCoinShopVoucherSettings::LoadVoucherSettings (嵌套类)
2. KCoinShopVoucherSettings_vk::LoadVoucherSettings (普通类)
3. DynamicLoadVoucherSettings (全局函数)

支持命名空间跟踪，包括宏定义的命名空间。
"""

import re
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import threading
from skills.skill_base import SkillBase

class CppFunctionExtractorBase(SkillBase):
    """C/C++函数提取器 - 支持命名空间跟踪"""

    def __init__(self, config_path: str):
        super().__init__(config_path)
        self.cpp_source = self.config["cpp_source"]
        self.functions: Dict[str, Any] = {}  # 函数名 -> 函数体
        self.macros = {
            "global": {},
            "local": {}
        }
        self.processed_files: List[str] = []
        self.failed_files: List[str] = []
        self.file_lock = threading.Lock()  # 线程锁，用于保护共享状态
        self.data_lock = threading.Lock()  # 线程锁，用于保护共享状态

        # 常见的命名空间宏定义
        self.namespace_macros = {
            'NAMESPACE_COIN_SHOP_BEGIN': 'KCoinShop',
            'NAMESPACE_COIN_SHOP_END': '',
            # 可以添加更多宏定义
        }

        # 匹配函数签名的正则表达式
        self.func_signature_pattern = re.compile(
            r'^\s*'  # 起始空格
            r'(?:'  # 开始非捕获组：返回类型
            r'(?:[\w:<>*&,\s]+(?:\s+const\s*)?\s+)'  # 返回类型
            r')?'  # 返回类型可选（构造函数/析构函数）
            r'(?!switch\s*\()'  # 排除switch
            r'(?!if\s*\()'  # 排除if
            r'(?!while\s*\()'  # 排除while
            r'(?!for\s*\()'  # 排除for
            r'(?!case\s*\()'  # 排除case
            r'(?!return\s*\()'  # 排除return
            r'(?!break\s*\()'  # 排除break
            r'(?!continue\s*\()'  # 排除continue
            r'(?!goto\s*\()'  # 排除goto
            r'(?!sizeof\s*\()'  # 排除sizeof
            r'(?!KGLOG_PROCESS_ERROR\s*\()'  # 排除KGLOG_PROCESS_ERROR宏
            r'(?!KG_PROCESS_ERROR\s*\()'  # 排除KG_PROCESS_ERROR宏
            r'('  # 开始捕获组1：完整的函数标识符
            r'(?:~\w+|\w+(?:<[^>]+>)?)'  # 函数名，支持析构函数或模板函数
            r'(?:::(?:~\w+|\w+(?:<[^>]+>)?))*'  # 零个或多个::函数名，支持析构函数
            r')'  # 结束捕获组1
            r'\s*'  # 空格
            r'\('  # 左括号
        )

        # 匹配命名空间定义（支持换行）
        self.namespace_pattern = re.compile(r'^\s*namespace\s+(\w+)')

        # 匹配类/结构体定义
        self.class_pattern = re.compile(r'^\s*(?:template\s*<[^>]+>\s*)?(?:class|struct)\s+(\w+)')

        # 匹配命名空间宏
        self.namespace_macro_pattern = re.compile(r'^\s*(\w+)_BEGIN\b')

        # 匹配函数调用，包括成员函数调用
        self.function_call_pattern = re.compile(
            r'(\w+(?:::\w+)*)\s*\([^)]*\)'  # 匹配 函数名(参数) 或 类名::函数名(参数)
        )

        # 匹配宏变量定义（基础版本）
        # 格式1: #define MACRO_NAME value
        # 格式2: #define MACRO_NAME (value)  带括号的值
        # 格式3: #define type MACRO_NAME value  带类型声明
        # 格式4: #define type MACRO_NAME (value)  带类型和括号值
        # 注释在函数中处理
        # 常见的C/C++类型关键字和类型后缀
        self.cpp_type_keywords = {
            'int', 'char', 'short', 'long', 'float', 'double', 'bool', 'void',
            'unsigned', 'signed', 'const', 'static', 'extern', 'auto'
        }

        # 构建类型前缀的正则表达式部分
        # 匹配以类型关键字结尾或以 _t 结尾的序列
        type_keyword_pattern = '|'.join(sorted(self.cpp_type_keywords, key=len, reverse=True))
        # 类型可以是: 1) 标准类型关键字, 2) 以 _t 结尾的类型
        # 后面可以跟指针/引用，然后再跟可选的标识符
        type_prefix_pattern = rf'(?:(?:{type_keyword_pattern}|(?:\w+_t))(?:\s*(?:\*+|&+)\s*)?(?:\s+\w+)?\s+)+'

        self.macro_definition_pattern = re.compile(
            rf'^\s*#\s*define\s+({type_prefix_pattern})?(\w+)\s+(.*?)\s*$'  # 捕获可能的类型前缀、宏名和值
        )

    def _is_cpp_file(self, file_path: str, check_exists: bool = False, check_content: bool = False) -> bool:
        """检查是否是C/C++文件

        Args:
            file_path: 文件路径
            check_exists: 是否检查文件是否存在 (默认: False)
            check_content: 是否检查文件内容 (默认: False)

        Returns:
            True如果是C/C++文件，否则False
        """
        # 常见的C/C++文件扩展名
        cpp_extensions = {
            '.cpp', '.cc', '.cxx', '.c++', '.cp',  # C++源文件
            '.c',                                  # C源文件
            '.h', '.hh', '.hpp', '.hxx', '.h++', '.hp',  # C/C++头文件
            '.inl',                                # 内联文件
            '.ipp',                                # 内联实现文件
            '.tcc', '.tpp',                        # 模板实现文件
            '.m', '.mm',                           # Objective-C/C++文件 (Mac/iOS)
            '.cu', '.cuh',                         # CUDA文件
            '.cl',                                 # OpenCL文件
        }

        # 获取文件扩展名并转为小写
        path_obj = Path(file_path)
        extension = path_obj.suffix.lower()

        # 检查扩展名
        if extension in cpp_extensions:
            # 扩展名匹配，进行进一步检查（如果需要）
            if check_exists:
                if not path_obj.exists():
                    return False
                if not path_obj.is_file():
                    return False

            if check_content and path_obj.exists():
                # 简单的内容检查：尝试读取文件，检查是否包含C/C++关键字
                try:
                    # 只读取前几KB来检查
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read(4096)

                    # 检查常见的C/C++关键字
                    cpp_keywords = {'#include', 'int', 'void', 'class', 'struct', 'namespace',
                                    'template', 'typedef', 'using', 'const', 'static', 'extern'}

                    # 如果有任何C++关键字，认为是C++文件
                    for keyword in cpp_keywords:
                        if keyword in content:
                            return True

                    # 如果没有找到关键字，但扩展名匹配，仍然返回True
                    # （因为可能是空文件或只有注释的文件）
                except (IOError, UnicodeDecodeError):
                    # 读取失败，但扩展名匹配，所以还是返回True
                    pass

            return True

        # 检查是否有特殊文件扩展名或无扩展名但有C/C++内容
        if check_content and path_obj.exists() and path_obj.is_file():
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(4096)

                # 检查文件内容是否包含C/C++特有的模式
                # 1. 包含 #include
                # 2. 包含 main 函数签名
                # 3. 包含 class/struct 定义
                cpp_patterns = [
                    r'^\s*#\s*include\s+[<"]',
                    r'^\s*int\s+main\s*\(',
                    r'^\s*class\s+\w+',
                    r'^\s*struct\s+\w+',
                    r'^\s*namespace\s+\w+',
                ]

                for pattern in cpp_patterns:
                    if re.search(pattern, content, re.MULTILINE):
                        return True
            except (IOError, UnicodeDecodeError):
                pass

        return False
        

    def _extract_macro_from_line(self, line: str) -> Optional[Tuple[str, Optional[str], str]]:
        if "BUILD_BF_MAP_TYPE_MAP" in line:
            tt = 0
            tt += 1
        clean_line = line
        if '//' in clean_line:
            clean_line = clean_line.split('//')[0]

        # 移除行尾空白
        clean_line = clean_line.rstrip()

        # 检查是否是带参数的宏（函数宏），如果是则跳过
        # 真正的带参数宏应该是: #define MACRO(param1, param2) value
        # 使用更精确的匹配，检查括号内是否有逗号或字母（参数）
        # 或者宏名后面直接跟着括号（没有空格）
        if re.search(r'#\s*define\s+\w+\([^)]*[a-zA-Z_][^)]*\)', clean_line):
            return None
        # 也检查宏名后面直接跟着左括号（没有空格）
        if re.search(r'#\s*define\s+\w+\(', clean_line):
            return None

        match = self.macro_definition_pattern.match(clean_line)
        if not match:
            return None

        type_prefix = match.group(1)  # 可能的类型前缀，如 "int " 或 "const char* "
        macro_name = match.group(2)
        macro_value = match.group(3)

        # 检查是否有值（macro_value 不应该为空）
        if not macro_value or macro_value.isspace():
            return None

        # 处理类型前缀
        macro_type = None
        if type_prefix:
            type_prefix = type_prefix.strip()
            # 检查类型前缀是否包含C++类型关键字
            cpp_keywords = {
                'int', 'char', 'short', 'long', 'float', 'double', 'bool', 'void',
                'unsigned', 'signed', 'const', 'static', 'extern', 'auto'
            }
            # 检查是否以已知类型结尾
            for keyword in cpp_keywords:
                if type_prefix.endswith(keyword) or keyword in type_prefix.split():
                    macro_type = type_prefix
                    break
            # 检查是否以 _t 结尾（标准类型后缀）
            if not macro_type and (type_prefix.endswith('_t') or ' ' in type_prefix):
                macro_type = type_prefix

        if macro_type:
            # 有类型定义
            return macro_name, macro_type, macro_value.strip()
        else:
            # 没有类型定义
            return macro_name, None, macro_value.strip()

    def _is_global_scope_file(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in {'.h', '.hpp', '.hxx', '.inl'}

    def _extract_macros_from_file(self, file_path: str, encoding: str) -> None:
        try:
            for enc in [encoding, 'utf-8', 'gb2312', 'latin-1']:
                try:
                    with open(file_path, 'r', encoding=enc) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return
        except Exception:
            return

        scope = "global" if self._is_global_scope_file(file_path) else "local"
        lines = content.splitlines()

        i = 0
        while i < len(lines):
            stripped = lines[i].strip()
            if not stripped.startswith('#'):
                i += 1
                continue

            # 尝试提取多行宏
            macro_info = self._extract_multiline_macro(lines, i)
            if macro_info:
                macro_name, macro_type, macro_value, new_i = macro_info
                with self.data_lock:
                    if scope == "global":
                        self.macros[scope][macro_name] = {
                            "value": macro_value,
                            "type": macro_type if macro_type else ""
                        }
                    else:
                        if file_path not in self.macros[scope]:
                            self.macros[scope][file_path] = {}
                        self.macros[scope][file_path][macro_name] = {
                            "value": macro_value,
                            "type": macro_type if macro_type else ""
                        }
                i = new_i + 1
            else:
                i += 1

    def _extract_multiline_macro(self, lines: List[str], start_idx: int) -> Optional[Tuple[str, Optional[str], str, int]]:
        """从指定行开始提取多行宏

        Args:
            lines: 所有行的列表
            start_idx: 开始行的索引

        Returns:
            (macro_name, macro_type, macro_value, end_idx) 或 None
        """
        if start_idx >= len(lines):
            return None

        line = lines[start_idx]

        # 清理行
        clean_line = line
        if '//' in clean_line:
            clean_line = clean_line.split('//')[0]
        clean_line = clean_line.rstrip()

        # 检查是否是带参数的宏
        if re.search(r'#\s*define\s+\w+\([^)]*[a-zA-Z_][^)]*\)', clean_line):
            return None
        if re.search(r'#\s*define\s+\w+\(', clean_line):
            return None

        match = self.macro_definition_pattern.match(clean_line)
        if not match:
            return None

        type_prefix = match.group(1)
        macro_name = match.group(2)
        first_line_value = match.group(3)

        # 处理类型前缀
        macro_type = None
        if type_prefix:
            type_prefix = type_prefix.strip()
            # 检查是否以已知类型结尾
            for keyword in self.cpp_type_keywords:
                if type_prefix.endswith(keyword) or keyword in type_prefix.split():
                    macro_type = type_prefix
                    break
            # 检查是否以 _t 结尾（标准类型后缀）
            if not macro_type and (type_prefix.endswith('_t') or ' ' in type_prefix):
                macro_type = type_prefix

        # 收集多行值
        macro_value_parts = []
        current_idx = start_idx
        current_value = first_line_value

        while True:
            # 移除行尾的反斜杠（续行符）
            if current_value.endswith('\\'):
                current_value = current_value.rstrip('\\').rstrip()
                macro_value_parts.append(current_value)
                current_idx += 1
                if current_idx >= len(lines):
                    break
                # 读取下一行
                next_line = lines[current_idx]
                # 清理下一行
                clean_next_line = next_line
                if '//' in clean_next_line:
                    clean_next_line = clean_next_line.split('//')[0]
                current_value = clean_next_line.rstrip()
            else:
                # 没有续行符，这是最后一行
                macro_value_parts.append(current_value)
                break

        # 合并所有部分
        full_macro_value = ' '.join(macro_value_parts).strip()

        # 检查是否有值
        if not full_macro_value or full_macro_value.isspace():
            return None

        return macro_name, macro_type, full_macro_value, current_idx

    def _extract_macro_file_wrapper(self, file_path: str, encoding: str) -> Optional[bool]:
        try:
            self._extract_macros_from_file(file_path, encoding)
            return True
        except Exception:
            return None

    def _expand_macros_in_body(self, file_path: str, func_body: str) -> str:
        scopes = ['local', 'global']
        for scope in scopes:
            cur_micros = self.macros[scope]
            if scope == 'local':
                cur_micros = cur_micros.get(file_path, {})
            if not cur_micros:
                continue
            for macro_name, macro_info in cur_micros.items():
                if re.search(r'\b' + re.escape(macro_name) + r'\b', func_body):
                    try:
                        macro_type = macro_info.get("type", "")
                        macro_value = macro_info.get("value", "")
                        whole_macro_value = ""
                        if macro_type:
                            if macro_value and macro_value.strip():
                                whole_macro_value = f"{macro_type} {macro_value}"
                            else:
                                whole_macro_value = f"{macro_type}"
                        else:
                            whole_macro_value = f"{macro_value}"
                        func_body = re.sub(
                            r'\b' + re.escape(macro_name) + r'\b',
                            whole_macro_value,
                            func_body
                        )
                    except:
                        pass

        return func_body

    def _find_matching_brace(self, lines: List[str], start_line: int, start_col: int) -> Optional[Tuple[int, int]]:
        brace_stack = 1  # 已经有一个左大括号
        i = start_line
        j = start_col + 1  # 从左大括号后面开始

        while i < len(lines):
            line = lines[i]
            while j < len(line):
                if line[j] == '{':
                    brace_stack += 1
                elif line[j] == '}':
                    brace_stack -= 1
                    if brace_stack == 0:
                        return i, j
                j += 1
            i += 1
            j = 0
        return None

    def _process_block_start(self, data: Dict[str, Any], lines: List[str], line_idx: int) -> Tuple[bool, int]:
        """处理块开始行（命名空间、类、结构体）"""
        line = lines[line_idx]
        namespace_stack = data["namespace_stack"]
        class_stack = data["class_stack"]

        # 检查标准命名空间定义：namespace Name
        namespace_match = self.namespace_pattern.match(line)
        if namespace_match:
            namespace_name = namespace_match.group(1)
            if '{' in line:
                namespace_stack.append(namespace_name)
                return True, line_idx + 1
            else:
                for i in range(line_idx + 1, min(line_idx + 5, len(lines))):
                    if '{' in lines[i]:
                        namespace_stack.append(namespace_name)
                        return True, i + 1
                return False, line_idx + 1

        # 检查匿名命名空间：namespace {
        if line.strip().startswith('namespace {'):
            namespace_stack.append('')
            return True, line_idx + 1

        # 检查命名空间宏
        macro_match = self.namespace_macro_pattern.match(line)
        if macro_match:
            macro_name = macro_match.group(1)
            full_macro = macro_name + "_BEGIN"
            if full_macro in self.namespace_macros:
                namespace_name = self.namespace_macros[full_macro]
                if namespace_name:
                    namespace_stack.append(namespace_name)
                data["active_namespace_macro"] = full_macro
                return True, line_idx + 1
            else:
                return False, line_idx + 1

        # 检查类/结构体定义
        class_match = self.class_pattern.match(line)
        if class_match:
            class_name = class_match.group(1)
            if '{' in line:
                class_stack.append(class_name)
                return True, line_idx + 1
            else:
                for i in range(line_idx + 1, min(line_idx + 5, len(lines))):
                    if '{' in lines[i]:
                        class_stack.append(class_name)
                        return True, i + 1
                return False, line_idx + 1

        return False, line_idx + 1

    def _remove_comments_from_line(self, line: str) -> str:
        if '//' in line:
            line = line.split('//')[0]
        return line.strip()

    def _process_block_end(self, data: Dict[str, Any], line: str) -> bool:
        """处理块结束（命名空间、类、结构体）"""
        line_without_comments = self._remove_comments_from_line(line)
        namespace_stack = data["namespace_stack"]
        class_stack = data["class_stack"]

        if line_without_comments.startswith('}'):
            if class_stack:
                class_stack.pop()
            elif namespace_stack:
                namespace_stack.pop()
                data["active_namespace_macro"] = None
            return True

        if line_without_comments.endswith('_END'):
            if data["active_namespace_macro"]:
                macro_base = data["active_namespace_macro"][:-6]
                expected_end_macro = macro_base + "_END"
                if line_without_comments == expected_end_macro:
                    if namespace_stack:
                        namespace_stack.pop()
                    data["active_namespace_macro"] = None
                    return True
            return False
        return False

    def _build_full_function_name(self, data: Dict[str, Any], func_name: str) -> str:
        """构建完整的函数名，包含命名空间和类名"""
        parts = []
        namespace_stack = data["namespace_stack"]
        class_stack = data["class_stack"]

        if namespace_stack:
            parts.extend(namespace_stack)

        if class_stack:
            parts.extend(class_stack)

        parts.append(func_name)

        return '::'.join(parts) if parts else func_name

    def _contains_call(self, func_body: str, call_func_name: str) -> bool:
        clean_body = func_body

        # 移除字符串常量
        clean_body = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '', clean_body)
        clean_body = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", '', clean_body)
        # 移除单行注释
        clean_body = re.sub(r'//.*$', '', clean_body, flags=re.MULTILINE)

        return re.search(rf'{call_func_name}\s*\(', clean_body) is not None

    def _extract_function_calls(self, func_body: str, call_func_name: str) -> List[Dict[str, str]]:
        g_open_tab_file_calls = []
        call_pattern = re.compile(rf'(\w+(?:\s*\*\s*\w+)?)\s*=\s*{call_func_name}\s*\([^)]*\)\s*;')

        for match in call_pattern.finditer(func_body):
            var_name = match.group(1)
            # 清理可能的类型前缀，如ITabFile* piTabFile -> piTabFile
            if '*' in var_name:
                var_name = var_name.split('*')[-1].strip()
            elif ' ' in var_name:
                # 处理 "ITabFile* piTabFile" 或 "ITabFile *piTabFile" 或 "auto piTabFile"
                parts = var_name.split()
                var_name = parts[-1]
            g_open_tab_file_calls.append(var_name)

        if not g_open_tab_file_calls:
            return []

        # 现在查找使用这些变量作为参数的函数调用
        # 使用更稳健的方法匹配函数调用，处理字符串常量中的逗号和嵌套括号
        result = []
        i = 0
        while i < len(func_body):
            # 查找函数名和开括号
            func_match = re.search(r'(\w+(?:::\w+)*)\s*\(', func_body[i:])
            if not func_match:
                break

            func_name = func_match.group(1)
            start_pos = i + func_match.start()
            open_paren_pos = i + func_match.end() - 1  # 开括号的位置

            # 排除常见的关键字和宏
            excluded_keywords = ['if', 'while', 'for', 'switch', 'return', 'sizeof', 'new', 'delete']
            if any(func_name.startswith(kw) for kw in excluded_keywords):
                i = start_pos + len(func_name)
                continue

            # 从开括号开始，找到匹配的闭括号
            paren_count = 1
            pos = open_paren_pos + 1
            in_string = False
            string_char = None
            escaped = False

            while pos < len(func_body) and paren_count > 0:
                char = func_body[pos]

                if escaped:
                    # 当前字符被转义，忽略其特殊含义
                    escaped = False
                elif char == '\\':
                    # 遇到转义字符，标记下一个字符被转义
                    escaped = True
                elif not in_string:
                    # 不在字符串内
                    if char == '(':
                        paren_count += 1
                    elif char == ')':
                        paren_count -= 1
                    elif char == '"' or char == "'":
                        in_string = True
                        string_char = char
                elif char == string_char:
                    # 在字符串内，遇到匹配的引号（且没有被转义）
                    in_string = False
                    string_char = None

                pos += 1

            if paren_count == 0:
                # 找到了完整的函数调用
                full_call = func_body[start_pos:pos]
                # 提取参数部分（排除函数名和括号）
                params_start = open_paren_pos + 1
                params_end = pos - 1
                params_str = func_body[params_start:params_end]

                # 检查参数中是否包含g_OpenTabFile返回的变量
                for var_name in g_open_tab_file_calls:
                    # 使用正则表达式确保匹配整个单词
                    pattern = re.compile(r'\b' + re.escape(var_name) + r'\b')
                    if pattern.search(params_str):
                        result.append({
                            "func_name": func_name,
                            "full_call": full_call,
                            "param_var": var_name
                        })
                        break  # 找到匹配就跳出

                i = pos
            else:
                i = start_pos + 1

        # 去重
        unique_result = []
        seen = set()
        for item in result:
            key = (item["func_name"], item["full_call"])
            if key not in seen:
                seen.add(key)
                unique_result.append(item)

        return unique_result

    def _extract_function(self, lines: List[str], line_idx: int) -> Tuple[Optional[str], Optional[str], int, int]:
        if line_idx >= len(lines):
            return None, None, line_idx, line_idx

        line = lines[line_idx]

        # 检查是否是 template<> 行
        template_line = False
        current_line_idx = line_idx
        current_line = line

        # 检查当前行是否是单独的 template<> 行
        if line.strip() == 'template<>':
            if current_line_idx + 1 < len(lines):
                current_line_idx += 1
                current_line = lines[current_line_idx]
                template_line = True
            else:
                return None, None, line_idx, line_idx

        match = self.func_signature_pattern.match(current_line)
        if not match:
            if template_line == False and current_line.strip().startswith('template<>'):
                template_end = current_line.find('>')
                if template_end != -1 and template_end + 1 < len(current_line):
                    remaining = current_line[template_end + 1:].lstrip()
                    # 检查剩余部分是否匹配函数签名
                    match = self.func_signature_pattern.match(remaining)
                    if not match:
                        return None, None, line_idx, line_idx
                else:
                    return None, None, line_idx, line_idx
            else:
                return None, None, line_idx, line_idx

        full_func_name = match.group(1)

        # 查找完整的参数列表（包括模板参数）
        # 我们需要从当前行开始，找到函数签名的结束位置（找到 ')' 且没有匹配的 '('）
        signature_start_idx = current_line_idx
        signature_end_idx = signature_start_idx

        # 首先找到函数签名开始的字符位置
        # 找到 '(' 的位置，从那里开始计数括号
        signature_start_line = current_line_idx
        signature_start_col = current_line.find('(')

        if signature_start_col == -1:
            # 如果没有找到 '('，可能是多行函数签名，查找下一个包含 '(' 的行
            for i in range(current_line_idx, min(current_line_idx + 10, len(lines))):
                if '(' in lines[i]:
                    signature_start_line = i
                    signature_start_col = lines[i].find('(')
                    break

        if signature_start_col == -1:
            return None, None, line_idx, line_idx

        # 查找匹配的 ')' 作为函数签名的结束
        paren_count = 1
        current_line = signature_start_line
        current_col = signature_start_col + 1

        # 处理括号匹配，跳过字符串中的括号
        in_string = False
        string_char = None
        escaped = False

        while current_line < len(lines):
            line_content = lines[current_line]

            while current_col < len(line_content):
                char = line_content[current_col]

                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif not in_string:
                    if char == '(':
                        paren_count += 1
                    elif char == ')':
                        paren_count -= 1
                        if paren_count == 0:
                            signature_end_idx = current_line
                            break
                    elif char == '"' or char == "'":
                        in_string = True
                        string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None

                current_col += 1

            if paren_count == 0:
                break

            current_line += 1
            current_col = 0

        if paren_count != 0:
            return None, None, line_idx, line_idx

        # 查找函数体开始的左大括号
        brace_start_line = signature_end_idx
        brace_start_col = -1

        # 从函数签名结束位置开始查找 '{'
        for i in range(signature_end_idx, min(signature_end_idx + 10, len(lines))):
            if '{' in lines[i]:
                brace_start_line = i
                brace_start_col = lines[i].find('{')
                break

        if brace_start_col == -1:
            return None, None, line_idx, line_idx

        # 查找匹配的右大括号
        brace_match = self._find_matching_brace(lines, brace_start_line, brace_start_col)
        if not brace_match:
            return None, None, line_idx, line_idx

        end_line, end_col = brace_match

        # 提取完整的函数定义（从函数签名开始到函数体结束）
        # 首先构建完整的函数签名
        signature_lines = []

        # 如果前面有单独的 template<> 行，包含它
        if template_line:
            signature_lines.append(lines[current_line_idx - 1])  # template<> 行

        if current_line_idx == signature_end_idx:
            # 函数签名在同一行
            signature_lines.append(lines[current_line_idx])
        else:
            # 多行函数签名
            for i in range(current_line_idx, signature_end_idx + 1):
                signature_lines.append(lines[i])

        # 现在构建完整的函数定义
        if brace_start_line == end_line:
            # 函数体在同一行
            if brace_start_line > signature_end_idx:
                # 函数体在签名之后的新行
                full_definition = '\n'.join(signature_lines) + '\n' + lines[brace_start_line][brace_start_col:end_col + 1]
            else:
                # 函数签名和函数体在同一行
                # 我们需要确保不重复添加函数体
                if line_idx == signature_end_idx:
                    # 整个函数定义在同一行
                    full_definition = '\n'.join(signature_lines)
                else:
                    # 多行签名，但函数体在签名行
                    # 这种情况比较少见，但需要处理
                    full_definition = '\n'.join(signature_lines)
        else:
            # 多行函数体
            definition_lines = signature_lines.copy()
            definition_lines.append(lines[brace_start_line][brace_start_col:])

            for i in range(brace_start_line + 1, end_line):
                definition_lines.append(lines[i])

            definition_lines.append(lines[end_line][:end_col + 1])
            full_definition = '\n'.join(definition_lines)

        # 更新起始行号（函数定义的第一行）
        # 如果有单独的 template<> 行，起始行是 template<> 行
        start_line = current_line_idx - 1 if template_line else current_line_idx

        return full_func_name, full_definition, start_line, end_line

    def _rebuild_func_body(self, func_body: str, start_line: int) -> str:
        """重建函数体，移除行号前缀"""
        lines = func_body.split('\n')
        clean_lines = []
        for i, line in enumerate(lines):
            line = line.strip()
            clean_lines.append(f"{start_line + i + 1}: {line}")
        return '\n'.join(clean_lines)
    
    def _extract_functions_from_file(self, file_path: str, encoding: str = 'gbk') -> int:
        count = 0
        final_encoding = encoding
        file_path = file_path.replace('\\', '/')
        call_set = set()

        # file_path = 'i:/SVN/trunk/Sword3/Source/Server/SO3BattlefieldServer/KBattleFieldMgr.cpp'
        if not self._is_cpp_file(file_path, check_exists=True):
            with self.file_lock:
                self.failed_files.append(f"{file_path} (不是C/C++文件)")
            return 0

        try:
            for enc in [encoding, 'utf-8', 'gb2312', 'latin-1']:
                try:
                    with open(file_path, 'r', encoding=enc) as f:
                        content = f.read()
                    final_encoding = enc
                    break
                except UnicodeDecodeError:
                    continue
            else:
                with self.file_lock:
                    self.failed_files.append(f"{file_path} (编码错误)")
                return 0

        except Exception as e:
            with self.file_lock:
                self.failed_files.append(f"{file_path} (读取错误: {e})")
            return 0

        # 按行分割
        lines = content.splitlines()
        data = {
            "namespace_stack": [],
            "class_stack": [],
            "active_namespace_macro": None,
        }

        # 先收集当前文件中所有的函数
        all_functions_in_file = {}
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                i += 1
                continue
            processed, new_line_idx = self._process_block_start(data, lines, i)
            if processed:
                i = new_line_idx
                continue
            if self._process_block_end(data, line):
                i += 1
                continue
            if stripped.startswith('#') or stripped.startswith('//'):
                i += 1
                continue

            func_name, func_body, start_line, end_line = self._extract_function(lines, i)
            if func_name and func_body:
                full_func_name = self._build_full_function_name(data, func_name)
                all_functions_in_file[full_func_name] = {
                    "func_name": func_name,
                    "func_body": func_body,
                    "start_line": start_line
                }
                i = end_line + 1
            else:
                i += 1

        data = {
            "namespace_stack": [],
            "class_stack": [],
            "active_namespace_macro": None,
        }
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if not stripped:
                i += 1
                continue
            processed, new_line_idx = self._process_block_start(data, lines, i)
            if processed:
                i = new_line_idx
                continue
            if self._process_block_end(data, line):
                i += 1
                continue
            if stripped.startswith('#') or stripped.startswith('//'):
                i += 1
                continue
            func_name, func_body, start_line, end_line = self._extract_function(lines, i)
            if func_name and func_body:
                if self._contains_call(func_body, "g_OpenTabFile"):
                    count += self._extract_relative_funcs(file_path, final_encoding, encoding, "g_OpenTabFile", func_name, func_body, start_line, all_functions_in_file, call_set)
                i = end_line + 1
            else:
                i += 1
        return count
    
    def _extract_relative_funcs(self, file_path: str, final_encoding: str, encoding: str, call_name: str, func_name: str, func_body: str, start_line: int, all_functions_in_file: Any, call_set: set) -> int:
        count = 0
        function_calls = self._extract_function_calls(func_body, call_name)
        call_funcs = []

        for call_info in function_calls:
            called_func = call_info["func_name"]
            for stored_func_name, stored_func_info in all_functions_in_file.items():
                if stored_func_name.endswith("::" + called_func) or stored_func_name == called_func:
                    if stored_func_name in call_set:
                        continue
                    call_set.add(stored_func_name)
                    new_func_body = self._rebuild_func_body(stored_func_info["func_body"], stored_func_info["start_line"])
                    call_funcs.append({
                        "func_name": stored_func_name,
                        "func_body": new_func_body,
                    })

        # if final_encoding.lower() != encoding.lower():
        #     try:
        #         new_func_body = new_func_body.encode(final_encoding, errors='ignore').decode(encoding, errors='ignore')
        #     except:
        #         pass
        with self.data_lock:
            new_func_body = self._rebuild_func_body(func_body, start_line)
            new_func_body = self._expand_macros_in_body(file_path, new_func_body)
            if func_name not in self.functions:
                self.functions[func_name] = {
                    "path": [],
                    "func_body": new_func_body
                }
            self.functions[func_name]["path"].append(file_path)
            count += 1
            for call_func in call_funcs:
                call_func_name = call_func["func_name"]
                call_func_body = self._expand_macros_in_body(file_path, call_func["func_body"])
                if call_func_name not in self.functions:
                    self.functions[call_func_name] = {
                        "path": [],
                        "func_body": call_func_body
                    }
                self.functions[call_func_name]["path"].append(file_path)
                count += 1
        return count

    def _extract_file_wrapper(self, file_path: str, encoding: str) -> Optional[Tuple[int, bool]]:
        """线程安全的文件提取包装器"""
        try:
            count = self._extract_functions_from_file(file_path, encoding)
            return count, True
        except Exception as ex:
            with self.file_lock:
                self.failed_files.append(f"{file_path} (处理错误: {ex})")
            return 0, False