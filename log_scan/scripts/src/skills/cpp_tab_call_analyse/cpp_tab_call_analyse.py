# error_analyse.py
import threading
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from datetime import datetime
from core.function.base_function import *
from skills.cpp_tab_call_analyse.cpp_tab_call_analyse_base import CppTabCallAnalyseBase

class CppTabCallAnalyse(CppTabCallAnalyseBase):
    def __init__(self, config_path, chat_mgr):
        super().__init__(config_path, chat_mgr)

    def analyse(self, cpp_funcbody: Any, batch_size: int, max_workers: int, current_step):
        context_result = cpp_funcbody["functions"]
        macros = cpp_funcbody["macros"]
        analyse_data = []
        for func_name, func_info in context_result.items():
            analyse_data.append({'func_name': func_name, 'func_info': func_info})
        count = len(analyse_data)
        chunk_size = max((count + max_workers - 1) // max_workers, batch_size)
        current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{current_time}] 步骤{current_step}: 启动分析，共 {count} 个片段，使用 {max_workers} 个并发会话...")
        
        tasks = []
        total_tasks = 0
        for i in range(max_workers):
            start_idx = i * chunk_size
            if start_idx >= count:
                break
            end_idx = min(start_idx + chunk_size, count)
            worker_data = analyse_data[start_idx:end_idx]
            session = self.chat_mgr.add_session('chat')
            tasks.append({
                'session': session,
                'data': worker_data
            })
            total_tasks += len(worker_data)
        if total_tasks == 0:
            return
        
        pbar = tqdm(total=total_tasks, desc="C++代码tab表调用分析", unit="task")
        progress_lock = threading.Lock()
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {
                    executor.submit(
                        self._process_worker_batch, 
                        task['data'], 
                        task['session'], 
                        macros,
                        batch_size,
                        pbar,
                        progress_lock,
                    ): task for task in tasks
                }
                for future in as_completed(future_to_task):
                    task_info = future_to_task[future]
                    try:
                        future.result()
                    except Exception as ex:
                        current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        print(f"[{current_time}] 任务 {task_info} 执行发生未捕获异常: {ex}")
        finally:
            pbar.close()