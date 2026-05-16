#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从日志目录中提取 C 代码日志并排序
日志格式: KGLogPrintf(KGLOG_ERR, "[TAB_FILE->] [%s,%s]", GetCallerFunctionName(), pcszFileName)
按照第一个参数(函数名)再第二个参数(文件名)的ASCII顺序排序
"""
import sys
import os
import datetime
from typing import Optional, Any, List, Tuple
import argparse
from skills.tab_file_extractor.tab_file_extractor_base import TabFileExtractorBase

class TabFileExtractor(TabFileExtractorBase):
    
    def __init__(self, config_path: str, work_dir: str):
        super().__init__(config_path)
        self.work_dir = work_dir

    def generate_tab_file_info(self, encoding: str = 'gbk', max_workers: Optional[int] = None) -> Any:
        # 检查路径是否存在
        log_dir = self.log_path
        if not os.path.exists(log_dir):
            print(f"错误: 路径 '{log_dir}' 不存在")
            print("请提供正确的日志文件或目录路径")
            return False

        self.func_file_pairs.clear()
        self.processed_files.clear()
        self.failed_files.clear()

        # 提取日志
        print("\n开始提取日志...")
        pairs = self._extract_logs(encoding, max_workers)
        if not pairs:
            print("没有找到匹配的日志记录")
            return False
        print(f"\n处理统计:")
        print(f"  处理文件: {len(self.processed_files)}")
        print(f"  失败文件: {len(self.failed_files)}")
        print(f"  找到的记录总数: {len(self.func_file_pairs)}")
        self.func_file_pairs = self._sort_pairs()
        print(f"  去重后的唯一记录数: {len(self.func_file_pairs)}")
        self.func_name_to_files = self._get_func_name_to_files()
        if self.failed_files:
            print(f"\nFailed files:")
            for failed in self.failed_files:
                print(f"  - {failed}")
        return self.func_name_to_files
    
    def load(self, path: str, encoding: str = 'utf-8') -> List[Tuple[str, str]]:
        """
        从保存的文件中加载数据，形成List[Tuple[str, str]]结构

        Args:
            path: 文件路径
            encoding: 文件编码 (默认: utf-8)

        Returns:
            List[Tuple[str, str]]: (函数名, 文件名) 对的列表
        """
        try:
            value = self.json_parser.read_from_file(path, encoding)
            self.func_name_to_files = self._list_to_set(value)
            print(f"从 {path} 成功加载 {len(self.func_name_to_files)} 条记录")
            return self.func_name_to_files

        except FileNotFoundError:
            print(f"错误: 文件 '{path}' 不存在")
            return []
        except Exception as ex:
            print(f"加载文件时出错: {ex}")
            return []

    def save(self, data: Any, tag: str, encoding: str, step: int) -> None:
        # output_lines = []
        # output_lines.append("FunctionName\tFileName")
        # for func_name, file_name in self.func_file_pairs:
        #     output_lines.append(f'{func_name}\t{file_name.replace("\\", "/")}')

        current_dir = self.work_dir
        output_dir = os.path.join(current_dir, ".temporary_results")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        file_path = os.path.join(output_dir, f"temporary_{tag}_{timestamp}.json")
        try:
            data_in_list = self._set_to_list(data)
            self.json_parser.write_to_file(data=data_in_list, file_path=file_path, ensure_ascii=False, indent=4, encoding=encoding)
            print(f"\n[*] 步骤{step}: 提取结果已保存至: {file_path}")
            return file_path
        except Exception as ex:
            print(f"\n[*] 步骤{step}: 保存文件{file_path}失败: {ex}")