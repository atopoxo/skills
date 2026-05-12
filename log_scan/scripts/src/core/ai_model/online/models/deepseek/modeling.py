import copy
from openai import OpenAI
from typing import Any, AsyncIterable, List, Optional, Union
from core.function.base_function import merge
from core.ai_model.online.base.ai_model_online_base import AIModelOnlineBase
from core.ai_model.base.ai_types import Delta

class DeepSeek(AIModelOnlineBase):
    def __init__(self, config: Any, helper: Any):
        super().__init__(config, helper)
        model_config = config
        self.client: OpenAI = OpenAI(
            api_key=model_config['api_key'],
            base_url=model_config['url']
        )
        self.tool_client: Optional[OpenAI] = None
    
    def chat_stream(self, signal: Any, data: Any) -> Any:
        return super().chat_stream(signal, data)
    
    def set_tool_model(self, model_config: Any) -> None:
        self.tool_client = OpenAI(
            api_key=model_config['api_key'],
            base_url=model_config['url']
        )
    
    def get_response(
        self,
        tool_model: bool,
        module_name: str,
        messages: List[Any],
        stream: bool = True,
        max_tokens: int = 8192,
        index: int = -1,
        extra: Any = None
    ) -> Union[AsyncIterable[Any], Any]:
        client = self.tool_client if tool_model else self.client
        
        # 创建参数对象
        params = {
            "model": module_name,
            "messages": messages[:index + 1] if index >= 0 else messages,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        if extra:
            extra_body = {'extra_body': extra}
            params = merge(copy.deepcopy(params), extra_body)
        
        return client.chat.completions.create(**params)
    
    def get_tool_response(
        self,
        tool_model: bool,
        module_name: str,
        messages: List[Any],
        stream: bool = True,
        max_tokens: int = 8192,
        index: int = -1,
        extra: Any = None
    ) -> Union[AsyncIterable[Any], Any]:
        client = self.tool_client if tool_model else self.client
        
        filtered_messages: List[Any] = []
        if len(messages) >= 1:
            last_user_message = None
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get('role') == 'user':
                    last_user_message = messages[i]
                    break
            
            if last_user_message:
                # 保留第一条消息和最后一条用户消息
                filtered_messages = [messages[0], last_user_message]
        
        params = {
            "model": module_name,
            "messages": filtered_messages,
            "max_tokens": max_tokens,
            "stream": stream
        }
        
        if extra:
            extra_body = {'extra_body': extra}
            params = merge(copy.deepcopy(params), extra_body)
        
        return client.chat.completions.create(**params)
    
    def get_delta(self, chunk: Any) -> Delta:
        choice = chunk.choices[0] if chunk.choices else None
        delta_data = choice.delta if choice else None
        
        if delta_data:
            return Delta(
                reasoning=getattr(delta_data, "reasoning_content", None) if hasattr(delta_data, "reasoning_content") else None,
                conclusion=getattr(delta_data, "content", None) if hasattr(delta_data, "content") else None
            )
        else:
            return Delta(
                reasoning=None,
                conclusion=None
            )

def get_class(config: Any, helper: Any) -> DeepSeek:
    return DeepSeek(config, helper)