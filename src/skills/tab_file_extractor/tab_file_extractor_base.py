#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从日志目录中提取 C 代码日志并排序
日志格式: KGLogPrintf(KGLOG_ERR, "[TAB_FILE->] [%s,%s]", GetCallerFunctionName(), pcszFileName)
按照第一个参数(函数名)再第二个参数(文件名)的ASCII顺序排序
"""

import re
import os
from typing import List, Tuple, Optional, Any
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from skills.skill_base import SkillBase

class TabFileExtractorBase(SkillBase):
    
    def __init__(self, config_path: str):
        super().__init__(config_path)
        self.log_path = self.config['server_whole_log_path']
        self.tab_file_pattern = re.compile(r'\[TAB_FILE->\]\s*\[([^,]+),([^\]]+)\]')
        self.func_file_pairs: List[Tuple[str, str]] = []
        self.processed_files: List[str] = []
        self.failed_files: List[str] = []
        self.lock = threading.Lock()  # 线程锁，用于保护共享状态

    def _is_log_file(self, file_path: str) -> bool:
        """
        判断是否为日志文件

        Args:
            file_path: 文件路径

        Returns:
            bool: 如果是日志文件返回True
        """
        # 常见的日志文件扩展名
        log_extensions = {'.log', '.txt', '.LOG', '.TXT'}
        # 或者文件名包含log关键词
        file_name = os.path.basename(file_path).lower()
        return (os.path.splitext(file_path)[1] in log_extensions or
                'log' in file_name)

    def _extract_from_file(self, file_path: str, encoding: str = 'utf-8') -> int:
        """
        从单个日志文件中提取数据

        Args:
            file_path: 日志文件路径
            encoding: 文件编码

        Returns:
            int: 从该文件中提取的记录数量
        """
        count = 0
        local_pairs = []  # 本地存储提取的对，最后一次性添加到共享列表

        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
        except UnicodeDecodeError:
            # 尝试其他编码
            try:
                with open(file_path, 'r', encoding='gbk') as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='latin-1') as f:
                        content = f.read()
                except Exception as e:
                    with self.lock:
                        self.failed_files.append(f"{file_path} (编码错误: {e})")
                    return 0
        except Exception as e:
            with self.lock:
                self.failed_files.append(f"{file_path} (读取错误: {e})")
            return 0

        # 搜索 [TAB_FILE->] 模式
        matches = self.tab_file_pattern.findall(content)

        for match in matches:
            if len(match) == 2:
                func_name = match[0].strip()
                file_name = match[1].strip()
                # 清理可能的引号或空格
                func_name = func_name.strip('"\' ')
                file_name = file_name.strip('"\' ')
                if func_name and file_name:
                    local_pairs.append((func_name, file_name.replace('\\', '/')))
                    count += 1

        # 批量添加提取的对
        if local_pairs:
            with self.lock:
                self.func_file_pairs.extend(local_pairs)

        return count

    def _extract_logs(self, encoding: str = 'utf-8', max_workers: Optional[int] = None) -> List[Tuple[str, str]]:
        """
        从日志目录中提取所有日志文件的函数名和文件名对

        Args:
            encoding: 文件编码
            max_workers: 最大工作线程数，None表示自动计算

        Returns:
            List[Tuple[str, str]]: (函数名, 文件名) 对的列表
        """
        if not os.path.exists(self.log_path):
            print(f"Error: Path '{self.log_path}' does not exist")
            return []

        # 如果是文件，直接处理该文件
        if os.path.isfile(self.log_path):
            count = self._extract_from_file(self.log_path, encoding)
            if count > 0:
                with self.lock:
                    self.processed_files.append(self.log_path)
            return self.func_file_pairs

        # 如果是目录，收集所有日志文件
        log_files = []
        for root, _, files in os.walk(self.log_path):
            for file in files:
                file_path = os.path.join(root, file)
                if self._is_log_file(file_path):
                    log_files.append(file_path)

        total_files = len(log_files)
        if total_files == 0:
            print("No log files found")
            return []

        print(f"Found {total_files} log files, starting extraction...")

        # 如果没有指定max_workers，使用默认值
        if max_workers is None:
            # 最大线程数设为8，但不超过文件数量
            max_workers = min(8, total_files)
        else:
            # 确保max_workers不超过文件数量
            max_workers = min(max_workers, total_files)

        print(f"Using {max_workers} worker threads")

        # 使用线程池并行处理文件，添加进度条
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 创建进度条
            with tqdm(total=total_files, desc="提取日志文件", unit="文件") as pbar:
                # 提交所有任务
                future_to_file = {
                    executor.submit(self._extract_file_wrapper, file_path, encoding): file_path
                    for file_path in log_files
                }

                # 处理完成的任务
                for future in as_completed(future_to_file):
                    file_path = future_to_file[future]
                    try:
                        count, success = future.result()
                        if success and count > 0:
                            with self.lock:
                                self.processed_files.append(file_path)
                    except Exception as ex:
                        with self.lock:
                            self.failed_files.append(f"{file_path} (处理错误: {ex})")
                    finally:
                        pbar.update(1)
        return self.func_file_pairs

    def _extract_file_wrapper(self, file_path: str, encoding: str) -> Tuple[int, bool]:
        """
        线程安全的文件提取包装器

        Args:
            file_path: 文件路径
            encoding: 文件编码

        Returns:
            Tuple[int, bool]: (提取的记录数量, 是否成功)
        """
        try:
            count = self._extract_from_file(file_path, encoding)
            return count, True
        except Exception as ex:
            with self.lock:
                self.failed_files.append(f"{file_path} (处理错误: {ex})")
            return 0, False

    def _sort_pairs(self) -> List[Tuple[str, str]]:
        # 去重处理：使用字典保持顺序（Python 3.7+ 保持插入顺序）
        # 以(func_name, file_name)为键，值为None
        unique_dict = {}
        for pair in self.func_file_pairs:
            unique_dict[pair] = None

        # 获取去重后的键（即唯一的(func_name, file_name)对）
        unique_pairs = list(unique_dict.keys())

        # 先按函数名排序，再按文件名排序
        return sorted(unique_pairs, key=lambda x: (x[0], x[1]))
    
    def _get_func_name_to_files(self) -> Any:
        func_name_to_files = {}
        for pair in self.func_file_pairs:
            func_name, path = pair
            if func_name not in func_name_to_files:
                func_name_to_files[func_name] = set()
            if path not in func_name_to_files[func_name]:
                func_name_to_files[func_name].add(path)
        return func_name_to_files
    
    def _set_to_list(self, data: Any) -> Any:
        result = {}
        for key, value in data.items():
            result[key] = list(value)
        return result
    
    def _list_to_set(self, data: Any) -> Any:
        result = {}
        for key, value in data.items():
            result[key] = set(value)
        return result