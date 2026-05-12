# error_analyse.py
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from datetime import datetime
from typing import Any, List
from core.function.base_function import *
from core.json.json_parser import get_json_parser
from skills.skill_base import SkillBase

@singleton
class ErrorAnalyse(SkillBase):
    def __init__(self, config_path, context_mgr, chat_mgr):
        super().__init__(config_path)
        self.context_mgr = context_mgr
        self.chat_mgr = chat_mgr
        self.code_block_marker = "```"
        self.tips = {
            "analyse_prompt": f"""请帮我分析一下下面的代码该如何改进。
                    """,
            "analyse_result": f"""
                重要：直接返回如下格式的内容，xxx为编号，编号从1开始，如果问题中包含多个代码片段，每个代码片段都需要返回分析结果，不能多或者少：
                <<<-<<<代码片段xxx
                    ...
                >>>->>>
                ...
                """
        }
        self.json_parser = get_json_parser()

    def analyse(self, context_result: Any, batch_size: int, encoding: str, max_workers: int, current_step: int) -> Dict:
        analyse_data = []
        for context in context_result:
            if context['need_analyse']:
                analyse_data.append(context)
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
            return analyse_data
        
        pbar = tqdm(total=total_tasks, desc="代码分析", unit="task")
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
                        current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        print(f"[{current_time}] 任务 {task_info} 执行发生未捕获异常: {ex}")
        finally:
            pbar.close()
        return analyse_data
    
    def _process_worker_batch(self, worker_data: List[Any], session: Any, batch_size: int, pbar: tqdm, progress_lock: threading.Lock):
        count = len(worker_data)
        retry_count = 3
        for i in range(0, count, batch_size):
            batch_items = worker_data[i : i + batch_size]
            real_count = len(batch_items)

            query = self.tips["analyse_prompt"]
            for j, item in enumerate(batch_items):
                global_idx = i + j
                query += f"""
                    #代码片段{global_idx + 1}:
                        代码内容：
                        {self.code_block_marker}
                        {item['select_content']}
                        {self.code_block_marker}
                        报错原因："{item['error']}"
                        {item['reference']}
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

                    pattern = r'<<<-<<<代码片段(\d+)\n(.*?)\n>>>->>>'
                    matches = re.findall(pattern, content, re.DOTALL)
                    if len(matches) != real_count:
                        print(f"\n[!] 解析失败：期望 {real_count} 个结果，实际 {len(matches)} 个。重试中...")
                        continue
                    for snippet_id, block in matches:
                        index = int(snippet_id) - 1
                        worker_data[index]['suggestion'] = block
                    success = True
                    break
                except Exception as ex:
                    print(f"\n[!] 处理异常: {ex}")
            if not success:
                print(f"[!] 批次 {i//batch_size + 1} 处理失败，已达到最大重试次数。")
                print(f"{retry}次尝试用ai分析代码片段{i + 1}-{i + 1 + real_count}均以失败告终")
            with progress_lock:
                pbar.update(real_count)