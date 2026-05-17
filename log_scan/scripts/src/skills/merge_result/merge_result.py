# merge_result.py
import json
import glob
import os
import datetime

from skills.result_generate.result_generate import ResultGenerate


class MergeResult:
    def __init__(self, cwd: str):
        self.cwd = cwd

    def merge_result(self, result_dir: str) -> bool:
        """将 temporary_else_analysis.json 与最新 temporary_svn_*.json 合并，替换 total.json。

        Args:
            result_dir: final_result_{timestamp} 目录的绝对路径

        Returns:
            是否执行了合并（False 表示无需合并或合并失败）
        """
        else_path = os.path.join(result_dir, "temporary_else_analysis.json")

        if not os.path.exists(else_path):
            print("[跳过] 无可归类的 temporary_else 报错，无需合并")
            return False

        with open(else_path, 'r', encoding='utf-8') as f:
            else_data = json.load(f)

        categories = ['tab_load', 'lua_call', 'lua', 'c/c++']
        all_empty = all(len(else_data.get(cat, [])) == 0 for cat in categories)
        if all_empty:
            print("[跳过] temporary_else_analysis 所有分类均为空，无需合并")
            return False

        # 读取最新 temporary_svn_*.json
        svn_files = sorted(glob.glob(os.path.join(self.cwd, ".temporary_results", "temporary_svn_*.json")))
        if not svn_files:
            print("[错误] 未找到 temporary_svn_*.json 文件")
            return False

        latest_svn = svn_files[-1]
        print(f"[合并] 读取 SVN 数据: {os.path.basename(latest_svn)}")

        # temporary_svn 文件使用 GBK 编码
        try:
            with open(latest_svn, 'r', encoding='gbk') as f:
                svn_data = json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            with open(latest_svn, 'r', encoding='utf-8') as f:
                svn_data = json.load(f)

        # 按 category 逐一合并
        for cat in categories:
            added = len(else_data.get(cat, []))
            svn_data[cat].extend(else_data.get(cat, []))
            if added > 0:
                print(f"  {cat}: +{added} 条 (总计 {len(svn_data[cat])} 条)")

        # 替换 total.json
        total_path = os.path.join(result_dir, "total.json")
        with open(total_path, 'w', encoding='utf-8') as f:
            json.dump(svn_data, f, ensure_ascii=False, indent=4)
        print(f"[完成] 已更新 total.json")
        return True

    def regenerate_report(self, result_dir: str, product_dir, encoding: str = 'gbk') -> bool:
        """读取合并后的 total.json，仿照 analyzer.py 步骤 7 重新生成 HTML 报告。

        参数与 analyzer.py 中 analyse_log_file 的 step 7 调用一致：
        - context_result 从 total.json 读入
        - current_step=8（表示合并后重新生成的步骤）

        Args:
            result_dir: final_result_{timestamp} 目录的绝对路径
            product_dir: 产品目录路径（对应 script_map 中的值，如 z:/trunk）
            encoding: 文件编码，默认 gbk

        Returns:
            是否成功重新生成
        """
        total_path = os.path.join(result_dir, "total.json")
        if not os.path.exists(total_path):
            print(f"[错误] total.json 不存在: {total_path}")
            return False

        # 读取合并后的 context_result
        try:
            with open(total_path, 'r', encoding='utf-8') as f:
                context_result = json.load(f)
        except UnicodeDecodeError:
            with open(total_path, 'r', encoding='gbk') as f:
                context_result = json.load(f)

        # 找到 result_dir 中已有的 index_*.html 作为 root_html_path
        html_files = sorted(glob.glob(os.path.join(result_dir, "index_*.html")))
        if not html_files:
            print(f"[错误] 未找到 index_*.html 文件于: {result_dir}")
            return False
        root_html_path = html_files[-1]

        current_step = 8
        current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{current_time}] 步骤{current_step}: 重新生成最终报告（含 temporary_else 合并结果）...")

        result_generator = ResultGenerate(self.cwd)
        result_generator.save(context_result, product_dir, encoding=encoding,
                              result_dir=result_dir, root_html_path=root_html_path,
                              current_step=current_step)
        return True
