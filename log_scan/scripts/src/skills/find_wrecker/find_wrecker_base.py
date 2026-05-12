# find_wrecker.py
import requests
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from typing import Any
from core.function.base_function import *
from skills.skill_base import SkillBase
from skills.submit_tool.GetAssignees import process_workitem_data

class FindWreckerBase(SkillBase):
    def __init__(self, config_path):
        super().__init__(config_path)
        self.use_svn = self.config['svn']['use_svn']

    def _parse_svn_log(self, lines):
        """解析SVN日志输出"""
        history = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if line.startswith('r'):
                parts = line.split('|')
                if len(parts) >= 3:
                    rev = parts[0].strip()
                    author = parts[1].strip()
                    date = parts[2].strip()
                    description = ""
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j].strip()
                        if next_line.startswith('---'):
                            break
                        if next_line and not next_line.startswith('Changed paths:') and not next_line.startswith('M ') and not next_line.startswith('A ') and not next_line.startswith('D '):
                            description = next_line
                            break
                        j += 1
                    history.append({
                        'revision': rev, 
                        'author': author,
                        'date': date,
                        'description': description
                    })
                    i = j + 1
                else:
                    i += 1
            else:
                i += 1
        return history

    def _get_svn_path_modify(self, file_path: str) -> str:
        return file_path

    def _get_svn_file_differs(self, file_path: str, encoding: str, check_days: int, check_count: int, pbar: tqdm, progress_lock: threading.Lock, start_day: str = None) -> Any:
        if 'skill/Buff.tab' in file_path:
            start_day = '2026-04-17'
        history = []
        history_days = []
        history_count = []
        try:
            if check_days > 0:
                import datetime
                if start_day:
                    # 如果有起始日期，使用起始日期作为开始时间
                    try:
                        # 尝试解析起始日期
                        end_date = datetime.datetime.strptime(start_day, '%Y-%m-%d')
                        start_date = end_date - datetime.timedelta(days=check_days)
                        start_str = start_date.strftime('%Y-%m-%d')
                        end_str = end_date.strftime('%Y-%m-%d')
                        log_cmd_days = ['svn', 'log', '-v', '-r', f'{{{start_str}}}:{{{end_str}}}', self._get_svn_path_modify(file_path)]
                    except ValueError:
                        # 如果日期格式错误，回退到原始逻辑
                        days_ago = (datetime.datetime.now() - datetime.timedelta(days=check_days)).strftime('%Y-%m-%d')
                        log_cmd_days = ['svn', 'log', '-v', '-r', f'{{{days_ago}}}:HEAD', self._get_svn_path_modify(file_path)]
                else:
                    # 如果没有起始日期，使用原始逻辑
                    days_ago = (datetime.datetime.now() - datetime.timedelta(days=check_days)).strftime('%Y-%m-%d')
                    log_cmd_days = ['svn', 'log', '-v', '-r', f'{{{days_ago}}}:HEAD', self._get_svn_path_modify(file_path)]
                try:
                    log_res = subprocess.run(log_cmd_days, capture_output=True, text=False, timeout=30)
                    if log_res.returncode == 0 and log_res.stdout:
                        raw_output = log_res.stdout.decode(encoding, errors='ignore')
                        if raw_output:  # 添加空检查
                            lines = raw_output.splitlines()
                            history_days = self._parse_svn_log(lines)
                            history_days.reverse()
                except Exception:
                    history_days = []
            if check_count > 0:
                if len(history_days) < check_count:
                    log_cmd_limit = ['svn', 'log', '-v', '-l', '100', self._get_svn_path_modify(file_path)]
                    try:
                        log_res = subprocess.run(log_cmd_limit, capture_output=True, text=False, timeout=30)
                        if log_res.returncode == 0 and log_res.stdout:
                            raw_output = log_res.stdout.decode(encoding, errors='ignore')
                            if raw_output:  # 添加空检查
                                lines = raw_output.splitlines()
                                history_count = self._parse_svn_log(lines)
                    except Exception:
                        history_count = []

            if len(history_days) >= len(history_count):
                history = history_days
            else:
                history = history_count
        except Exception as ex:
            print(f"{file_path} 执行发生未捕获异常: {ex}")
        finally:
            with progress_lock:
                pbar.update(1)
            return history
        
    def _get_svn_differs(self, context_result: Any, encoding: str, check_days: int, check_count: int, max_workers: int, start_day: str = None) -> Any:
        file_history_cache = {}
        try:
            unique_files = list(set(item['file_path'] for item in context_result))
            tasks = []
            for file_path in unique_files:
                tasks.append({
                    "file_path": file_path
                })
            total_tasks = len(tasks)
            if total_tasks == 0:
                return file_history_cache
            pbar = tqdm(total=total_tasks, desc="svn提交记录查询", unit="task")
            progress_lock = threading.Lock()
            try:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_task = {
                        executor.submit(
                            self._get_svn_file_differs,
                            task['file_path'],
                            encoding,
                            check_days,
                            check_count,
                            pbar,
                            progress_lock,
                            start_day,
                        ): task for task in tasks
                    }
                    for future in as_completed(future_to_task):
                        task_info = future_to_task[future]
                        file_path = task_info['file_path']
                        try:
                            file_history_cache[file_path] = future.result()
                        except Exception as ex:
                            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                            print(f"[{current_time}] 任务 {task_info} 执行发生未捕获异常: {ex}")
            finally:
                pbar.close()
            return file_history_cache
        except Exception as ex:
            return f"SVN 查询失败: {ex}"

    def _find_hunk_for_line(self, diff_text: str, target_line: int) -> dict:
        if not diff_text.strip():
            return None
        lines = diff_text.split('\n')
        result = {
            "type": None,
            "old_line": None,
            "new_line": target_line,
            "old_content": None,
            "new_content": None
        }
        cumulative_offset = 0 

        i = 0
        while i < len(lines):
            line = lines[i]
            # 1. 解析 Hunk Header: @@ -old_start,count +new_start,count @@
            if line.startswith('@@'):
                match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
                if not match:
                    i += 1
                    continue

                old_start = int(match.group(1))
                old_line_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_line_count = int(match.group(4)) if match.group(4) else 1

                adjusted_new_start = new_start
                adjusted_new_end = adjusted_new_start + new_line_count
                if adjusted_new_start <= target_line and target_line < adjusted_new_end:
                    j = i + 1
                    current_old_line = old_start
                    current_new_line = adjusted_new_start
                    while j < len(lines) and not lines[j].startswith('@@'):
                        hunk_line = lines[j]
                        if hunk_line.startswith('\\ '): # 忽略文件属性变更行（如 newline style）
                            j += 1
                            continue
                        elif hunk_line.startswith('-'):
                            if current_new_line > target_line:
                                result["type"] = "deleted"
                                result["old_line"] = current_old_line
                                result["new_line"] = None
                                result["old_content"] = hunk_line[1:].strip()
                                return result
                            current_old_line += 1
                        elif hunk_line.startswith('+'):
                            if current_new_line == target_line:
                                result["type"] = "added"
                                result["old_line"] = None
                                result["new_line"] = target_line
                                result["new_content"] = hunk_line[1:].strip()
                                return result
                            current_new_line += 1
                        elif hunk_line.startswith(' '):
                            # 上下文行：没有修改，只是更新行号计数器
                            # 注意：如果目标行是上下文行，它可能没有被修改
                            # 但我们仍然返回上下文信息
                            if current_new_line == target_line:
                                result["type"] = "context"
                                result["old_line"] = current_old_line
                                result["new_line"] = target_line
                                result["old_content"] = hunk_line[1:]
                                result["new_content"] = hunk_line[1:]
                                return result
                            current_old_line += 1
                            current_new_line += 1
                        else:
                            pass
                        j += 1
                    i = j - 1
                else:
                    if target_line > adjusted_new_end:
                        hunk_offset = (new_line_count - old_line_count) + (new_start - old_start)
                        cumulative_offset = hunk_offset
            i += 1
        if result["type"] is None:
            result["type"] = "context"
            result["old_line"] = max(1, target_line - cumulative_offset)
            result["new_line"] = target_line
            
        return result if result["type"] else None

    def _get_item_svn_info(self, item: Any, file_history_cache: dict, encoding: str, pbar: tqdm, progress_lock: threading.Lock) -> dict:
        try:
            key = item["key"]
            data = item["value"]
            file_path = data['file_path']
            history = file_history_cache.get(file_path, [])
            if key == "tab_load":
                self._update_wrecker_info_by_col_attribute(file_path, data, history, encoding)
            else:
                self._update_wrecker_info_by_line_num(file_path, data, history, encoding)
        except Exception as ex:
            print(f"{data['file_path']} 执行发生未捕获异常: {ex}")
        finally:
            with progress_lock:
                pbar.update(1)

    def _get_tab_attribute_col_index(self, file_path: str, encoding: str, tab_attribute: str) -> int:
        column_index = None
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
        except Exception:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                return column_index

        lines = content.split('\n')
        if not lines:
            return column_index
        headers = []
        if lines:
            headers = lines[0].split('\t')
        for i, header in enumerate(headers):
            if tab_attribute == header or tab_attribute in header:
                column_index = i
                break
        return column_index
        
    def _read_file_lines_with_encoding(self, file_path: str, encoding: str) -> list:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read().splitlines()
        except Exception:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read().splitlines()
            except Exception:
                return []

    def _update_wrecker_info_by_col_attribute(self, file_path: str, data: Any, history: list, encoding: str):
        tab_attribute = data.get('tab_attribute')
        if not tab_attribute:
            data['wrecker_info'] = None
            return

        column_index = self._get_tab_attribute_col_index(file_path, encoding, tab_attribute)
        if column_index is None:
            data['wrecker_info'] = []
            data['update_error'] = f"{file_path} 未找到列 {tab_attribute}"
            return

        try:
            file_lines = self._read_file_lines_with_encoding(file_path, encoding)
            header = file_lines[0] if file_lines else ""
        except Exception as ex:
            print(f"{file_path} open file 执行发生未捕获异常: {ex}")
            return

        def _get_line_content(line_num):
            if line_num is not None and file_lines and line_num > 0 and line_num <= len(file_lines):
                return file_lines[line_num - 1]
            return ""

        all_modifications = []
        for hist in history:
            rev = hist['revision']
            author = hist['author']
            description = hist['description']
            diff_cmd = ['svn', 'diff', '-c', rev, self._get_svn_path_modify(file_path)]
            try:
                diff_res = subprocess.run(diff_cmd, capture_output=True, text=True, check=True, encoding=encoding, timeout=30)
            except Exception as ex:
                continue
            diff_text = diff_res.stdout
            if not diff_text.strip():
                continue

            try:
                modifications_in_rev = self._find_hunk_for_column(diff_text, column_index)
                for mod in modifications_in_rev:
                    new_line = mod.get("new_line")
                    chain_entry = {
                        "author": author,
                        "revision": rev,
                        "description": description,
                        "principal": self._get_principal(description),
                        "type": mod.get('type', 'modify'),
                        "old": mod.get("old_value"),
                        "new": mod.get("new_value"),
                        "old_line": mod.get("old_line"),
                        "new_line": new_line,
                        "header": header,
                        "new_line_content": _get_line_content(new_line)
                    }
                    all_modifications.append(chain_entry)
            except Exception as ex:
                print(f"{data['file_path']} chain_entry 执行发生未捕获异常: {ex}")
        if not all_modifications:
            all_modifications = self._find_tab_attribute_creation(file_path, tab_attribute, column_index, encoding)
            for mod in all_modifications:
                new_line = mod.get("new_line")
                mod["header"] = header
                mod["new_line_content"] = _get_line_content(new_line)
        all_modifications = self._merge_modifications(all_modifications)
        # error_msg = data.get('error_msg', '')
        # all_modifications = self._filter_by_error_relevance(all_modifications, error_msg, 20)
        data['wrecker_info'] = all_modifications if all_modifications else None

    def _merge_modifications(self, modifications: list) -> list:
        result = []
        line_result = {}
        if not modifications:
            return result
        for modify in modifications:
            line_num = modify["new_line"]
            if line_num not in line_result:
                line_result[line_num] = []
            line_result[line_num].append(modify)
            
        revision_result = {}
        for line_num, modify_list in line_result.items():
            last_modify = None
            for modify in modify_list:
                if last_modify is None:
                    self._update_revision_record(revision_result, modify)
                    last_modify = modify
                else:
                    if modify['new'] != last_modify['new']:
                        self._update_revision_record(revision_result, modify)
                        last_modify = modify

        seen_ids = set()
        result = []
        for revision, item in revision_result.items():
            if "cache" in item:
                for modify in item["cache"].values():
                    mod_id = id(modify)
                    if mod_id not in seen_ids:
                        seen_ids.add(mod_id)
                        result.append(modify)
            else:
                min_mod = item['min_modify']
                max_mod = item['max_modify']
                min_id = id(min_mod)
                max_id = id(max_mod)
                if min_id not in seen_ids:
                    seen_ids.add(min_id)
                    result.append(min_mod)
                if max_id != min_id and max_id not in seen_ids:
                    seen_ids.add(max_id)
                    result.append(max_mod)
        return result
    
    def _update_revision_record(self, revision_result: Any, modify: Any):
        revision = modify['description'] if modify.get('description') else modify['revision']
        if revision not in revision_result:
            revision_result[revision] = {}
        num_flag_new = is_number(modify['new'])
        num_flag_old = is_number(modify['old'])
        if num_flag_new or num_flag_old:
            if num_flag_new:
                cur_value = float(modify['new'])
                if revision_result[revision].get("min") is None:
                    revision_result[revision] = {
                        "min": cur_value,
                        "max": cur_value,
                        "min_modify": modify,
                        "max_modify": modify
                    }
                else:
                    if revision_result[revision]["min"] > cur_value:
                        revision_result[revision]["min"] = cur_value
                        revision_result[revision]["min_modify"] = modify
                    if revision_result[revision]["max"] < cur_value:
                        revision_result[revision]["max"] = cur_value
                        revision_result[revision]["max_modify"] = modify
            if num_flag_old:
                cur_value = float(modify['old'])
                if revision_result[revision].get("min") is None:
                    revision_result[revision] = {
                        "min": cur_value,
                        "max": cur_value,
                        "min_modify": modify,
                        "max_modify": modify
                    }
                else:
                    if revision_result[revision]["min"] > cur_value:
                        revision_result[revision]["min"] = cur_value
                        revision_result[revision]["min_modify"] = modify
                    if revision_result[revision]["max"] < cur_value:
                        revision_result[revision]["max"] = cur_value
                        revision_result[revision]["max_modify"] = modify
        else:
            if "cache" not in revision_result[revision]:
                revision_result[revision] = {
                    "cache": {}
                }
            cur_value = modify['new']
            if cur_value not in revision_result[revision]["cache"]:
                revision_result[revision]["cache"][cur_value] = modify
            cur_value = modify['old']
            if cur_value not in revision_result[revision]["cache"]:
                revision_result[revision]["cache"][cur_value] = modify

    
    def _extract_search_tokens(self, error_msg: str) -> list:
        tokens = []

        quoted = re.findall(r'"([^"]+)"', error_msg)
        tokens.extend(quoted)

        numbers = re.findall(r'\d+', error_msg)
        tokens.extend(numbers)

        identifiers = re.findall(r'[a-zA-Z_]\w{2,}', error_msg)
        tokens.extend(identifiers)

        skip_words = {'the', 'and', 'for', 'not', 'int', 'void', 'bool', 'char',
                      'line', 'ERROR', 'KGLOG', 'PROCESS', 'at', 'nil', 'null'}
        tokens = [t for t in tokens if t.lower() not in skip_words]

        dotted_identifiers = re.findall(r'[a-zA-Z_]\w*(?:\.[a-zA-Z_]\w*)+', error_msg)
        for dotted in dotted_identifiers:
            parts = dotted.split('.')
            tokens.extend(parts)  # 添加各个部分
            tokens.append(dotted)  # 添加完整形式

        return list(dict.fromkeys(tokens))

    def _filter_by_error_relevance(self, modifications: list, error_msg: str, max_results: int = 200) -> list:
        if not modifications:
            return modifications

        def _rev_num(rev_str: str) -> int:
            try:
                return int(rev_str.lstrip('r'))
            except (ValueError, AttributeError):
                return 0

        modifications.sort(key=lambda x: _rev_num(x.get('revision', '')), reverse=True)

        if not error_msg:
            return modifications[:max_results]

        tokens = self._extract_search_tokens(error_msg)

        if not tokens:
            return modifications[:max_results]

        scored = []
        for mod in modifications:
            score = 0
            old_val = str(mod.get('old', '')) if mod.get('old') else ''
            new_val = str(mod.get('new', '')) if mod.get('new') else ''
            for token in tokens:
                if token in old_val or token in new_val:
                    score += 1
            scored.append((score, mod))

        matching = [mod for score, mod in scored if score > 0]
        if matching:
            return matching[:max_results]

        return modifications[:max_results]

    def _find_hunk_for_column(self, diff_text: str, column_index: int) -> list:
        if not diff_text.strip():
            return []

        modifications = []
        lines = diff_text.split('\n')
        i = 0
        while i < len(lines):
            if lines[i].startswith('@@'):
                match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', lines[i])
                if not match:
                    i += 1
                    continue

                old_start = int(match.group(1))
                old_line_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_line_count = int(match.group(4)) if match.group(4) else 1

                current_old_line = old_start
                current_new_line = new_start
                deletes = []
                adds = []
                contexts = []
                j = i + 1
                while j < len(lines) and not lines[j].startswith('@@'):
                    line = lines[j]
                    if line.startswith('\\ '):  # 忽略文件属性变更行
                        j += 1
                        continue

                    columns = line[1:].split('\t') if len(line) > 1 else []
                    column_value = columns[column_index] if len(columns) > column_index else None

                    if line.startswith('-'):
                        if column_value is not None:
                            deletes.append((current_old_line, column_value))
                        current_old_line += 1
                    elif line.startswith('+'):
                        if column_value is not None:
                            adds.append((current_new_line, column_value))
                        current_new_line += 1
                    elif line.startswith(' '):
                        if column_value is not None:
                            contexts.append((current_old_line, current_new_line, column_value))
                        current_old_line += 1
                        current_new_line += 1
                    j += 1
                if old_line_count == new_line_count and not deletes and not adds and contexts:
                    for old_line, new_line, context_value in contexts:
                        modifications.append({
                            'type': 'context_modify',  # 特殊类型，表示上下文行中的可能修改
                            "old_value": None,  # 旧值未知
                            "new_value": context_value,
                            "old_line": old_line,
                            "new_line": new_line
                        })
                else:
                    hunk_mods = self._match_column_modifications(deletes, adds, contexts)
                    modifications.extend(hunk_mods)
                i = j
            else:
                i += 1
        return modifications
    
    def _match_column_modifications(self, deletes: list, adds: list, contexts: list) -> list:
        modifications = []
        try:
            processed_deletes = set()
            processed_adds = set()
            context_map_old_to_new = {old_line: new_line for old_line, new_line, _ in contexts}

            for old_line, del_value in deletes:
                if old_line in processed_deletes:
                    continue
                expected_new_line = context_map_old_to_new.get(old_line)
                if expected_new_line is None:
                    closest_old = max([k for k in context_map_old_to_new.keys() if k < old_line], default=None)
                    if closest_old is not None:
                        offset = old_line - closest_old
                        expected_new_line = context_map_old_to_new[closest_old] + offset
                if expected_new_line is not None:
                    for new_line, add_value in adds:
                        if new_line in processed_adds:
                            continue
                        if abs(new_line - expected_new_line) <= 2:
                            if del_value != add_value:
                                modifications.append({
                                    'type': 'modify',
                                    "old_value": del_value,
                                    "new_value": add_value,
                                    "old_line": old_line,
                                    "new_line": new_line
                                })
                            processed_deletes.add(old_line)
                            processed_adds.add(new_line)
                            break

            remaining_deletes = [(line, val) for line, val in deletes if line not in processed_deletes]
            remaining_adds = [(line, val) for line, val in adds if line not in processed_adds]
            remaining_deletes.sort()
            remaining_adds.sort()
            di, ai = 0, 0
            while di < len(remaining_deletes) and ai < len(remaining_adds):
                old_line, del_value = remaining_deletes[di]
                new_line, add_value = remaining_adds[ai]

                if del_value != add_value:
                    modifications.append({
                        'type': 'modify',
                        "old_value": del_value,
                        "new_value": add_value,
                        "old_line": old_line,
                        "new_line": new_line
                    })
                processed_deletes.add(old_line)
                processed_adds.add(new_line)
                di += 1
                ai += 1
            for old_line, del_value in deletes:
                if old_line not in processed_deletes:
                    modifications.append({
                        'type': 'deleted',
                        "old_value": del_value,
                        "new_value": None,
                        "old_line": old_line,
                        "new_line": None
                    })
            for new_line, add_value in adds:
                if new_line not in processed_adds:
                    modifications.append({
                        'type': 'added',
                        "old_value": None,
                        "new_value": add_value,
                        "old_line": None,
                        "new_line": new_line
                    })
        except Exception as ex:
            print(f"_match_column_modifications 执行发生未捕获异常: {ex}")
        finally:
            return modifications

    def _find_tab_attribute_creation(self, file_path: str, tab_attribute: str, column_index: int, encoding: str) -> list:
        modifications = []
        try:
            result = subprocess.run(
                ['svn', 'blame', self._get_svn_path_modify(file_path), '-v'],
                capture_output=True, text=True, check=True, encoding=encoding
            )
            lines = result.stdout.strip().split('\n')
            for row_num, line in enumerate(lines, 1):
                if line.strip():
                    line_items = line.split()
                    if len(line_items) >= 2:
                        rev = line_items[0]
                        author = line_items[1]

                        # 获取该修订的详细信息
                        description = ""
                        log_cmd = ['svn', 'log', '-v', '-r', rev, self._get_svn_path_modify(file_path)]
                        try:
                            log_res = subprocess.run(log_cmd, capture_output=True, text=True, check=True, encoding=encoding, timeout=30)
                            if log_res.returncode == 0 and log_res.stdout:
                                raw_output = log_res.stdout
                                lines_log = raw_output.splitlines()
                                hist_log = self._parse_svn_log(lines_log)
                                if hist_log:
                                    description = hist_log[0]['description']
                        except Exception as ex:
                            pass

                        modifications.append({
                            "author": author,
                            "revision": rev,
                            "description": description,
                            "principal": self._get_principal(description),
                            "type": "created",
                            "old": None,
                            "new": None,
                            "old_line": None,
                            "new_line": row_num
                        })

        except Exception as ex:
            pass

        return modifications

    def _update_wrecker_info_by_line_num(self, file_path: str, data: Any, history: list, encoding: str):
        current_target_line = data['line_num']
        modification_chain = []
        hunk_info = None
        for hist in history:
            rev = hist['revision']
            author = hist['author']
            description = hist['description']
            diff_cmd = ['svn', 'diff', '-c', rev, self._get_svn_path_modify(file_path)]
            try:
                diff_res = subprocess.run(diff_cmd, capture_output=True, text=True, check=True, encoding=encoding, timeout=30)
            except Exception as ex:
                continue
            hunk_info = self._find_hunk_for_line(diff_res.stdout, current_target_line)
            if not hunk_info:
                continue
            
            chain_entry = {
                "author": author,
                "revision": rev,
                "description": description,
                "principal": self._get_principal(description),
                "old": hunk_info.get('old_content'),
                "new": hunk_info.get('new_content'),
                "type": hunk_info['type'],
                "old_line": hunk_info["old_line"],
                "new_line": hunk_info["new_line"]
            }
            old_line = hunk_info["old_line"]
            if hunk_info['type'] == 'deleted':
                break
            elif hunk_info['type'] == 'added':
                modification_chain.append(chain_entry)
                break
            else:
                if old_line is not None:
                    current_target_line = old_line
                if hunk_info['type'] == 'modify':
                    modification_chain.append(chain_entry)
        if len(modification_chain) == 0:
            result = subprocess.run(
                ['svn', 'blame', self._get_svn_path_modify(file_path), '-v'], 
                capture_output=True, text=True, check=True, encoding=encoding
            )
            lines = result.stdout.strip().split('\n')
            if lines and current_target_line <= len(lines):
                line_items = lines[current_target_line].split()
                rev = line_items[0]
                author = line_items[1]
                description = ""
                log_cmd = ['svn', 'log', '-v', '-r', rev, self._get_svn_path_modify(file_path)]
                try:
                    log_res = subprocess.run(log_cmd, capture_output=True, text=True, check=True, encoding=encoding, timeout=30)
                    if log_res.returncode == 0 and log_res.stdout:
                        raw_output = log_res.stdout
                        lines = raw_output.splitlines()
                        history = self._parse_svn_log(lines)
                        if history:
                            description = history[0]['description']
                except Exception as ex:
                    pass
                finally:
                    modification_chain.append({
                        "author": author,
                        "revision": rev,
                        "description": description,
                        "principal": self._get_principal(description),
                        "old": None, 
                        "new": None, 
                        "type": "modified"
                    })
        data['wrecker_info'] = modification_chain if modification_chain else None

    def _get_principal(self, description: str) -> list:
        principal = []
        if len(description) == 0:
            return principal
        try:
            submit_number = self._get_submit_number(description)
            url = f"https://gep.seasungame.com/api/devsimple-open/workitem/workItemInfo/{submit_number}"
            r = requests.request("GET", url)
            rsp = self.json_parser.parse(r.text)
            processed_rsp = process_workitem_data(rsp)
            data = processed_rsp.get('data', '')
            if data:
                for assigne in data.get('assignees', []):
                    user_id = assigne.get('userId', [])
                    principal.append(user_id)
        except Exception as ex:
            pass
        finally:
            return principal
        
    def _get_submit_number(self, description: str) -> int:
        """
        从description中提取出提交单号
        
        参数:
            description: 提交描述字符串
            
        返回:
            提取的提交单号（整数）
            
        示例:
            1. description: 【剑网3-C675187】优化"园圃驱蚊虫"的操作体验
               返回：675187
            2. description: 剑网3-87141】【仓库-提交单】科举优化
               返回：87141
            3. description: 9247百草园脚本
               返回：9247
        """
        import re
        
        # 如果描述为空，返回0
        if not description or not isinstance(description, str):
            return 0
        
        # 定义多种匹配模式，按优先级尝试
        patterns = [
            # 模式1: 【剑网3-C{数字}】
            r'【剑网3-C(\d+)】',
            # 模式2: 剑网3-{数字}】
            r'剑网3-(\d+)】',
            # 模式3: 【剑网3-{数字}】
            r'【剑网3-(\d+)】',
            # 模式4: {数字}开头
            r'^(\d+)',
            # 模式5: 任意位置包含{数字}（但不包含字母C）
            r'[^0-9C](\d{4,})',
            # 模式6: 任意位置包含{数字}
            r'(\d{4,})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, description)
            if match:
                try:
                    # 提取匹配的数字
                    number_str = match.group(1)
                    submit_number = int(number_str)
                    return submit_number
                except (ValueError, IndexError):
                    continue
        
        # 如果没有找到匹配的数字，尝试更通用的数字提取
        # 查找所有连续数字
        all_numbers = re.findall(r'\d+', description)
        if all_numbers:
            # 返回最长的数字（最有可能是提交单号）
            longest_number = max(all_numbers, key=len)
            try:
                return int(longest_number)
            except ValueError:
                pass
        
        # 如果仍然没有找到，返回0
        return 0