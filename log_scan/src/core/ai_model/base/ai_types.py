from dataclasses import dataclass
from typing import List, Dict, Any, Optional, TypedDict, NotRequired

@dataclass
class ModelInfo:
    def __init__(
        self,
        url: str,
        id: str,
        platform: str,
        code_name: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
        name: str,
        type: str,
        show_config: bool,
        safe: bool,
        api_key: str,
        can_modify: bool
    ):
        self.url = url
        self.id = id
        self.platform = platform
        self.code_name = code_name
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.name = name
        self.type = type
        self.show_config = show_config
        self.safe = safe
        self.api_key = api_key
        self.can_modify = can_modify

@dataclass
class AICharacterInfo:
    def __init__(
        self,
        id: str,
        name: str,
        describe: str,
        can_modify: bool
    ):
        self.id = id
        self.name = name
        self.describe = describe
        self.can_modify = can_modify

@dataclass
class SearchEngineInfo:
    def __init__(
        self,
        id: str,
        name: str,
        engine_id: str,
        url: str,
        api_key: str,
        show_config: bool
    ):
        self.id = id
        self.name = name
        self.engine_id = engine_id
        self.url = url
        self.api_key = api_key
        self.show_config = show_config

# --- 接口 (Interfaces) 转换为 TypedDict ---

class ContextItem(TypedDict):
    type: str
    name: str
    paths: NotRequired[Optional[List[str]]]
    content: NotRequired[Optional[str]]
    range: NotRequired[Optional[Dict[str, Any]]] # 对应 { start, end, startLine, endLine }

class ContextOption(TypedDict):
    type: str
    id: str
    name: str
    describe: str
    icon: NotRequired[Optional[str]]
    context_item: NotRequired[Optional[ContextItem]]
    children: NotRequired[Optional[List['ContextOption']]] # 递归引用

class Message(TypedDict):
    role: str
    content: str
    timestamp: int
    context_option: NotRequired[Optional[List[ContextOption]]]
    context_expand: NotRequired[Optional[bool]]

class Cache(TypedDict):
    tools_usage: str
    tools_describe: str
    tool_calls: List[List[Any]] # 对应 ToolCall[][]，这里假设 Any 代表 ToolCall 结构
    context: str
    knowledge: str
    backup: str
    returns: Dict[str, Any] # 对应 { [key: string]: any }

class Session(TypedDict):
    session_id: str
    last_modified_timestamp: int
    name: str
    round: int
    history: List[Message]
    cache: Cache
    is_ai_stream_transfer: bool
    force_save: bool
    refresh: bool

class AIInstance(TypedDict):
    sessions: Dict[str, Session]
    selected_session_id: str
    model_id: NotRequired[Optional[str]]
    tool_model_id: NotRequired[Optional[str]]

class UserInfo(TypedDict):
    ai_config: Dict[str, Any]
    ai_instance: Dict[str, AIInstance]

class InputData(TypedDict):
    history: List[Message]
    cache: Cache
    index: NotRequired[Optional[int]]
    user_id: NotRequired[Optional[str]]
    instance_name: NotRequired[Optional[str]]
    session: NotRequired[Optional[Session]]
    tools_selected: NotRequired[Optional[List[Any]]]
    use_knowledge: NotRequired[Optional[bool]]
    model_config: NotRequired[Optional[Any]]
    tool_model_config: NotRequired[Optional[Any]]
    tool_model_extra: NotRequired[Optional[Any]]
    model_extra: NotRequired[Optional[Any]]

class ContentMap(TypedDict):
    think_content: str
    conclusion_content: str

class Delta(TypedDict):
    reasoning: NotRequired[Optional[str]]
    conclusion: NotRequired[Optional[str]]

class ContextTreeNode(TypedDict):
    value: Optional[ContextItem]
    children: List['ContextTreeNode'] # 递归引用，Python 3.7+ 需要字符串注解或 __future__ import