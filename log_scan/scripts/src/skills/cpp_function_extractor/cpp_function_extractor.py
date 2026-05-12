#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从C/C++源代码中提取函数名和函数体，输出为JSON格式
支持三种函数名格式：
1. KCoinShop::KCoinShopVoucherSettings::LoadVoucherSettings (嵌套类)
2. KCoinShopVoucherSettings_vk::LoadVoucherSettings (普通类)
3. DynamicLoadVoucherSettings (全局函数)

支持命名空间跟踪，包括宏定义的命名空间。
"""
import os
import datetime
from typing import Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from skills.cpp_function_extractor.cpp_function_extractor_base import CppFunctionExtractorBase

class CppFunctionExtractor(CppFunctionExtractorBase):
    def __init__(self, config_path: str):
        super().__init__(config_path)

    def extract_macros(self, all_files: list, total_files: int, encoding: str = 'gbk', max_workers: Optional[int] = None) -> Dict[str, Any]:
        if max_workers is None:
            max_workers = min(16, total_files, os.cpu_count() * 2 or 4)
        else:
            max_workers = min(max_workers, total_files)

        print(f"  找到 {total_files} 个文件，使用 {max_workers} 个工作线程扫描宏定义...")
        with tqdm(total=total_files, desc="预扫描宏定义", unit="文件") as pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_file = {
                    executor.submit(self._extract_macro_file_wrapper, file_path, encoding): file_path
                    for file_path in all_files
                }

                for future in as_completed(future_to_file):
                    pbar.update(1)

        local_count = 0
        for file_path, macros in self.macros['local'].items():
            local_count += len(macros)
        global_count = len(self.macros['global'])
        all_macro_count = global_count + local_count
        print(f"  预扫描完成: 共 {all_macro_count} 个宏定义 (全局: {global_count}, 文件局部: {local_count})")

        return self.macros

    def extract_functions(self, encoding: str = 'gbk', max_workers: Optional[int] = None) -> Dict[str, Any]:
        for source in self.cpp_source:
            source_path = source["root"]
            if not os.path.exists(source_path):
                print(f"错误: 路径 '{source_path}' 不存在")
                print("请提供正确的源代码文件或目录路径")
                return {}

        self.functions.clear()
        self.processed_files.clear()
        self.failed_files.clear()

        cpp_files = []
        print("正在扫描C++文件...")
        for source in self.cpp_source:
            source_root = source.get("root", "")
            black_list = source.get("black_list", [])
            for root, dirs, files in os.walk(source_root):
                # 过滤黑名单目录：跳过黑名单中的子目录
                dirs[:] = [d for d in dirs if d not in black_list and not d.startswith('.')]
                for file in files:
                    file_path = os.path.join(root, file)
                    if self._is_cpp_file(file_path):
                        cpp_files.append(file_path.replace('\\', '/'))

        total_files = len(cpp_files)
        if total_files == 0:
            print("没有找到C++文件")
            return self.functions

        self.extract_macros(cpp_files, total_files, encoding, max_workers)
        print(f"找到 {total_files} 个C++文件，开始并行提取...")

        if max_workers is None:
            max_workers = min(16, total_files, os.cpu_count() * 2 or 4)
        else:
            max_workers = min(max_workers, total_files)

        print(f"使用 {max_workers} 个工作线程")

        with tqdm(total=total_files, desc="提取函数", unit="文件") as pbar:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_file = {
                    executor.submit(self._extract_file_wrapper, file_path, encoding): file_path
                    for file_path in cpp_files
                }

                for future in as_completed(future_to_file):
                    file_path = future_to_file[future]
                    try:
                        result = future.result()
                        if result:
                            count, processed = result
                            if processed:
                                with self.file_lock:
                                    self.processed_files.append(file_path)
                            pbar.set_postfix({
                                "成功": len(self.processed_files),
                                "失败": len(self.failed_files),
                                "函数": len(self.functions)
                            })
                    except Exception as ex:
                        with self.file_lock:
                            self.failed_files.append(f"{file_path} (处理错误: {ex})")
                    finally:
                        pbar.update(1)

        print(f"\n处理完成:")
        print(f"  总共处理文件: {total_files}")
        print(f"  成功处理文件: {len(self.processed_files)}")
        print(f"  失败文件: {len(self.failed_files)}")
        print(f"  提取的函数数量: {len(self.functions)}")

        if self.failed_files:
            print(f"\n失败的文件列表 (前10个):")
            for i, failed_file in enumerate(self.failed_files[:10]):
                print(f"  {i+1}. {failed_file}")
            if len(self.failed_files) > 10:
                print(f"  ... 还有 {len(self.failed_files) - 10} 个失败文件")

        return {
            "macros": self.macros,
            "functions": self.functions
        }

    def load(self, path: str, encoding: str = 'utf-8') -> Dict[str, Any]:
        """
        从保存的JSON文件中加载函数数据

        Args:
            path: JSON文件路径
            encoding: 文件编码 (默认: utf-8)

        Returns:
            Dict[str, Any]: 函数名 -> 函数体的字典
        """
        try:
            self.functions = self.json_parser.read_from_file(path, encoding)
            print(f"从 {path} 成功加载 {len(self.functions)} 个函数")
            return self.functions
        except Exception as ex:
            print(f"错误: JSON文件 '{path}' 格式不正确: {ex}")
            return {}

    def save(self, data: Any, tag: str, encoding: str, step: int) -> None:
        """保存结果为JSON格式"""
        if not self.functions:
            print("没有找到函数")
            return None

        current_dir = os.getcwd()
        output_dir = os.path.join(current_dir, ".temporary_results")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        file_path = os.path.join(output_dir, f"temporary_{tag}_{timestamp}.json")
        try:
            self.json_parser.write_to_file(data=data, file_path=file_path, ensure_ascii=False, indent=4, encoding=encoding)
            print(f"\n[*] 步骤{step}: 提取结果已保存至: {file_path}")
            return file_path
        except Exception as ex:
            print(f"\n[*] 步骤{step}: 保存文件{file_path}失败: {ex}")