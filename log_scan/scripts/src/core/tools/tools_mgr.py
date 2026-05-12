import importlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable, TypeVar, Generic
from core.function.base_function import *
from core.json.json_parser import get_json_parser

T = TypeVar('T')

@dataclass
class ToolConfig(Generic[T]):
    id: str
    type: str
    next_tool_id: Optional[str] = None
    returns: Optional[Dict[str, Any]] = None
    # 动态属性
    def __getitem__(self, key):
        return getattr(self, key, None)
    
@dataclass
class ToolFunctionCall(Generic[T]):
    module: str
    cls: str  # 'class' is a keyword in Python
    name: str
    description: str
    parameters: Dict[str, Any]

@dataclass
class ToolCallFunction:
    module: str
    cls: str
    name: str
    arguments: Dict[str, Any]

@dataclass
class ToolCall:
    id: str
    function: ToolCallFunction

@dataclass
class ToolModuleCache:
    cache: Dict[str, Callable] = field(default_factory=dict)
    call: Any = None

@dataclass
class ToolCallInfo:
    id: str
    input: Dict[str, Any]
    output: Dict[str, Any]

@dataclass
class AIUsageTips:
    tools_describe: Optional[str] = None
    tools_usage: Optional[str] = None

@singleton
class ToolsMgr:
    def __init__(self, config: Any = None):
        self.config = config or {}
        self.tools: Dict[str, Dict[str, ToolModuleCache]] = {}
        self.json_parser = get_json_parser()
        self.tools_config: List[Dict[str, Any]] = []
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, 'config.json')
        self.tools_config = self.load_tools_config(config_path)
        self.load_tools(self.tools_config)

    def get_ai_usage_tips(self, tool_tips: Any, tool_calls: List[List[ToolCall]], tools_selected: List[Any]) -> AIUsageTips:
        result = AIUsageTips()
        tool_call_check_str = (
            "请直接生成如下格式的结果： \n"
            "```json\n"
            "{ \"tool_calls\":[ [ { \"id\": \"该工具的标示符，请不要修改\", \"function\": { \"module\": \"browser\", \"class\": \"Browser\", \"name\": \"search\", \"arguments\": { \"query\": \"需要搜索的关键词或问题，例如：'今日A股走势分析', '杭州天气'\", \"domain\": \"weather\" } } ] ] }\n"
            "```\n"
            "其中arguments为该工具的参数，其值用map表示，其中key为变量名，value为该变量的取值，例如：{\"query\": \"需要搜索的关键词或问题\"}，\"tool_calls\"中的每一项是一个array，它表示每一轮需要调用的工具列表，每一轮工具列表中的所有工具调用后，都需要调用大模型。 注意：\"tool_calls\"必须是一个二维的list，例如：[[], [], []]， 反之，请直接生成如下格式的结果： \n"
            "```json\n"
            "{ \"tool_calls\":[] }\n"
            "`"
        )
        
        if tool_tips:
            tools_usage = ""
            if tool_calls:
                if tool_calls[0]:
                    tool_calls_str = self.json_parser.to_json_str(tool_calls[0])
                    tools_usage = f"\n## 上一轮的分析认为，当前还需要调用如下工具：{tool_calls_str}，"
                
                if len(tool_calls) > 1:
                    next_tool_calls = tool_calls[1:]
                    next_tool_calls_str = self.json_parser.to_json_str(next_tool_calls)
                    tools_usage += f"之后的几轮分析还需要调用工具：{next_tool_calls_str}"
                
                tools_usage += f"\n请判断是否需要更新当前或之后几轮的调用工具集，如果需要，{tool_call_check_str}\n"
            else:
                tools_usage = f"\n## 请判断是否需要调用工具，如果需要，{tool_call_check_str}，"
            
            result.tools_usage = tools_usage
        else:
            tools = self.get_tools_config(tools_selected)
            tools_str = self.json_parser.to_json_str(tools)
            result.tools_describe = (
                f"\n## 在生成时请注意，回答当前的问题时，只能使用如下的工具： {tools_str} 参数解释： "
                "1.\"properties\"表示传入参数，其值用一个map表示，key为变量名，value为该变量的描述。 "
                "2.每个变量的描述用一个map表示，\"type\"表示该变量对应的python类型，\"description\"表示该变量的描述，\"default\"表示该变量的默认值，如果该变量没有默认值，则不填该字段。 "
                "3.\"required\"为必须要有的传入参数列表，其值用一个列表表示，列表中的每一项为变量名，例如：[\"query\"]。 "
                "4.\"name\"表示该函数名称，例如：\"search\"。 "
                "5.\"class\"表示该函数的类，例如：\"Browser\"。 "
                "6.\"module\"表示该函数的类，例如：\"browser\"。 "
                "7.\"type\"表示该工具的类型，例如：\"function\"，如果type为\"function\"，则表示该工具是一个函数，可以调用，并且\"function\"描述了如何调用该函数。\n"
            )
            result.tools_usage = f"\n## {tool_call_check_str}\n"
        
        return result

    def get_all_tools(self) -> List[Any]:
        return self.tools_config

    def get_tools(self, content: str) -> List[List[Dict[str, Any]]]:
        return self.parse_tools(content)

    def get_tool(self, tool_id: str) -> Optional[Dict[str, Any]]:
        tool_config = next((tool for tool in self.tools_config if tool['id'] == tool_id), None)
        if not tool_config:
            return None
        
        tool_type = tool_config['type']
        call = tool_config[tool_type]
        arg_map = {}
        
        for arg_name, arg_info in call['parameters']['properties'].items():
            arg_map[arg_name] = arg_info.get('default', None)
        
        return {
            'id': tool_config['id'],
            'next_tool_id': tool_config.get('next_tool_id'),
            tool_type: {
                'module': call['module'],
                'class': call['class'],
                'name': call['name'],
                'arguments': arg_map
            }
        }

    def call_tool(self, module_name: str, class_name: str, function_name: str, args: Dict[str, Any]) -> Any:
        module_name = module_name or ''
        if module_name not in self.tools:
            return None
        module_map = self.tools[module_name]
        class_name = class_name or ''
        if class_name not in module_map:
            return None
        class_map = module_map[class_name]
        class_call = class_map['call']

        function_name = function_name or ''
        if function_name not in class_map['cache']:
            return None
        
        function_call = class_map["cache"][function_name]
        if class_call:
            return getattr(class_call, function_call)(**args)
        else:
            return function_call(**args)

    def get_tools_config(self, tools_selected: List[Any]) -> List[Dict[str, Any]]:
        if tools_selected:
            return [tool for tool in self.tools_config if any(selected_id == tool['id'] for selected_id in tools_selected)]
        else:
            return self.tools_config

    def get_tool_return_property(self, module_name: str, class_name: str, function_name: str, variable: str) -> Optional[Any]:
        tool = next((t for t in self.tools_config 
                    if t[t['type']]['module'] == module_name 
                    and t[t['type']]['class'] == class_name 
                    and t[t['type']]['name'] == function_name), None)
        
        if not tool or 'returns' not in tool:
            return None
        
        return_prop = tool['returns']['properties'].get(variable)
        return return_prop if return_prop else None

    def get_tool_instance(self, module_name: str, class_name: str) -> Optional[Any]:
        if module_name not in self.tools:
            return None
        module_cache = self.tools[module_name]
        if class_name not in module_cache:
            return None
        return module_cache[class_name].call

    # =============== 私有方法 ===============

    def load_tools_config(self, file_path: str) -> List[Dict[str, Any]]:
        data = self.json_parser.read_json_file(file_path)
        return data.get('tools', [])

    def load_tools(self, tools_config: List[Dict[str, Any]]) -> None:
        for item in tools_config:
            class_name = None
            function_name = None
            try:
                tool_type = item['type']
                call = item[tool_type]
                module_name = call.get('module', 'base')
                parent_path = os.path.join(os.path.dirname(__file__), '../../tools')
                module_path = os.path.join(parent_path, f"{module_name}/{module_name}")
                spec = importlib.util.spec_from_file_location(module_name, module_path + ".py")
                if spec and spec.loader:
                    tool_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(tool_module)
                else:
                    continue
                if module_name not in self.tools:
                    self.tools[module_name] = {}
                module_cache = self.tools[module_name]
                class_name = call.get('class', '')
                if class_name not in module_cache:
                    class_instance = getattr(tool_module, class_name)(self.config)
                    module_cache[class_name] = ToolModuleCache(cache={}, call=class_instance)
                
                class_cache = module_cache[class_name].cache
                function_name = call.get('name', '')
                if function_name not in class_cache:
                    # 绑定方法
                    bound_method = getattr(module_cache[class_name].call, function_name)
                    class_cache[function_name] = bound_method
            except Exception as error:
                print(f"Failed to load tool {class_name}:{function_name} due to error: {error}")

    def parse_tools(self, content: str) -> List[List[Dict[str, Any]]]:
        try:
            tool_json = self.json_parser.parse(content)
            if 'tool_calls' in tool_json:
                return tool_json['tool_calls']
            return []
        except Exception as error:
            print("Tools parse failed", error)
            return []