from typing import Any
from pathlib import Path
import datetime
import html
import os
import uuid
from core.json.json_parser import get_json_parser

class ResultGenerate:
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.json_parser = get_json_parser()

    def get_result_dir(self, rel_path: str) -> str:
        current_dir = self.work_dir
        output_dir = os.path.join(current_dir, rel_path)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        result_dir = os.path.join(output_dir, f"final_result_{timestamp}")
        if not os.path.exists(result_dir):
            os.makedirs(result_dir)
        return result_dir
    
    def get_root_html_path(self, base_url: str, result_dir: str) -> dict:
        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        uid = str(uuid.uuid4())[:8]
        page_name = f"index_{timestamp}_{uid}.html"
        
        # 本地文件路径（用于写入文件）
        local_path = os.path.join(result_dir, page_name)
        
        # 获取result_dir相对于工作目录父目录的相对路径
        parent_work_dir = os.path.dirname(str(self.work_dir))
        rel_result_dir = os.path.relpath(result_dir, parent_work_dir)
        # 替换反斜杠为正斜杠，用于URL
        rel_result_dir = rel_result_dir.replace('\\', '/')
        
        # 构建完整的URL（用于外部访问）
        url_path = local_path  # 默认返回本地路径
        if base_url:
            # 确保base_url以/结尾
            if not base_url.endswith('/'):
                base_url = base_url + '/'
            # 构建完整的URL路径
            url_path = f"{base_url}{rel_result_dir}/{page_name}"
        
        return {
            'local_path': local_path,
            'url': url_path,
            'page_name': page_name,
            'result_dir': result_dir
        }

    def generate_empty_page(self, root_html_path: str, encoding: str):
        """
        生成空结果页面，显示"数据正常生成中..."
        
        参数:
        - root_html_path: 结果输出路径
        - encoding: 文件编码
        """
        # 空页面HTML模板
        empty_page_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="{encoding}">
    <title>代码分析结果</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; 
            padding: 20px; 
            background: #f9f9f9; 
            color: #333;
            line-height: 1.6;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }}
        .container {{
            text-align: center;
            max-width: 600px;
            padding: 40px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #27ae60;
            margin-bottom: 20px;
            font-size: 2em;
        }}
        .message {{
            color: #7f8c8d;
            font-size: 1.2em;
            margin-bottom: 30px;
        }}
        .status {{
            color: #3498db;
            font-size: 1em;
            font-weight: bold;
        }}
        .clock-icon {{
            font-size: 4em;
            color: #d4a017;
            margin-bottom: 20px;
            position: relative;
            display: inline-block;
            width: 1em;
            height: 1em;
        }}
        .clock-face {{
            position: absolute;
            width: 100%;
            height: 100%;
            border: 0.1em solid #d4a017;
            border-radius: 50%;
            background: #fff8dc;
        }}
        .clock-hour-hand {{
            position: absolute;
            width: 0.05em;
            height: 0.35em;
            background: #d4a017;
            top: 0.15em;
            left: 0.475em;
            transform-origin: bottom center;
            transform: rotate(30deg);
        }}
        .clock-minute-hand {{
            position: absolute;
            width: 0.05em;
            height: 0.45em;
            background: #d4a017;
            top: 0.05em;
            left: 0.475em;
            transform-origin: bottom center;
            transform: rotate(60deg);
        }}
        .clock-center {{
            position: absolute;
            width: 0.1em;
            height: 0.1em;
            background: #d4a017;
            border-radius: 50%;
            top: 0.45em;
            left: 0.45em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="clock-icon">
            <div class="clock-face"></div>
            <div class="clock-hour-hand"></div>
            <div class="clock-minute-hand"></div>
            <div class="clock-center"></div>
        </div>
        <h1>数据正在生成中...</h1>
        <div class="status">状态：正常</div>
    </div>
</body>
</html>"""
        
        # 保存空页面
        try:
            with open(root_html_path, 'w', encoding=encoding) as f:
                f.write(empty_page_html)
            print(f"[+] 空结果页面已生成: {root_html_path}")
        except Exception as ex:
            print(f"[!] 保存空结果页面失败: {ex}")

    def save_temporary(self, context_result: Any, encoding: str, step: int, tag: str) -> str:
        current_dir = self.work_dir
        output_dir = os.path.join(current_dir, ".temporary_results")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        file_path = os.path.join(output_dir, f"temporary_{tag}_{timestamp}.json")
        try:
            self.json_parser.write_to_file(context_result, file_path, ensure_ascii=False, indent=4, encoding=encoding)
            print(f"\n[*] 步骤{step}: 分析结果已保存至: {file_path}")
            return file_path
        except Exception as ex:
            print(f"\n[*] 步骤{step}: 保存文件{file_path}失败: {ex}")

    def load_temporary(self, file_path: str, encoding: str, step: int):
        try:
            return self.json_parser.read_from_file(file_path, encoding=encoding)
        except Exception as ex:
            print(f"\n[*] 步骤{step}: 加载文件{file_path}失败: {ex}")
            return None
        
    def save(self, context_result: Any, scripts_dir: str, encoding: str, result_dir: str, root_html_path: str, current_step: int) -> str:
        file_path = os.path.join(result_dir, f"total.json")
        try:
            self.json_parser.write_to_file(context_result, file_path, ensure_ascii=False, indent=4, encoding=encoding)
            self._save_to_html(context_result, scripts_dir, result_dir, 'utf-8', root_html_path)
            print(f"\n[*] 步骤{current_step}: 分析结果已保存至: {file_path}")
            return file_path
        except Exception as ex:
            print(f"\n[*] 步骤{current_step}: 保存文件{file_path}失败: {ex}")

    def _save_to_html(self, context_result: Any, scripts_dir: str, result_dir: str, encoding: str, root_html_path: str):
        html_files = []  # 存储生成的HTML文件信息
        
        for key, items in context_result.items():
            for item in items:
                path = item['file_path']
                line_num = item.get('line_num', None)
                suggestion = item.get('suggestion', None)
                error = item.get('error', None)
                error_msg = item.get('error_msg', None)
                tab_attribute = item.get('tab_attribute', None)
                path_split = os.path.splitext(path)
                path_without_ext = path_split[0]
                ext = path_split[1]
                dir_to_remove = scripts_dir.rstrip('/\\') + os.sep
                dir_to_remove = dir_to_remove.replace('\\', '/')
                if path_without_ext.startswith(dir_to_remove):
                    relative_path = path_without_ext[len(dir_to_remove):]
                else:
                    relative_path = path_without_ext
                safe_filename = relative_path.replace('/', '_').replace('\\', '_')
                final_filename = f"{key}_{safe_filename}_{line_num}.html"
                output_path = os.path.join(result_dir, final_filename)
                html_files.append({
                    'file_path': relative_path + ext,
                    'line_num': line_num,
                    'error': error,
                    'error_msg': error_msg,
                    'tab_attribute': tab_attribute,
                    'html_file': final_filename,
                    'wrecker_info': item.get('wrecker_info'),
                    'wrecker_index': item.get('wrecker_index', 0),
                    'update_error': item.get('update_error', None)
                })
                
                main_page_filename = os.path.basename(root_html_path)
                self._write_to_html(
                    output_path=output_path,
                    content=suggestion,
                    encoding=encoding,
                    file_path=relative_path + ext,
                    line_num=line_num,
                    error=error,
                    error_msg=error_msg,
                    tab_attribute=tab_attribute,
                    wrecker_info=item.get('wrecker_info'),
                    wrecker_index=item.get('wrecker_index', 0),
                    update_error=item.get('update_error', None),
                    main_page_filename=main_page_filename
                )
            
        # 生成主页面
        if html_files:
            self._generate_main_page(root_html_path, html_files, encoding)
        else:
            # 生成空结果页面
            self.generate_empty_page(root_html_path, encoding)

    def _build_tab_table_html(self, wrecker_info: list, wrecker_index: int, tab_attribute: str) -> str:
        if not wrecker_info:
            return ""
        info = wrecker_info[wrecker_index] if wrecker_index < len(wrecker_info) and wrecker_index >= 0 else wrecker_info[0]
        header = info.get('header', '')
        new_line_content = info.get('new_line_content', '')
        if not header and not new_line_content:
            return ""

        headers = header.split('\t')
        values = new_line_content.split('\t')
        if not headers:
            return ""

        # Find the column index for tab_attribute
        target_col = None
        for i, h in enumerate(headers):
            if tab_attribute == h:
                target_col = i
                break
        # Fallback: match against name part of typed headers (e.g. "id:int")
        if target_col is None:
            for i, h in enumerate(headers):
                if ':' in h and h.split(':', 1)[0] == tab_attribute:
                    target_col = i
                    break
        if target_col is None:
            target_col = -1

        max_cols = 8
        total_cols = max(len(headers), len(values) or 0)
        if total_cols <= max_cols:
            display_indices = set(range(total_cols))
            has_ellipsis = False
        else:
            has_ellipsis = True
            # Force: first 3 columns + target_col
            display_indices = set()
            for i in range(min(3, total_cols)):
                display_indices.add(i)
            if target_col >= 0 and target_col < total_cols:
                display_indices.add(target_col)
            # Fill remaining slots up to max_cols (reserve 1 for ellipsis)
            remaining = [i for i in range(total_cols) if i not in display_indices]
            available_slots = max_cols - len(display_indices)
            if available_slots > 0:
                for i in remaining[:available_slots]:
                    display_indices.add(i)
        sorted_indices = sorted(display_indices)

        def _build_cells(indices, get_text, cell_tag, is_target_col, is_header):
            cells = ""
            prev = None
            for i in indices:
                if has_ellipsis and prev is not None and i > prev + 1:
                    cells += f'<{cell_tag}>...</{cell_tag}>'
                text = get_text(i)
                is_target = is_target_col(i)
                cls = ' class="highlight"' if is_target else ""
                if is_target:
                    if is_header:
                        cells += f'<{cell_tag}{cls}>{self._html_escape(text)} <span class="badge">出错属性</span></{cell_tag}>'
                    else:
                        cells += f'<{cell_tag}{cls}>{self._html_escape(text)}</{cell_tag}>'
                else:
                    cells += f'<{cell_tag}{cls}>{self._html_escape(text)}</{cell_tag}>'
                prev = i
            if has_ellipsis and prev is not None and prev < total_cols - 1:
                cells += f'<{cell_tag}>...</{cell_tag}>'
            return cells

        header_cells = _build_cells(
            sorted_indices,
            lambda i: headers[i] if i < len(headers) else "",
            'th',
            lambda i: i == target_col,
            True
        )
        value_cells = _build_cells(
            sorted_indices,
            lambda i: values[i] if i < len(values) else "",
            'td',
            lambda i: i == target_col,
            False
        )

        return f'''<div class="section">
        <div class="section-title">Tab 表数据预览：</div>
        <div class="section-content">
            <table class="tab-table">
                <thead>
                    <tr>{header_cells}</tr>
                </thead>
                <tbody>
                    <tr>{value_cells}</tr>
                </tbody>
            </table>
        </div>
    </div>'''

    def _html_escape(self, text: str) -> str:
        import html
        return html.escape(str(text)) if text else ""

    def _write_to_html(self, output_path: str, content: str, encoding: str,
                      file_path: str = "", line_num: int = 0, error: str = "", error_msg: str = "", tab_attribute: str = "",
                      wrecker_info: list = None, wrecker_index: int = 0, update_error: str = None, main_page_filename: str = "index.html"):
        if content is None:
            suggestion_html = None
        else:
            try:
                import markdown
                # 将修改建议内容转换为 HTML
                suggestion_html = markdown.markdown(content, extensions=['fenced_code'])
            except ImportError:
                import html
                print("[!] 警告: 未安装 'markdown' 库，无法渲染代码高亮。正在使用纯文本模式。")
                print("[!] 建议执行: pip install markdown")
                suggestion_html = f"<pre>{self._html_escape(content)}</pre>"
            except Exception as e:
                print(f"[!] Markdown 转换失败: {e}")
                import html
                suggestion_html = f"<pre>{self._html_escape(content)}</pre>"

        # 根据 suggestion_html 是否为 None 动态生成 HTML 模板
        if suggestion_html is None or update_error:
            # 不显示代码修改建议部分
            suggestion_section = ""
        else:
            tips = "tab表修改建议" if tab_attribute else "代码修改建议"
            suggestion_section = f"""
    <div class="section">
        <div class="section-title">{tips}：</div>
        <div class="section-content">
            <div class="suggestion">
                {suggestion_html}
            </div>
        </div>
    </div>"""

        # 根据 tab_attribute 是否为 None 生成不同的 HTML 内容
        if tab_attribute is not None and tab_attribute != "":
            if update_error:
                tab_table_section = f'<div class="section"><div class="section-title">错误信息：</div><div class="section-content"><div class="error-reason">{self._html_escape(update_error)}</div></div></div>'
            else:
                tab_table_section = self._build_tab_table_html(wrecker_info, wrecker_index, tab_attribute)
            # 当 tab_attribute 不为 None 时的 HTML 模板
            html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="{encoding}">
    <title>代码修改建议详情</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            padding: 20px;
            background: #f9f9f9;
            color: #333;
            line-height: 1.6;
        }}
        .section {{
            margin-bottom: 30px;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .section-title {{
            font-size: 18px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #3498db;
        }}
        .section-content {{
            font-size: 14px;
            color: #555;
        }}
        .file-path {{
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            color: #2980b9;
            word-break: break-all;
        }}
        .line-num {{
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            color: #e74c3c;
            font-weight: bold;
            font-size: 16px;
        }}
        .error-reason {{
            color: #c0392b;
            background-color: #fdeaea;
            padding: 10px;
            border-radius: 5px;
            border-left: 4px solid #e74c3c;
        }}
        .suggestion {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #e9ecef;
        }}
        /* 代码块样式 */
        pre {{
            background-color: #282c34;
            color: #abb2bf;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            border: 1px solid #ddd;
            margin: 10px 0;
        }}
        code {{
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            background-color: #f4f4f4;
            padding: 2px 4px;
            border-radius: 3px;
            color: #e83e8c;
        }}
        pre code {{
            background-color: transparent;
            padding: 0;
            color: inherit;
        }}
        blockquote {{
            border-left: 4px solid #ccc;
            padding-left: 15px;
            color: #666;
            margin: 0;
        }}
        .back-link {{
            margin-top: 30px;
            text-align: center;
        }}
        .back-link a {{
            color: #3498db;
            text-decoration: none;
            font-weight: bold;
        }}
        .back-link a:hover {{
            color: #2980b9;
            text-decoration: underline;
        }}
        .tab-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            font-size: 13px;
        }}
        .tab-table th, .tab-table td {{
            border: 1px solid #ddd;
            padding: 8px 10px;
            text-align: left;
            max-width: 150px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .tab-table th {{
            background-color: #f0f0f0;
            font-weight: bold;
            color: #2c3e50;
        }}
        .tab-table .highlight {{
            background-color: #fff3cd;
            font-weight: bold;
            color: #856404;
        }}
        .badge {{
            display: inline-block;
            font-size: 10px;
            background: #e74c3c;
            color: white;
            padding: 1px 6px;
            border-radius: 8px;
            margin-left: 4px;
            vertical-align: middle;
        }}
    </style>
</head>
<body>
    <div class="section">
        <div class="section-title">出错的tab表路径：</div>
        <div class="section-content">
            <div class="file-path">{file_path if file_path else "文件路径未提供"}</div>
        </div>
    </div>

    <div class="section">
        <div class="section-title">出错的tab表属性：</div>
        <div class="section-content">
            <div class="line-num">{tab_attribute if tab_attribute else "tab表属性未提供"}</div>
        </div>
    </div>

    <div class="section">
        <div class="section-title">c++报错行代码信息：</div>
        <div class="section-content">
            <div class="error-reason">{line_num if line_num else "未知"} 行: {error_msg if error_msg else "c++报错行代码信息未提供"}</div>
        </div>
    </div>

    {tab_table_section}

    {suggestion_section}

    <div class="back-link">
        <a href="{main_page_filename}" target="_self">返回主页面</a>
    </div>
</body>
</html>"""
        else:
            # 当 tab_attribute 为 None 时的 HTML 模板（保持原样）
            html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="{encoding}">
    <title>代码修改建议详情</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            padding: 20px;
            background: #f9f9f9;
            color: #333;
            line-height: 1.6;
        }}
        .section {{
            margin-bottom: 30px;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        .section-title {{
            font-size: 18px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #3498db;
        }}
        .section-content {{
            font-size: 14px;
            color: #555;
        }}
        .file-path {{
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            color: #2980b9;
            word-break: break-all;
        }}
        .line-num {{
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            color: #e74c3c;
            font-weight: bold;
            font-size: 16px;
        }}
        .error-reason {{
            color: #c0392b;
            background-color: #fdeaea;
            padding: 10px;
            border-radius: 5px;
            border-left: 4px solid #e74c3c;
        }}
        .suggestion {{
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #e9ecef;
        }}
        /* 代码块样式 */
        pre {{
            background-color: #282c34;
            color: #abb2bf;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            border: 1px solid #ddd;
            margin: 10px 0;
        }}
        code {{
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            background-color: #f4f4f4;
            padding: 2px 4px;
            border-radius: 3px;
            color: #e83e8c;
        }}
        pre code {{
            background-color: transparent;
            padding: 0;
            color: inherit;
        }}
        blockquote {{
            border-left: 4px solid #ccc;
            padding-left: 15px;
            color: #666;
            margin: 0;
        }}
        .back-link {{
            margin-top: 30px;
            text-align: center;
        }}
        .back-link a {{
            color: #3498db;
            text-decoration: none;
            font-weight: bold;
        }}
        .back-link a:hover {{
            color: #2980b9;
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="section">
        <div class="section-title">报错文件路径：</div>
        <div class="section-content">
            <div class="file-path">{file_path if file_path else "文件路径未提供"}</div>
        </div>
    </div>

    <div class="section">
        <div class="section-title">报错行：</div>
        <div class="section-content">
            <div class="line-num">第 {line_num if line_num else "未知"} 行</div>
        </div>
    </div>

    <div class="section">
        <div class="section-title">报错原因：</div>
        <div class="section-content">
            <div class="error-reason">{error if error else "错误原因未提供"}</div>
        </div>
    </div>

    {suggestion_section}

    <div class="back-link">
        <a href="{main_page_filename}" target="_self">返回主页面</a>
    </div>
</body>
</html>"""
        
        try:
            with open(output_path, 'w', encoding=encoding) as f:
                f.write(html_template)
        except Exception as e:
            print(f"[!] 保存文件 {output_path} 失败: {e}")

    def _generate_main_page(self, root_html_path: str, html_files: list, encoding: str):
        """
        生成主页面，包含所有生成的HTML文件的链接表格
        
        参数:
        - root_html_path: 结果输出路径
        - html_files: HTML文件信息列表
        - encoding: 文件编码
        """
        # 生成表格行
        table_rows = ""
        for file_info in html_files:
            file_path = file_info['file_path']
            error = file_info['error'] if file_info.get('error') else file_info.get('error_msg', None)
            wrecker_info = file_info.get('wrecker_info')
            wrecker_index = file_info.get('wrecker_index', 0)
            html_file = file_info.get('html_file', None)
            
            description = ""
            author = ""
            principal = []
            if wrecker_info and isinstance(wrecker_info, list) and wrecker_index >= 0 and len(wrecker_info) > wrecker_index:
                info = wrecker_info[wrecker_index]
                description = info.get('description', '')
                author = info.get('author', '')
                principal = info.get('principal', [])
            
            if not file_info.get('update_error') and (wrecker_index == -1 or not html_file):
                suggestion_cell = '问题已修复/暂未找到问题'
            elif html_file:
                suggestion_cell = f'<a href="{html_file}" target="_blank">详情</a>'
            else:
                suggestion_cell = '-'
            table_rows += f"""
            <tr>
                <td>{file_path}</td>
                <td>{description}</td>
                <td>{author}</td>
                <td>{', '.join(principal)}</td>
                <td>{error}</td>
                <td>{suggestion_cell}</td>
            </tr>"""
        
        # 主页面HTML模板
        main_page_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="{encoding}">
    <title>代码修改建议汇总</title>
    <style>
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; 
            padding: 20px; 
            background: #f9f9f9; 
            color: #333;
            line-height: 1.6;
        }}
        h1 {{
            text-align: center;
            color: #2c3e50;
            margin-bottom: 30px;
        }}
        .stats {{
            text-align: center;
            margin-bottom: 20px;
            color: #7f8c8d;
            font-size: 14px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: white;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            border-radius: 5px;
            overflow: hidden;
        }}
        th {{
            background-color: #3498db;
            color: white;
            font-weight: bold;
            text-align: left;
            padding: 15px;
            position: sticky;
            top: 0;
        }}
        td {{
            padding: 12px 15px;
            border-bottom: 1px solid #ecf0f1;
        }}
        tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}
        tr:hover {{
            background-color: #e8f4fc;
        }}
        a {{
            color: #2980b9;
            text-decoration: none;
            font-weight: bold;
        }}
        a:hover {{
            color: #1a5276;
            text-decoration: underline;
        }}
        .file-path {{
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .description {{
            max-width: 400px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
    </style>
</head>
<body>
    <h1>代码修改建议汇总</h1>
    <div class="stats">共 {len(html_files)} 个建议</div>
    <table>
        <thead>
            <tr>
                <th>文件路径</th>
                <th>描述</th>
                <th>修改人</th>
                <th>负责人</th>
                <th>错误原因</th>
                <th>建议</th>
            </tr>
        </thead>
        <tbody>
            {table_rows}
        </tbody>
    </table>
</body>
</html>"""
        
        # 保存主页面
        main_page_path = root_html_path
        try:
            with open(main_page_path, 'w', encoding=encoding) as f:
                f.write(main_page_html)
            print(f"[+] 主页面已生成: {main_page_path}")
        except Exception as e:
            print(f"[!] 保存主页面失败: {e}")