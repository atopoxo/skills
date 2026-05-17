import datetime
import os
from typing import Any
from core.json.json_parser import get_json_parser
from settings.global_config import GlobalConfig
from core.function.base_function import singleton
from core.logs.log_manager import LogManager
from core.storage.storage import Storage
from core.context.context_mgr import ContextMgr
from core.tools.tools_mgr import ToolsMgr
from skills.chat_manager import ChatMgr
from skills.log_extract.log_extract import LogExtract
from skills.modify_tips import ModifyTips
from skills.lua_call_finder.lua_call_finder import LuaCallFinder
from skills.error_analyse.error_analyse import ErrorAnalyse
from skills.find_wrecker.find_wrecker import FindWrecker
from skills.result_generate.result_generate import ResultGenerate
from skills.extract_file.extract_file import ExtractFile
from skills.cpp_function_extractor.cpp_function_extractor import CppFunctionExtractor
from skills.tab_file_extractor.tab_file_extractor import TabFileExtractor
from skills.cpp_tab_call_analyse.cpp_tab_call_analyse import CppTabCallAnalyse
from skills.tab_error_finder.tab_error_finder import TabErrorFinder
from skills.cpp_error_analyse.cpp_error_analyse import CppErrorAnalyse

analyzer = None

@singleton
class Analyzer:
    def __init__(self, user_id, cwd):
        self.user_id = user_id
        self.cwd = cwd
        self.db_path = os.path.join(cwd, "log_analyzer.db")
        self.root_html_path = None

    def get_root_html_path(self):
        return self.root_html_path

    def init_env(self):
        self.json_parser = get_json_parser()
        self.global_config = GlobalConfig()
        config = self.global_config.get_config()
        self.log_mgr = LogManager(None, None)
        self.storage = Storage({}, self.user_id, self.db_path)
        self.storage.init_databases()
        self.context_mgr = ContextMgr(config.get('extension_name', ''))
        self.context_mgr.init()
        self.tools_mgr = ToolsMgr(config)
        self.chat_mgr = ChatMgr(config, 'admin', self.storage, self.context_mgr, config.get('default_model_id', 'online/volcengine-deepseek-chat'), config.get('default_tool_model', 'online/volcengine-deepseek-chat'))
        self.chat_mgr.init_models()
        custom_config_path = os.path.join(self.cwd, "custom_config.json")
        self.custom_config = self.json_parser.read_json_file(custom_config_path)
        self.log_extractor = LogExtract(custom_config_path, self.cwd)
        self.tips_analyzer = ModifyTips(custom_config_path, self.context_mgr)
        self.lua_call_finder = LuaCallFinder()
        self.error_analyzer = ErrorAnalyse(custom_config_path, self.context_mgr, self.chat_mgr)
        self.svn_finder = FindWrecker(custom_config_path, self.chat_mgr)
        self.result_generator = ResultGenerate(self.cwd)
        self.extract_file = ExtractFile()
        self.cpp_function_extractor = CppFunctionExtractor(custom_config_path, self.cwd)
        self.tab_file_extractor = TabFileExtractor(custom_config_path, self.cwd)
        self.cpp_tab_call_analyse = CppTabCallAnalyse(custom_config_path, self.chat_mgr, self.cwd)
        self.tab_error_finder = TabErrorFinder(custom_config_path)
        self.cpp_error_analyzer = CppErrorAnalyse(custom_config_path, self.context_mgr, self.chat_mgr)

    def analyse_log_file(self, func_name_to_body_path: str, tab_file_pairs_path: str, log_paths: list, product_dir: str, encoding: str, result_dir: str, root_html_path: str, temporary_file_path: str, save_temporary_result: bool, max_workers: int = 16, start_day: str = None):
        current_step = 1
        context_result = {}
        if (func_name_to_body_path and tab_file_pairs_path) or temporary_file_path:
            if func_name_to_body_path:
                cpp_funcbody = self.cpp_function_extractor.load(func_name_to_body_path, encoding)
                current_step = 2
            if tab_file_pairs_path:
                tab_infos = self.tab_file_extractor.load(tab_file_pairs_path, encoding)
                current_step = 2
            if temporary_file_path and 'temporary_reference_' in temporary_file_path:
                context_result = self.result_generator.load_temporary(temporary_file_path, encoding, current_step)
                current_step = 4
            elif temporary_file_path and 'temporary_analyse_' in temporary_file_path:
                context_result = self.result_generator.load_temporary(temporary_file_path, encoding, current_step)
                current_step = 5
            elif temporary_file_path and 'temporary_svn_' in temporary_file_path:
                context_result = self.result_generator.load_temporary(temporary_file_path, encoding, current_step)
                current_step = 7
            elif temporary_file_path and 'total.json' in temporary_file_path:
                context_result = self.result_generator.load_temporary(temporary_file_path, encoding, current_step)
                current_step = 7
        if current_step == 1:
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{current_time}] 步骤{current_step}: 正在从服务器日志中提取函数名和文件信息...")
            tab_infos = self.tab_file_extractor.generate_tab_file_info()
            self.tab_file_extractor.save(tab_infos, 'tab_infos', encoding, current_step)
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{current_time}] 步骤{current_step}: 正在从代码库提取函数信息...")
            cpp_funcbody = self.cpp_function_extractor.extract_functions(encoding, max_workers)
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{current_time}] 步骤{current_step}: 正在用ai分析c++代码调用tab表信息...")
            self.cpp_tab_call_analyse.analyse(cpp_funcbody, 5, max_workers, current_step)
            self.cpp_function_extractor.save(cpp_funcbody, 'cpp_funcbody', encoding, current_step)
            current_step += 1
        if current_step == 2:
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{current_time}] 步骤{current_step}: 正在解析日志...")
            (errors, count) = self.log_extractor.extract(log_paths, encoding)
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{current_time}] 发现 {count} 处脚本报错(包含重复)。")
            (unique_errors, unique_error_count) = self.log_extractor.get_unique_errors(product_dir, errors, encoding)
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{current_time}] 发现 {unique_error_count} 处独一无二的脚本报错。")
            self.log_extractor.save_remain_log(unique_errors["else"], encoding)
            current_step += 1
        if current_step == 3:
            script_dirs = []
            rel_path_list = [
                'client/scripts',
                'server/arena_scripts',
                'server/battlefield_scripts',
                'server/center_scripts'
            ]
            for rel_path in rel_path_list:
                script_dirs.append(os.path.join(product_dir, rel_path).replace('\\', '/'))
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{current_time}] 步骤{current_step}: 正在检查脚本调用tab接口的参数...")
            context_result["tab_load"] = self.tab_error_finder.find(unique_errors["tab_load"], cpp_funcbody["functions"], tab_infos, product_dir, encoding, 1, current_step)
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{current_time}] 步骤{current_step}: 正在检查脚本调用c接口的参数...")
            context_result["lua_call"] = self.lua_call_finder.find(unique_errors["lua_call"], script_dirs, encoding, max_workers)
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{current_time}] 步骤{current_step}: 正在分析上下文引用...")
            context_result["lua"] = self.tips_analyzer.get_modify_tips(unique_errors["lua"], 5, encoding, max_workers)
            if save_temporary_result:
                self.result_generator.save_temporary(context_result, encoding, current_step, 'reference')
            current_step += 1
            kinds = ["lua", "lua_call", "tab_load", "c/c++"]
            for kind in kinds:
                if not context_result.get(kind):
                    context_result[kind] = []
                self._add_source(context_result[kind], "analyzer")
        if current_step == 4:
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{current_time}] 步骤{current_step}: 大模型正在分析改进建议...")
            context_result["tab_load"] = self.cpp_error_analyzer.analyse(context_result["tab_load"], 5, encoding, max_workers, current_step)
            context_result["lua"] = self.error_analyzer.analyse(context_result["lua"], 5, encoding, max_workers, current_step)
            if save_temporary_result:
                self.result_generator.save_temporary(context_result, encoding, current_step, 'analyse')
            current_step += 1
        if current_step == 5:
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{current_time}] 步骤{current_step}: 正在查询SVN责任人...")
            self.svn_finder.get_blame_by_history(context_result, encoding, max_workers, start_day)
            current_step += 1
        if current_step == 6:
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{current_time}] 步骤{current_step}: 正在分析SVN责任人...")
            self.svn_finder.analyse_wrecker(context_result, 5, True, encoding, max_workers)
            if save_temporary_result:
                self.result_generator.save_temporary(context_result, encoding, current_step, 'svn')
            current_step += 1
        # if current_step == 7:
        #     current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        #     print(f"[{current_time}] 步骤{current_step}: 输出最终报告...")
        #     cpp_roots = [src['root'] for src in self.custom_config.get('cpp_source', [])]
        #     cpp_source_dir = os.path.commonpath(cpp_roots) if cpp_roots else ''
        #     self.result_generator.save(context_result, [product_dir, cpp_source_dir], encoding=encoding, result_dir=result_dir, root_html_path=root_html_path, current_step=current_step)
        #     current_step += 1
    
    def run(self, cwd: str, log_path: str, data: dict) -> str:
        log_dir = os.path.join(cwd, "input")
        os.makedirs(log_dir, exist_ok=True)
        self.extract_file.extract(log_path, log_dir)
        version = data.get("version")
        script_map = self.custom_config.get("script_map", {})
        product_dir = script_map.get(version, "z:/trunk")
        log_files = [os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith('.log')]

        if len(log_files) > 0 and os.path.exists(product_dir):
            result_dir = self.result_generator.get_result_dir(rel_path=".results")
            html_path_info = self.result_generator.get_root_html_path(self.custom_config.get("base_url", ""), result_dir)
            
            # 获取本地路径和URL
            local_html_path = html_path_info['local_path']
            accessible_url = html_path_info['url']
            self.result_generator.generate_empty_page(local_html_path, 'utf-8')
            self.root_html_path = accessible_url
            # self.analyse_log_file(rf"Y:\AI\skills\log_scan\scripts\.temporary_results\temporary_cpp_funcbody_2026_05_11_21_06_40.json", 
            #                       rf"Y:\AI\skills\log_scan\scripts\.temporary_results\temporary_tab_infos_2026_05_11_20_41_52.json", 
            #                       log_files, product_dir, 'gbk', result_dir, local_html_path, 
            #                       rf"Y:\AI\skills\log_scan\scripts\.temporary_results\temporary_svn_2026_05_20_12_20_54.json", True, 16, start_day=None)
            self.analyse_log_file(rf"Y:\AI\skills\log_scan\scripts\.temporary_results\temporary_cpp_funcbody_2026_05_11_21_06_40.json", 
                                  rf"Y:\AI\skills\log_scan\scripts\.temporary_results\temporary_tab_infos_2026_05_11_20_41_52.json", 
                                  log_files, product_dir, 'gbk', result_dir, local_html_path, 
                                  rf"y:\AI\skills\log_scan\scripts\.results\final_result_2026_05_16_22_21_51\total.json", True, 16, start_day=None)
            # self.analyse_log_file(None, 
            #                       None, 
            #                       log_files, product_dir, 'gbk', result_dir, local_html_path, None, True)
            return accessible_url
        else:
            return None
        
    def _add_source(self, data: Any, tag: str):
        for item in data:
            item["source"] = tag

def get_analyzer() -> Analyzer:
    global analyzer
    cwd = os.path.join(os.getcwd(), "scripts")
    analyzer = Analyzer("admin", cwd)
    return analyzer

def execute(analyzer: Analyzer, log_path: str, data: dict):
    cwd = os.path.join(os.getcwd(), "scripts")
    os.chdir(cwd)
    analyzer.init_env()
    return analyzer.run(cwd, log_path, data)

def get_root_html_path(analyzer: Analyzer) -> str:
    if analyzer:
        return analyzer.get_root_html_path()
    else:
        return None
    
if __name__ == "__main__":
    log_path = rf"Y:\AI\skills\log_scan\scripts\input.zip"
    data = {
        "version": "bvt",
    }
    analyzer = get_analyzer()
    execute(analyzer, log_path, data)
