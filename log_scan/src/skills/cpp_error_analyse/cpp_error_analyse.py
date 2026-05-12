# cpp_error_analyse.py
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from datetime import datetime
from typing import Any, List
from core.function.base_function import *
from skills.skill_base import SkillBase


@singleton
class CppErrorAnalyse(SkillBase):
    def __init__(self, config_path, context_mgr, chat_mgr):
        super().__init__(config_path)
        self.context_mgr = context_mgr
        self.chat_mgr = chat_mgr
        self.tips = {
            "analyse_prompt": "请帮我解释以下C++报错信息，说明错误原因和可能的修复方向。\n",
            "analyse_result": "\n重要：直接返回如下格式的内容，xxx为编号，编号从1开始，每个报错都需要返回解释，不能多或者少：\n<<<-<<<报错xxx\n...\n>>>->>>\n"
        }

    def analyse(self, context_result: Any, batch_size: int, encoding: str, max_workers: int, current_step: int) -> Any:
        count = len(context_result)
        chunk_size = max((count + max_workers - 1) // max_workers, batch_size)
        current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{current_time}] 步骤{current_step}: 启动C++报错分析，共 {count} 个报错，使用 {max_workers} 个并发会话...")

        tasks = []
        total_tasks = 0
        for i in range(max_workers):
            start_idx = i * chunk_size
            if start_idx >= count:
                break
            end_idx = min(start_idx + chunk_size, count)
            worker_data = context_result[start_idx:end_idx]
            session = self.chat_mgr.add_session('chat')
            tasks.append({
                'session': session,
                'data': worker_data
            })
            total_tasks += len(worker_data)
        if total_tasks == 0:
            return context_result

        pbar = tqdm(total=total_tasks, desc="C++报错分析", unit="task")
        progress_lock = threading.Lock()
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {
                    executor.submit(
                        self._process_worker_batch,
                        task['data'],
                        task['session'],
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
                        current_time = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        print(f"[{current_time}] 任务 {task_info} 执行发生未捕获异常: {ex}")
        finally:
            pbar.close()
        return context_result

    def _process_worker_batch(self, worker_data: List[Any], session: Any, batch_size: int, pbar: tqdm, progress_lock: threading.Lock):
        count = len(worker_data)
        retry_count = 3
        for i in range(0, count, batch_size):
            batch_items = worker_data[i : i + batch_size]
            real_count = len(batch_items)

            query = self.tips["analyse_prompt"]
            for j, item in enumerate(batch_items):
                global_idx = i + j
                file_path = item.get('file_path', '未知文件')
                line_num = item.get('line_num', '未知行')
                tab_attribute = item.get('tab_attribute', '')
                cpp_error_msg = item.get('cpp_error_msg', '')
                query += f"""
                    #报错{global_idx + 1}:
                        出错的tab文件路径: {file_path}
                        Tab属性: {tab_attribute}
                        C++报错信息: {cpp_error_msg}
                    """
            query += self.tips["analyse_result"]

            success = False
            for retry in range(retry_count):
                try:
                    generator = self.chat_mgr.chat_stream(None, session, False, [], query, None, None, None, {}, {})
                    content = ''
                    for text in generator():
                        content += text

                    pattern = r'<<<-<<<报错(\d+)\n(.*?)\n>>>->>>'
                    matches = re.findall(pattern, content, re.DOTALL)
                    if len(matches) != real_count:
                        print(f"\n[!] 解析失败：期望 {real_count} 个结果，实际 {len(matches)} 个。重试中...")
                        continue
                    for snippet_id, block in matches:
                        index = int(snippet_id) - 1
                        batch_items[index]['suggestion'] = block
                    success = True
                    break
                except Exception as ex:
                    print(f"\n[!] 处理异常: {ex}")
            if not success:
                print(f"[!] 批次 {i//batch_size + 1} 处理失败，已达到最大重试次数。")
                print(f"{retry}次尝试用AI分析C++报错{i + 1}-{i + 1 + real_count}均以失败告终")
            with progress_lock:
                pbar.update(real_count)
