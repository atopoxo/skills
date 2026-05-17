# else_analyzer.py
import threading
import subprocess
import datetime
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from typing import Any
from skills.skill_base import SkillBase


class ElseAnalyzer(SkillBase):
    def __init__(self, config_path):
        super().__init__(config_path)
        self.use_svn = self.config.get('svn', {}).get('use_svn', False)

    def read_files(self, file_paths: list, encoding: str = 'gbk', max_workers: int = 16) -> dict:
        """
        并行读取多个文件。

        参数:
        - file_paths: 要读取的文件路径列表
        - encoding: 文件编码
        - max_workers: 最大并行线程数，默认 16

        返回:
        - {file_path: lines_list} 字典，lines_list 为文件每一行组成的列表
        """
        result = {}
        unique_paths = list(dict.fromkeys(file_paths))
        if not unique_paths:
            return result

        total = len(unique_paths)
        pbar = tqdm(total=total, desc="并行读取文件", unit="file")
        progress_lock = threading.Lock()
        actual_workers = min(max_workers, total)

        try:
            with ThreadPoolExecutor(max_workers=actual_workers) as executor:
                future_to_path = {
                    executor.submit(
                        self._read_single_file, path, encoding
                    ): path for path in unique_paths
                }
                for future in as_completed(future_to_path):
                    path = future_to_path[future]
                    try:
                        result[path] = future.result()
                    except Exception as ex:
                        current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        print(f"[{current_time}] 读取文件 {path} 失败: {ex}")
                        result[path] = []
                    finally:
                        with progress_lock:
                            pbar.update(1)
        finally:
            pbar.close()

        return result

    def _read_single_file(self, file_path: str, encoding: str) -> list:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read().splitlines()
        except Exception:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read().splitlines()
            except Exception:
                return []

    def svn_query(self, file_paths: list, encoding: str = 'gbk', max_workers: int = 16) -> dict:
        """
        并行执行 SVN blame 查询。

        参数:
        - file_paths: 要查询的 SVN 文件路径列表
        - encoding: 文件编码
        - max_workers: 最大并行线程数，默认 16

        返回:
        - {file_path: svn_info_list} 字典，svn_info_list 每项包含 {author, revision, description, principal}
        """
        result = {}
        if not self.use_svn:
            print("[!] SVN 查询已禁用")
            return result

        unique_paths = list(dict.fromkeys(file_paths))
        if not unique_paths:
            return result

        total = len(unique_paths)
        pbar = tqdm(total=total, desc="并行SVN查询", unit="file")
        progress_lock = threading.Lock()
        actual_workers = min(max_workers, total)

        try:
            with ThreadPoolExecutor(max_workers=actual_workers) as executor:
                future_to_path = {
                    executor.submit(
                        self._svn_blame_single, path, encoding
                    ): path for path in unique_paths
                }
                for future in as_completed(future_to_path):
                    path = future_to_path[future]
                    try:
                        result[path] = future.result()
                    except Exception as ex:
                        current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        print(f"[{current_time}] SVN 查询 {path} 失败: {ex}")
                        result[path] = []
                    finally:
                        with progress_lock:
                            pbar.update(1)
        finally:
            pbar.close()

        return result

    def _svn_blame_single(self, file_path: str, encoding: str) -> list:
        try:
            blame_res = subprocess.run(
                ['svn', 'blame', file_path, '-v'],
                capture_output=True, text=False, timeout=30
            )
            if blame_res.returncode != 0 or not blame_res.stdout:
                return []

            raw_output = blame_res.stdout.decode(encoding, errors='ignore')
            if not raw_output.strip():
                return []

            lines = raw_output.strip().split('\n')
            history = []
            seen_revs = set()
            for row_num, line in enumerate(lines, 1):
                if not line.strip():
                    continue
                items = line.split()
                if len(items) < 2:
                    continue
                rev = items[0]
                author = items[1]
                if rev in seen_revs:
                    continue
                seen_revs.add(rev)

                description = self._get_svn_revision_description(file_path, rev, encoding)
                history.append({
                    'author': author,
                    'revision': rev,
                    'description': description,
                    'principal': self._get_principal(description)
                })
            return history
        except subprocess.TimeoutExpired:
            print(f"SVN blame {file_path} 超时")
            return []
        except Exception as ex:
            print(f"SVN blame {file_path} 异常: {ex}")
            return []

    def _get_svn_revision_description(self, file_path: str, rev: str, encoding: str) -> str:
        try:
            log_cmd = ['svn', 'log', '-v', '-r', rev, file_path]
            log_res = subprocess.run(log_cmd, capture_output=True, text=False, timeout=30)
            if log_res.returncode == 0 and log_res.stdout:
                raw_output = log_res.stdout.decode(encoding, errors='ignore')
                lines = raw_output.splitlines()
                history = self._parse_svn_log(lines)
                if history:
                    return history[0].get('description', '')
        except Exception:
            pass
        return ''

    def _parse_svn_log(self, lines):
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

    def _get_principal(self, description: str) -> list:
        principal = []
        if not description:
            return principal
        try:
            import requests
            from skills.submit_tool.GetAssignees import process_workitem_data
            submit_number = self._get_submit_number(description)
            url = f"https://gep.seasungame.com/api/devsimple-open/workitem/workItemInfo/{submit_number}"
            r = requests.get(url)
            rsp = self.json_parser.parse(r.text)
            processed_rsp = process_workitem_data(rsp)
            data = processed_rsp.get('data', '')
            if data:
                for assigne in data.get('assignees', []):
                    user_id = assigne.get('userId', [])
                    principal.append(user_id)
        except Exception:
            pass
        return principal

    def _get_submit_number(self, description: str) -> int:
        import re
        if not description or not isinstance(description, str):
            return 0
        patterns = [
            r'【剑网3-C(\d+)】',
            r'剑网3-(\d+)】',
            r'【剑网3-(\d+)】',
            r'^(\d+)',
            r'[^0-9C](\d{4,})',
            r'(\d{4,})'
        ]
        for pattern in patterns:
            match = re.search(pattern, description)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue
        all_numbers = re.findall(r'\d+', description)
        if all_numbers:
            try:
                return int(max(all_numbers, key=len))
            except ValueError:
                pass
        return 0
