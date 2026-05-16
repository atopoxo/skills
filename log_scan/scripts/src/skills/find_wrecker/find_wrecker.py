# find_wrecker.py
import threading
import re
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from typing import Any, List
from core.function.base_function import *
from skills.find_wrecker.find_wrecker_base import FindWreckerBase

@singleton
class FindWrecker(FindWreckerBase):
    def __init__(self, config_path, chat_mgr):
        super().__init__(config_path)
        self.chat_mgr = chat_mgr
        self.code_block_marker = "```"
        self.return_format = {
                    "key": {
                        "type": "string"
                    },
                    "error_index": {
                        "type": "string"
                    },
                    "wrecker_index": {
                        "type": "string"
                    }
                }
        self.tips = {
            "analyse_prompt": f"""请帮我分析下面各个报错片段的SVN修改记录，
            当出现'报错原因'属性时，需要找到首次出现'报错原因'对应的修改处，
            当出现'c++报错行代码'属性时，找到'wrecker_info'中首次出现当'修改前内容'的值变成'修改后内容'的值时，会导致'c++报错行代码'所指的报错的记录，
            如果没找到会导致'c++报错行代码'所指的报错的svn提交记录，那么'wrecker_index'应该返回-1，
            直接按照指定的格式返回即可，
            其中'修改类型'可选参数为：'add(添加)'、'delete(删除)'、'modify(修改)'：
                    """,
            "analyse_result": f"""
                重要：直接返回如下格式的内容，xxx为编号，编号从1开始，如果问题中包含多个片段，每个片段都需要返回分析结果，不能多或者少：
                <<<-<<<报错片段xxx
                    {self.json_parser.to_json_str(self.return_format, indent=2)}
                >>>->>>
                ...
                """
        }
    
    def set_chat_mgr(self, chat_mgr):
        """设置聊天管理器，用于大模型分析"""
        self.chat_mgr = chat_mgr

    def get_principal(self, description: str):
        return self._get_principal(description)

    def get_blame_by_history(self, context_result: Any, encoding: str, max_workers: int, start_day: str = None):
        if not self.use_svn:
            return "SVN 查询已禁用"
        try:
            tasks = []
            file_history_cache = {}
            for key, items in context_result.items():
                check_days = 7
                check_count = 100
                if key == "tab_load":
                    check_count = 10000
                cache = self._get_svn_differs(items, encoding, check_days, check_count, max_workers, start_day)
                file_history_cache.update(cache)
                for item in items:
                    tasks.append({"key": key, "value": item})
            total_tasks = len(tasks)
            if total_tasks == 0:
                return
            pbar = tqdm(total=total_tasks, desc="svn差异追溯", unit="task")
            progress_lock = threading.Lock()
            try:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_task = {
                        executor.submit(
                            self._get_item_svn_info, 
                            task,
                            file_history_cache,
                            encoding,
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
        except Exception as ex:
            return f"Find SVN differs error: {ex}"
        return context_result

    def analyse_wrecker(self, context_result: Any, batch_size: int, save_result: bool, encoding: str, max_workers: int):
        if self.chat_mgr is None:
            print("[!] 警告: 未设置chat_mgr，无法进行大模型分析")
            return
        analyse_items = []
        for key, items in context_result.items():
            for i, context in enumerate(items):
                wrecker_info_len = len(context['wrecker_info'])
                if wrecker_info_len > 1 or (wrecker_info_len > 0 and context.get('error_msg')):
                    analyse_items.append({'key': key, 'index': i, 'item': context})
                else:
                    if context.get('update_error'):
                        context['wrecker_index'] = -1
                    else:
                        context['wrecker_index'] = 0
        count = len(analyse_items)
        if count == 0:
            return
        
        chunk_size = max((count + max_workers - 1) // max_workers, batch_size)
        current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{current_time}] 步骤5: 启动分析svn wrecker，共 {count} 个片段，使用 {max_workers} 个并发会话...")
        tasks = []
        total_tasks = 0
        for i in range(max_workers):
            start_idx = i * chunk_size
            if start_idx >= count:
                break
            end_idx = min(start_idx + chunk_size, count)
            worker_data = analyse_items[start_idx:end_idx]
            session = self.chat_mgr.add_session('chat')
            tasks.append({
                'session': session,
                'data': worker_data
            })
            total_tasks += len(worker_data)
        if total_tasks == 0:
            return
        
        pbar = tqdm(total=total_tasks, desc="svn wrecker分析", unit="task")
        progress_lock = threading.Lock() 
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {
                    executor.submit(
                        self._process_wrecker_batch, 
                        task['data'], 
                        task['session'],
                        context_result,
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
    
    def _process_wrecker_batch(self, worker_data: List[Any], session: Any, context_result: Any, batch_size: int, pbar: tqdm, progress_lock: threading.Lock):
        count = len(worker_data)
        retry_count = 3
        for i in range(0, count, batch_size):
            batch_items = worker_data[i : i + batch_size]
            real_count = len(batch_items)

            query = self.tips["analyse_prompt"]
            for j, batch_item in enumerate(batch_items):
                item = batch_item['item']
                query_data = {
                    'key': batch_item['key'],
                    'error_index': batch_item['index'],
                }
                if item.get('error'):
                    query_data['报错原因'] = item['error']
                else:
                    query_data['c++报错行代码'] = item['cpp_error_msg']
                wrecker_infos = []
                if item.get('wrecker_info'):
                    for k, wrecker_item in enumerate(item['wrecker_info']):
                        author = wrecker_item.get('author', '未知')
                        revision = wrecker_item.get('revision', '未知')
                        change_type = wrecker_item.get('type', '未知')
                        old_content = wrecker_item.get('old', '未知')
                        new_content = wrecker_item.get('new', '未知')
                        query_block = {
                            "wrecker_index": k,
                            "作者": author,
                            "版本": revision,
                            "修改类型": change_type,
                            "修改前内容": old_content,
                            "修改后内容": new_content
                        }
                        wrecker_infos.append(query_block)
                query_data["svn修改记录查询结果"] = wrecker_infos
                query += f"""#报错片段{j + 1}
                            {self.json_parser.to_json_str(query_data, indent=2)}
                        """
            query += self.tips["analyse_result"]
            success = False
            for retry in range(retry_count):
                try:
                    generator = self.chat_mgr.chat_stream(None, session, False, [], query, None, None, None, {}, {})
                    content = ''
                    for text in generator():
                        content += text
                    pattern = r'<<<-<<<报错片段(\d+)\n(.*?)\n>>>->>>'
                    matches = re.findall(pattern, content, re.DOTALL)
                    if len(matches) != real_count:
                        print(f"\n[!] 解析失败：期望 {real_count} 个结果，实际 {len(matches)} 个。重试中...")
                        continue
                    for snippet_id, block in matches:
                        try:
                            wrecker_result = self.json_parser.parse(block)
                            key = wrecker_result["key"]
                            error_index = int(wrecker_result["error_index"])
                            wrecker_index = int(wrecker_result["wrecker_index"])

                            item = context_result[key][error_index]
                            item['wrecker_index'] = wrecker_index
                        except Exception as ex:
                            print(f"\n[!] 解析报错片段 {snippet_id} 失败: {ex}")
                    
                    success = True
                    break
                except Exception as ex:
                    print(f"\n[!] 处理异常: {ex}")
            
            if not success:
                print(f"[!] 批次 {i//batch_size + 1} 处理失败，已达到最大重试次数。")
                print(f"{retry_count}次尝试分析SVN修改记录{i + 1}-{i + 1 + real_count}均以失败告终")
            
            with progress_lock:
                pbar.update(real_count)