import os
import copy
from abc import ABC, abstractmethod
from typing import Any, List, Dict, Optional, Generator, Set
from datetime import datetime
from core.json.json_parser import get_json_parser
from core.context.context_mgr import ContextMgr
from core.tools.tools_mgr import ToolsMgr, ToolCall, ToolCallInfo
from core.ai_model.base.ai_types import ContentMap, Delta, InputData, Session, Message

class AIModelBase(ABC):
    def __init__(self, config: Any, helper: Any):
        self.json_parser = get_json_parser()
        self.config = config
        self.mode = "online"
        self.name = ""
        self.storage = helper.get("storage") if isinstance(helper, dict) else getattr(helper, 'storage', None)
        self.assistant = "assistant"
        self.sentence_divisions = ["。", "！", "!", "？", "?", "\n"]
        self.tools_mgr = ToolsMgr(config)
        
        self.context_mgr: Optional[ContextMgr] = helper.get("context_mgr") if isinstance(helper, dict) else getattr(helper, 'context_mgr', None)
        self.knowledge_mgr: Optional[Any] = helper.get("knowledge_mgr") if isinstance(helper, dict) else getattr(helper, 'knowledge_mgr', None)
        
        self.additional_tips = {
            "begin": "<|tips_start|>",
            "end": "<|tips_end|>"
        }

    @abstractmethod
    def chat_stream(self, signal: Any, input_data: Any) -> Generator[Any, None, None]:
        pass

    def set_tool_model(self, config: Any):
        raise NotImplementedError("Method not implemented.")

    def get_response(self, tool_model: bool, module_name: str, messages: List[Message], 
                           stream: bool = True, max_tokens: int = 8192, index: int = -1, extra: Any = None) -> Any:
        raise NotImplementedError("Method not implemented.")

    def get_tool_response(self, tool_model: bool, module_name: str, messages: List[Message], 
                                stream: bool = True, max_tokens: int = 8192, index: int = -1, extra: Any = None) -> Any:
        raise NotImplementedError("Method not implemented.")

    def get_delta(self, chunk: Any) -> Delta:
        raise NotImplementedError("Method not implemented.")

    def stream_generator_framework(self, signal: Any, input_data: InputData) -> Generator[Any, None, None]:
        need_save = True
        tools_selected = input_data.get("tools_selected", [])
        user_id = input_data.get("user_id")
        instance_name = input_data.get("instance_name")
        session: Session = input_data.get("session", {})
        session_id = session.get("session_id")
        messages: List[Message] = input_data.get("history", [])
        index = input_data.get("index") if input_data.get("index") is not None else len(messages) - 1
        use_knowledge = input_data.get("use_knowledge", False)
        model_config = input_data.get("model_config", {})
        model_name = model_config.get("model_name")
        max_tokens = model_config.get("max_tokens", 8192)
        tool_model_config = input_data.get("tool_model_config", {})
        tool_model_name = tool_model_config.get("model_name")
        tool_max_tokens = tool_model_config.get("max_tokens", 8192)
        cache = input_data.get("cache", {})
        tool_model_extra = input_data.get("tool_model_extra")
        model_extra = input_data.get("model_extra")
        message_replace = False
        has_task = True
        stream_content = ""
        current_index = index

        self.reset_cache(cache)
        self.set_tool_model({
            "api_key": tool_model_config.get("api_key"),
            "url": tool_model_config.get("url")
        })

        while has_task:
            try:
                # self.handle_references(messages, cache, current_index)
                self.handle_knowledge(use_knowledge, messages, cache, current_index)
                if len(tools_selected) > 0:
                    current_index = self.check_tool_tips(messages, cache, True, current_index, tools_selected)
                    content_map: ContentMap = {"think_content": "", "conclusion_content": ""}
                    for chunk in self.stream_generator(True, signal, user_id, session, tool_model_name, 
                                                             messages, tool_max_tokens, content_map, current_index, 
                                                             tool_model_extra, model_extra, message_replace, True):
                        yield chunk
                    current_index = self.check_tool_tips(messages, cache, False, current_index, tools_selected)
                    tools = self.tools_mgr.get_tools(content_map["conclusion_content"])
                    # yield* this.report_tool_infos(tools, contentMap.conclusion_content); # 注释掉的逻辑
                    filtered_tools = []
                    for tool_group in tools:
                        filtered_group = [tool for tool in tool_group if tool.get("id") in tools_selected]
                        if filtered_group:
                            filtered_tools.append(filtered_group)
                    tools = filtered_tools
                    tool_result = self.handle_tool_calls(tools, messages, cache, current_index)
                    tool_calls = tool_result.get("tool_calls", [])
                    if len(tool_calls) > 0:
                        tool_context = self.report_tool_use_infos(tool_calls)
                        yield tool_context
                        stream_content += tool_context
                    if not tool_result.get("ai") and cache.get("returns", {}).get("ai", {}).get("ai_conclusion"):
                        stream_content += cache["returns"]["ai"]["ai_conclusion"]
                        yield stream_content
                        break
                
                content_map: ContentMap = {"think_content": "", "conclusion_content": ""}
                yield from self.stream_generator(False, signal, user_id, session, model_name, 
                                                         messages, max_tokens, content_map, current_index, 
                                                         tool_model_extra, model_extra, message_replace, False)
                stream_content += content_map.get("think_content", "") + content_map.get("conclusion_content", "")
                if "returns" not in cache:
                    cache["returns"] = {"ai": {"ai_conclusion": ""}}
                if "ai" not in cache["returns"]:
                    cache["returns"]["ai"] = {"ai_conclusion": ""}
                cache["returns"]["ai"]["ai_conclusion"] = content_map.get("conclusion_content", "")
                has_task = len(cache.get("tool_calls", [])) > 0
            except Exception as ex:
                stream_content = "无法响应您的请求，请稍后再试..."
                yield stream_content
                print(f"Error: {ex}")
                break
            finally:
                self.save_messages(need_save, stream_content, messages, user_id, instance_name, session_id, message_replace, current_index)
                message_replace = True

        self.reset_cache(cache)
        self.save_cache(need_save, cache, user_id, instance_name, session_id)

    def reset_cache(self, cache: Dict):
        cache["tools_usage"] = ""
        cache["tools_describe"] = ""
        cache["context"] = ""
        cache["knowledge"] = ""
        cache["tool_calls"] = []
        cache["returns"] = {"ai": {"ai_conclusion": ""}}

    def check_tool_tips(self, messages: List[Message], cache: Dict, begin: bool, index: int, tools_selected: List) -> int:
        return_index = index
        if begin:
            pre_tool_tips = cache.get("tools_describe", "")
            tool_tips = self.tools_mgr.get_ai_usage_tips(pre_tool_tips, cache.get("tool_calls", []), tools_selected)
            tips_usage = f"{self.additional_tips['begin']}{tool_tips.get('tools_usage', '')}{self.additional_tips['end']}"
            if len(pre_tool_tips) <= 0:
                cache["tools_describe"] = tool_tips.get("tools_describe", "")
                if messages and len(messages) > 0:
                    messages[0]["content"] += cache["tools_describe"]
                if len(messages) > index:
                    cache["backup"] = copy.deepcopy(messages[index].get("content", ""))
                    messages[index]["content"] += tips_usage
            else:
                message = {
                    "role": "user",
                    "content": tips_usage,
                    "timestamp": int(datetime.now().timestamp() * 1000)
                }
                return_index = index + 2
                if return_index < len(messages):
                    messages.insert(return_index, message)
                else:
                    messages.append(message)
        else:
            if cache.get("backup"):
                if len(messages) > index:
                    messages[index]["content"] = cache["backup"]
                cache["backup"] = None
            else:
                if return_index < len(messages) and messages[return_index].get("role") == "user":
                    messages.pop(return_index)
                    return_index -= 2
        return return_index

    def report_tool_use_infos(self, tool_calls: List[ToolCallInfo]) -> str:
        result = "<ToolCalls>"
        for tool_call in tool_calls:
            result += "<ToolCall>"
            result += "<ToolCallId>"
            result += f"{tool_call.get('id', '')}"
            result += "</ToolCallId>"
            result += "<ToolCallInput>"
            result += "```json\n" + self.json_parser.to_json_str(tool_call.get("input", {}), 4) + "\n```"
            result += "</ToolCallInput>"
            result += "<ToolCallOutput>"
            output_data = tool_call.get("output", {}).get("data", {})
            result += self.json_parser.to_json_str(output_data, 4)
            result += "</ToolCallOutput>"
            result += "</ToolCall>"
        result += "</ToolCalls>"
        return result

    def stream_generator(self, tool_model: bool, signal: Any, user_id: Optional[str], session: Session, 
                               module_name: str, messages: List[Message], max_tokens: int, content_map: ContentMap, 
                               index: int, tool_model_extra: Any, model_extra: Any, message_replace: bool, 
                               use_tool_model: bool) -> Generator[Any, None, None]:
        response = None
        if use_tool_model:
            response = self.get_tool_response(tool_model, module_name, messages, True, max_tokens, index, tool_model_extra)
        else:
            response = self.get_response(tool_model, module_name, messages, True, max_tokens, index, model_extra)
        if response:
            for chunk in response:
                # if signal.aborted:
                #     return
                delta = self.get_delta(chunk)
                yield from self.handle_stream_normal_calls(delta, content_map)
                if session.get("force_save"):
                    stream_content = content_map.get("think_content", "") + content_map.get("conclusion_content", "")
                    self.save_session_messages(True, stream_content, messages, user_id, session, message_replace, index)
                    session["force_save"] = False
                    session["refresh"] = True
            yield from self.handle_stream_normal_calls(None, content_map)

    def handle_tool_calls(self, tools: List[List[ToolCall]], messages: List[Message], cache: Dict, index: int) -> Dict:
        current_tools: List[ToolCall] = []
        current_tool_calls: List[ToolCallInfo] = []
        tool_set: Set[str] = set()

        if len(tools) == 0:
            tools = cache.get("tool_calls", [])
        invalid_format = False
        for tool_list in tools:
            if not isinstance(tool_list, list):
                invalid_format = True
                break
        if invalid_format:
            tools = [tools] # type: ignore
        if len(tools) > 0:
            current_tools = tools[0]
            tools.pop(0)
        for tool_list in tools:
            for tool in tool_list:
                tool_set.add(tool.get("id", ""))
        
        tools_messages = {"return_to_ai": None}
        for call in current_tools:
            tool_id = call.get("id")
            tool_config = self.tools_mgr.get_tool(tool_id)
            next_tool_id = tool_config.get("next_tool_id") if tool_config else None
            
            if next_tool_id and next_tool_id not in tool_set:
                if len(tools) == 0:
                    tools.append([])
                next_tool = self.tools_mgr.get_tool(next_tool_id)
                if next_tool:
                    tools[0].append(next_tool)
                    tool_set.add(next_tool_id)
            
            func = call.get("function", {})
            module_name = func.get("module", "")
            class_name = func.get("class", "")
            function_name = func.get("name", "")
            args = self.parse_arguments(func.get("arguments"))
            for key, value in args.items():
                if isinstance(value, str) and value.startswith('$'):
                    temp = value[1:]
                    if ':' in temp:
                        ref_id, var_name = temp.split(':', 1)
                        returns = cache.get("returns", {})
                        if ref_id in returns and isinstance(returns[ref_id], dict):
                            args[key] = returns[ref_id].get(var_name)

            try:
                result = self.tools_mgr.call_tool(module_name, class_name, function_name, args)
                if result:
                    current_returns = []
                    for variable, item in result.items():
                        if isinstance(item, dict):
                            return_type = item.get("returnType")
                            show_type = item.get("showType")
                            item_value = item.get("value")
                        else:
                            return_type = "data"
                            show_type = "text"
                            item_value = item

                        if return_type == "ai_tips":
                            item_str = item_value if isinstance(item_value, str) else self.json_parser.to_json_str(item_value)
                            self.build_tools_messages(tools_messages, tool_id, item_str)
                        elif return_type == "ai_conclusion":
                            item_str = item_value if isinstance(item_value, str) else self.json_parser.to_json_str(item_value)
                            if "returns" not in cache: cache["returns"] = {}
                            if "ai" not in cache["returns"]: cache["returns"]["ai"] = {}
                            cache["returns"]["ai"]["ai_conclusion"] = item_str
                        else:
                            if "returns" not in cache: cache["returns"] = {}
                            cache["returns"][tool_id] = item # 存储完整 item 或 item_value? TS 中存的是 item
                            if "ai" not in cache["returns"]: cache["returns"]["ai"] = {}
                            cache["returns"]["ai"]["ai_conclusion"] = '已执行完所有工具'
                        if item:
                            current_return = {
                                "showType": show_type,
                                "value": item_value
                            }
                            current_returns.append(current_return)
                    if len(current_returns) > 0:
                        current_tool_call = {
                            "id": tool_id,
                            "input": {
                                "module": module_name,
                                "class": class_name,
                                "name": function_name,
                                "arguments": args
                            },
                            "output": {
                                "data": current_returns
                            }
                        }
                        current_tool_calls.append(current_tool_call)
            except Exception as ex:
                print(f"调用工具失败: {ex}")
        
        self.build_tools_messages(tools_messages, None, None)
        if tools_messages.get("return_to_ai"):
            flag = False
            if len(messages) > index:
                content = messages[index].get("content", "")
                for end in self.sentence_divisions:
                    if content.endswith(end):
                        flag = True
                        break
                if not flag:
                    messages[index]["content"] += "\n"
                messages[index]["content"] += f"{self.additional_tips['begin']}{tools_messages['return_to_ai']}{self.additional_tips['end']}"
        
        cache["tool_calls"] = tools
        return {
            "ai": tools_messages.get("return_to_ai"),
            "tool_calls": current_tool_calls
        }

    def parse_arguments(self, args: Any) -> Any:
        try:
            if isinstance(args, str):
                return self.json_parser.parse(args)
            return args
        except Exception as ex:
            print(f"参数解析失败: {ex}")
            return {}

    def build_tools_messages(self, tools_messages: Dict, tool_id: Optional[str], result: Optional[str]):
        if result:
            if tools_messages.get("return_to_ai") is None:
                tools_messages["return_to_ai"] = "根据用户的问题，以下是各个工具的调用情况：\n{\n"
            else:
                tools_messages["return_to_ai"] += ",\n"
            tools_messages["return_to_ai"] += f"{{'{tool_id}':{result}}}"
        else:
            if tools_messages.get("return_to_ai"):
                tools_messages["return_to_ai"] += "\n}\n"
                tools_messages["return_to_ai"] += "重要指令：工具调用产生的结果只能作为参考，并且你的回答更倾向于原问题而不是调用工具后的结果，此外回复的答案与不调用工具时候相比应该更加详细，在涉及到代码等问题时倾向于给出具体的实现。"

    # def handle_references(self, messages: List[Message], cache: Dict, index: int):
    #     if not cache.get("context") and self.context_mgr and len(messages) > index:
    #         context_option = messages[index].get("context_option")
    #         if context_option:
    #             context_describe = self.context_mgr.get_context(context_option, replace_byte)
    #             if context_describe:
    #                 cache["context"] = f"{self.additional_tips['begin']}{context_describe}{self.additional_tips['end']}"
    #                 messages[index]["content"] += cache["context"]

    def handle_knowledge(self, use_knowledge: bool, messages: List[Message], cache: Dict, index: int):
        if use_knowledge and not cache.get("knowledge") and self.knowledge_mgr and len(messages) > index:
            search_content = self.knowledge_mgr.search(messages[index].get("content", ""))
            if search_content:
                cache["knowledge"] = f"{self.additional_tips['begin']}{search_content}{self.additional_tips['end']}"
                messages[index]["content"] += cache["knowledge"]

    def handle_stream_normal_calls(self, delta: Optional[Delta], content_map: ContentMap) -> Generator[Any, None, None]:
        chunk_delta = ""
        if delta:
            reasoning = delta.get("reasoning")
            conclusion = delta.get("conclusion")
            if reasoning is not None:
                reasoning_content = reasoning
                if content_map["conclusion_content"].startswith("<conclusion>") and not content_map["conclusion_content"].endswith("</conclusion>"):
                    delta_content = "</conclusion>"
                    content_map["conclusion_content"] += delta_content
                    yield delta_content
                if not content_map["think_content"].startswith("<think>"):
                    reasoning_content = "<think>" + reasoning_content
                content_map["think_content"] += reasoning_content
                chunk_delta = reasoning_content
            elif conclusion is not None:
                conclusion_content = conclusion
                if content_map["think_content"].startswith("<think>") and not content_map["think_content"].endswith("</think>"):
                    delta_content = "</think>"
                    content_map["think_content"] += delta_content
                    yield delta_content
                if not content_map["conclusion_content"].startswith("<conclusion>"):
                    conclusion_content = "<conclusion>" + conclusion_content
                content_map["conclusion_content"] += conclusion_content
                chunk_delta = conclusion_content
            if chunk_delta:
                yield chunk_delta
        else:
            if content_map["think_content"].startswith("<think>") and not content_map["think_content"].endswith("</think>"):
                delta_content = "</think>"
                content_map["think_content"] += delta_content
                yield delta_content
            if content_map["conclusion_content"].startswith("<conclusion>") and not content_map["conclusion_content"].endswith("</conclusion>"):
                delta_content = "</conclusion>"
                content_map["conclusion_content"] += delta_content
                yield delta_content

    def save_messages(self, need_save: bool, response: str, history: List[Message], user_id: Optional[str], 
                            instance_name: Optional[str], session_id: Optional[str], message_replace: bool, index: int):
        if need_save and user_id and instance_name:
            ai_message_index = index + 1
            message: Message = {
                "role": self.assistant,
                "content": response,
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            if message_replace and ai_message_index < len(history):
                history[ai_message_index] = message
            else:
                if ai_message_index < len(history):
                    history[ai_message_index] = message
                else:
                    history.append(message)
            if self.storage:
                self.storage.update_user_info(user_id, instance_name, session_id, message, None, message_replace=message_replace, index=ai_message_index)

    def save_cache(self, need_save: bool, cache: Dict, user_id: Optional[str], instance_name: Optional[str], session_id: Optional[str]):
        if need_save and user_id and instance_name:
            if self.storage:
                self.storage.update_user_info(user_id, instance_name, session_id, None, cache)

    def save_session_messages(self, need_save: bool, response: str, history: List[Message], user_id: Optional[str], 
                                    session: Optional[Session], message_replace: bool, index: int):
        if need_save and user_id and session:
            ai_message_index = index + 1
            message: Message = {
                "role": self.assistant,
                "content": response,
                "timestamp": int(datetime.now().timestamp() * 1000)
            }
            if message_replace and ai_message_index < len(history):
                history[ai_message_index] = message
            else:
                if ai_message_index < len(history):
                    history[ai_message_index] = message
                else:
                    history.append(message)
            if self.storage:
                self.storage.update_user_info_by_session(user_id, session, message, None, message_replace=message_replace, ai_message_index=ai_message_index)

    def get_config(self) -> Any:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(current_dir, self.mode)
        config_path = os.path.join(config_path, self.name, "config.json")
        
        return self.json_parser.read_json_file(config_path)