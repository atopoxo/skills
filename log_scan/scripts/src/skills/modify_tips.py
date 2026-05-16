# modify_tips.py
from typing import Dict, List, Any
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from core.function.base_function import *
from skills.skill_base import SkillBase

@singleton
class ModifyTips(SkillBase):
    def __init__(self, config_path, context_mgr):
        super().__init__(config_path)
        self.context_mgr = context_mgr
        self.result_lock = threading.Lock()

    def get_modify_tips(self, unique_errors: Any, context_lines: int, encoding: str, max_workers: int) -> List[Any]:
        result = []
        tasks = []
        task_index = 0
        for file_path, lines in unique_errors.items():
            for line_num, error_data in lines.items():
                error_list = error_data.get('error', {})
                if not error_list:
                    continue
                reference_need = error_data.get('reference_need', False)
                error_str = ';'.join([error for error in error_list.keys()])
                count = sum(error_list.values())
                tasks.append({
                    'task_index': task_index,
                    'file_path': file_path,
                    'line_num': line_num,
                    'context_lines': context_lines,
                    'error': error_str,
                    'reference_need': reference_need,
                    'count': count
                })
                task_index += 1

        total_tasks = len(tasks)
        if total_tasks == 0:
            return result
        
        current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{current_time}] 开始并行处理 {len(tasks)} 个任务，线程池大小: {max_workers}")
        
        pbar = tqdm(total=total_tasks, desc="分析报错行代码上下文", unit="task")
        progress_lock = threading.Lock()
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_task = {
                    executor.submit(
                        self.__get_single_tip, 
                        result,
                        task['file_path'], 
                        task['line_num'], 
                        task['context_lines'],
                        task['error'],
                        task['reference_need'],
                        task['count'],
                        encoding, 
                        task['task_index'],
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
        return result
    
    def __get_single_tip(self, result: List[Dict], file_path: str, line_num: int, context_lines: int, error: str, reference_need: bool, count: int, encoding: str, task_index: int, pbar: tqdm, progress_lock: threading.Lock):
        try:
            code_context = read_file_context(file_path, line_num, context_lines, None, 'byte')
            if code_context:
                reference_content = ''
                need_analyse = False
                if reference_need:
                    reference_code = self.__get_reference_code(code_context, file_path)
                    reference_content = self.context_mgr.get_context(reference_code, encoding=code_context['encoding'], replace_byte=True)
                    if len(reference_content) > 0:
                        need_analyse = True
                else:
                    need_analyse = True
                try:
                    item = {
                        'encoding': code_context['encoding'],
                        'file_path': file_path,
                        'line_num': line_num,
                        'select_content': code_context['select_content'].decode(encoding, errors='ignore'),
                        'error': error,
                        'reference': reference_content,
                        'count': count,
                        'need_analyse': need_analyse
                    }
                    with self.result_lock:
                        result.append(item)
                except Exception as ex:
                    current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    print(f"[{current_time}] 获取第{task_index + 1}个错误的上下文失败，失败原因: {str(ex)}")
            else:
                print(f"文件读取失败: {file_path}")
        finally:
            with progress_lock:
                pbar.update(1)

    def __get_reference_code(self, code_context: Dict, file_path: str) -> Dict[str, str]:
        try:
            result = self.context_mgr.get_relevant_context(code_context["selection"]["start"]["pos"], code_context["select_content"], code_context["file_content"], file_path, code_context["encoding"])
            return result
        except Exception as ex:
            return {"error": f"获取引用代码失败: {str(ex)}"}