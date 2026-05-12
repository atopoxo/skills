from typing import List, Optional, Dict, Any
from datetime import datetime
from core.function.base_function import merge_dicts
from core.ai_model.base.ai_types import Message, InputData, Session
from core.storage.storage import Storage
from core.context.context_mgr import ContextMgr
from core.ai_model.manager.ai_model_mgr import AIModelMgr

class ChatMgr:
    def __init__(self, config: Any, user_id: str, storage: Storage, context_mgr: ContextMgr, default_model_id: str, default_tool_model_id: str):
        self.user_id: str = user_id
        self.storage: Storage = storage
        self.default_model_id: str = default_model_id
        self.default_tool_model_id: str = default_tool_model_id
        self.context_mgr = context_mgr
        self.ai_model_mgr = AIModelMgr(config, "log_analyzer", self.storage, self.context_mgr)

    def init_models(self):
        self.ai_model_mgr.set_selected_models(self.default_model_id, self.default_tool_model_id, self.user_id, 'chat')

    def add_session(self, instance_name: str):
        return self.storage.add_ai_instance_session(self.user_id, instance_name)
    
    def remove_session(self, instance_name: str, session_id: str):
        return self.storage.remove_ai_instance_session(self.user_id, instance_name, session_id)
    
    def get_session(self, instance_name: str, session_id: Optional[str] = None) -> Optional[Session]:
        return self.storage.get_ai_instance_session(self.user_id, instance_name, session_id)
    
    def chat_stream(self, signal, session: Session, use_knowledge: bool, tools_selected: List[Any], 
                         query: Optional[str] = None, index: Optional[int] = None, 
                         context_option: Optional[List[Any]] = None, context_expand: Optional[bool] = None, 
                         tool_model_extra: Optional[Dict] = None, model_extra: Optional[Dict] = None):
        
        history = self.get_messages(self.user_id, 'chat', session['session_id'], query, index, context_option, context_expand)       
        model_id = self.storage.get_ai_instance_model_id(self.user_id, 'chat')
        model_id = self.get_valid_model_id(model_id)
        
        tool_model_id = self.storage.get_ai_instance_tool_model_id(self.user_id, 'chat')
        tool_model_id = self.get_valid_tool_model_id(tool_model_id)
        
        tool_model_config = self.ai_model_mgr.get_model_config(tool_model_id)
        model_config = self.ai_model_mgr.get_model_config(model_id)
        
        real_tool_model_extra = merge_dicts(tool_model_config['extra'] if tool_model_config else None, tool_model_extra)
        real_model_extra = merge_dicts(model_config['extra'] if model_config else None, model_extra)
        
        data = InputData(
            user_id=self.user_id,
            instance_name='chat',
            session=session,
            history=history,
            index=index,
            tools_selected=tools_selected,
            use_knowledge=use_knowledge,
            model_config=model_config,
            tool_model_config=tool_model_config,
            cache=self.storage.get_ai_instance_cache(self.user_id, 'chat'),
            tool_model_extra=real_tool_model_extra,
            model_extra=real_model_extra
        )
        
        return self.ai_model_mgr.chat_stream(signal, model_id, data)

    def get_messages(self, user_id: str, instance_name: str, session_id: Optional[str] = None, 
                          query: Optional[str] = None, index: Optional[int] = None, 
                          context_option: Optional[List[Any]] = None, context_expand: Optional[bool] = None) -> List[Message]:
        
        message: Optional[Message] = None
        history: List[Message] = []
        if index is not None:
            if query:
                message = Message(role='user', content=query, timestamp=int(datetime.now().timestamp() * 1000), context_option=context_option, context_expand=context_expand)
                self.storage.update_user_info(user_id, instance_name, session_id, message, None, True, index)
            history = self.storage.get_ai_instance_messages(user_id, instance_name, session_id, True) or []
        else:
            message = Message(role='user', content=query, timestamp=int(datetime.now().timestamp() * 1000), context_option=context_option, context_expand=context_expand)
            self.storage.update_user_info(user_id, instance_name, session_id, message)
            history = self.storage.get_ai_instance_messages(user_id, instance_name, session_id, True) or []
            self.storage.add_ai_round(user_id, instance_name, session_id)
        round_count = self.storage.get_ai_round(user_id, instance_name, session_id)
        num = min(len(history), round_count)
        
        valid_num = 0
        valid_start = 0
        
        # 从后向前遍历查找 user 消息
        for i in range(len(history) - 1, -1, -1):
            if history[i]['role'] == 'user':
                valid_start = i
                valid_num += 1
            if valid_num >= num:
                break
                
        message_context = history[valid_start:]
        self.insert_date_time(message_context, 'user')
        total_len = sum(len(msg['content']) for msg in message_context)
        # print(f"len(message_context): {len(message_context)} total: {total_len}")   
        return message_context

    def insert_date_time(self, messages: List[Message], user: str):
        send_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        system_tips = Message(role="system", content=f"\n当前时间为：{send_time}\n", timestamp=int(datetime.now().timestamp() * 1000))
        
        if len(messages) > 0:
            if messages[0]['role'] != user:
                messages[0]['content'] = system_tips['content']
            else:
                messages.insert(0, system_tips)
        else:
            messages.append(system_tips)

    def get_valid_model_id(self, id: Optional[str]) -> str:
        return id if id else self.default_model_id

    def get_valid_tool_model_id(self, id: Optional[str]) -> str:
        return id if id else self.default_model_id