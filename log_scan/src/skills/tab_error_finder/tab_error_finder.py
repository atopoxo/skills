import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from datetime import datetime
from typing import Any, List, Dict

from skills.skill_base import SkillBase


class TabErrorFinder(SkillBase):
    def __init__(self, config_path):
        super().__init__(config_path)

    def find(self, unique_errors: Dict[str, Dict[int, List[str]]], cpp_funcbody: Any, tab_infos: Any, product_dir: str, encoding: str, max_workers: int, current_step: int) -> List[Dict[str, str]]:
        result = []

        if not unique_errors:
            return result
        tasks = []
        for func_name, line_errors in unique_errors.items():
            if func_name not in cpp_funcbody:
                continue
            func_info = cpp_funcbody[func_name]
            check_list = func_info.get("check_list", [])
            tab_files = tab_infos.get(func_name, [])
            for line_num, error_info in line_errors.items():
                matching_checks = []
                for check in check_list:
                    if check.get("error_line") == line_num:
                        matching_checks.append(check)
                for check in matching_checks:
                    tab_attribute = check.get("tab_attribute", "")
                    error_msg = check.get("error_msg", "")
                    error_msgs = error_info.get("error_msgs", [])
                    if error_msgs:
                        if isinstance(error_msgs, list):
                            error_msg = error_msgs[0]  # 使用第一个错误消息
                        else:
                            error_msg = error_msgs
                    elif not error_msg:
                        error_msg = check.get("error_msg", "")
                    cpp_error_msg = check.get("error_msg", "")
                    relative_path_list = error_info.get("relative_paths", [])
                    intersection_path_list = []
                    for relative_path in relative_path_list:
                        if relative_path in tab_files:
                            intersection_path_list.append(relative_path)
                    if len(intersection_path_list) <= 0:
                        intersection_path_list = list(tab_files)
                    for rel_path in intersection_path_list:
                        path = os.path.join(product_dir, "client", rel_path).replace('\\', '/')
                        if os.path.exists(path):
                            tasks.append({
                                "file_path": path,
                                "tab_attribute": tab_attribute,
                                "error_msg": error_msg,
                                "cpp_error_msg": cpp_error_msg,
                                "line_num": line_num
                            })

        total_tasks = len(tasks)
        if total_tasks == 0:
            return result

        current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{current_time}] 步骤{current_step}: 开始并行处理 {total_tasks} 个tab错误匹配任务，线程池大小: {max_workers}")

        progress_lock = threading.Lock()
        with tqdm(total=total_tasks, desc="匹配tab错误", unit="task") as pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {
                    executor.submit(
                        self._process_task,
                        result,
                        task,
                        pbar,
                        progress_lock
                    ): task for task in tasks
                }
                for future in as_completed(future_to_task):
                    task_info = future_to_task[future]
                    try:
                        future.result()
                    except Exception as ex:
                        current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        print(f"[{current_time}] 任务 {task_info} 处理失败: {ex}")

        return result

    def _process_task(self, result: List[Dict], task: Dict, pbar: tqdm, progress_lock: threading.Lock):
        try:
            with progress_lock:
                result.append({
                    "file_path": task["file_path"],
                    "tab_attribute": task["tab_attribute"],
                    "error_msg": task["error_msg"],
                    "cpp_error_msg": task["cpp_error_msg"],
                    "line_num": task["line_num"]
                })
                pbar.update(1)
        except Exception as ex:
            raise Exception(f"处理任务 {task} 时出错: {ex}")