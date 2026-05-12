import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from datetime import datetime
from typing import Any, List, Dict

class LuaCallFinder:
    def __init__(self):
        pass
    
    def find(self, unique_errors: Dict[str, Dict[int, List[str]]], script_dirs: list[str], encoding: str, max_workers: int) -> List[Dict]:
        result = []
        tasks = []
        for script_dir in script_dirs:
            tasks.extend(self._get_all_script_files(script_dir))
        total_tasks = len(tasks)
        if total_tasks == 0:
            return result
        
        current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{current_time}] 开始并行处理 {len(tasks)} 个任务，线程池大小: {max_workers}")

        progress_lock = threading.Lock()
        with tqdm(total=total_tasks, desc="查找函数调用", unit="task") as pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {
                    executor.submit(
                        self._process_file,
                        result,
                        unique_errors,
                        task,
                        encoding,
                        pbar,
                        progress_lock
                    ): task for task in tasks
                }
                for future in as_completed(future_to_task):
                    file_path = future_to_task[future]
                    try:
                        future.result()
                    except Exception as ex:
                        current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        print(f"[{current_time}] 文件 {file_path} 处理失败: {ex}")
        return result
    
    def _get_all_script_files(self, script_base_dir: str) -> List[str]:
        script_files = []
        for root, dirs, files in os.walk(script_base_dir):
            for file in files:
                if file.endswith('.lua'):
                    script_files.append(os.path.join(root, file))
        return script_files
    
    def _process_file(self, reslt: list[Dict], input_data: Any, file_path: str, encoding: str, pbar: tqdm, progress_lock: threading.Lock):
        try:
            current_result = []
            with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                content = f.read()
            
            lines = content.splitlines()
            for line_num, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                for class_name, class_result in input_data.items():
                    for function_name, function_result in class_result.items():
                        if function_name not in line:
                            continue
                        if re.match(r'^\s*--', line): 
                            continue
                        for c_line_num, item in function_result.items():
                            exact_patterns = [
                                rf'\s*{function_name}\s*\((.*?)\)',
                            ]
                            found_match = False
                            params_str = ""
                            for pattern in exact_patterns:
                                match = re.search(pattern, line)
                                if match:
                                    params_str = match.group(1).strip()
                                    found_match = True
                                    break
                            if found_match:
                                actual_params = self._count_params(params_str)
                                expected_params = item["expected_params"]
                                if actual_params != expected_params:
                                    error_msg = f"{function_name}希望{expected_params}个参数，结果发现{actual_params}个参数"
                                    result = {
                                        "file_path": file_path.replace('\\', '/'),
                                        "line_num": line_num + 1,
                                        "line_content": line,
                                        "error": error_msg
                                    }
                                    current_result.append(result)
        except Exception as ex:
            raise Exception(f"处理文件 {file_path} 时出错: {ex}")
        finally:
            with progress_lock:
                pbar.update(1)
                reslt.extend(current_result)
    
    def _count_params(self, params_str: str) -> int:
        if not params_str:
            return 0
        
        params_str = params_str.strip()
        if params_str == "":
            return 0
        
        # 计算参数个数（通过逗号分隔，但需要考虑嵌套函数调用等情况）
        # 这里使用简单的方法：统计逗号数量+1
        # 更复杂的实现需要考虑字符串、表、函数调用等
        params = []
        current_param = ""
        paren_depth = 0
        brace_depth = 0
        in_string = False
        string_char = None
        
        for char in params_str:
            if not in_string:
                if char in ['"', "'"]:
                    in_string = True
                    string_char = char
                    current_param += char
                elif char == '(':
                    paren_depth += 1
                    current_param += char
                elif char == ')':
                    paren_depth -= 1
                    current_param += char
                elif char == '{':
                    brace_depth += 1
                    current_param += char
                elif char == '}':
                    brace_depth -= 1
                    current_param += char
                elif char == ',' and paren_depth == 0 and brace_depth == 0:
                    params.append(current_param.strip())
                    current_param = ""
                else:
                    current_param += char
            else:
                current_param += char
                if char == string_char and params_str[params_str.index(char) - 1] != '\\':
                    in_string = False
        
        # 添加最后一个参数
        if current_param:
            params.append(current_param.strip())
        
        return len(params)