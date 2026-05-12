import asyncpg
import sqlite3
from typing import Any, Dict, List, Optional
from pathlib import Path
import uuid
import time
import threading
from datetime import datetime
from core.function.base_function import singleton
from core.ai_model.base.ai_types import Cache
from core.json.json_parser import get_json_parser
from core.ai_model.base.ai_types import Message, Session, AIInstance, UserInfo

@singleton
class Storage:
    MAX_SESSION_NAME_LENGTH = 60

    def __init__(self, config: Any, user_id: str, db_path: str):
        self.json_parser = get_json_parser()
        self.user_cache: Optional[UserInfo] = None
        self.local_db: Optional[sqlite3.Connection] = None
        self.remote_db: Optional[asyncpg.Pool] = None
        self.remote_db_connected: bool = False
        self.config = config
        self.user_id = user_id
        self.db_path = db_path
        self.lock = threading.Lock()
        self.db_lock = threading.Lock()

    def init_databases(self):
        full_db_path = Path(self.config.get('local_db_path', self.db_path))
        full_db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.local_db = sqlite3.connect(full_db_path, check_same_thread=False)
            self.local_db.row_factory = sqlite3.Row # 允许通过列名访问
            print(f"SQL database initialized at: {full_db_path}")
        except Exception as err:
            print(f"创建本地数据库失败: {err}")
            raise err
        
        self.__setup_local_database()
        local_users = self.get_all_local_users()
        for user in local_users:
            if self.user_id == user['user_id']:
                self.user_cache = self.json_parser.parse(user['data'].decode('utf-8'))

        if self.config.get('remote_db'):
            try:
                self.remote_db = asyncpg.create_pool(**self.config['remote_db'])
                self.remote_db_connected = True
                print("Connected to remote PostgreSQL database")
                self.sync_local_to_remote(local_users)
            except Exception as err:
                print(f"Remote database connection failed, using local storage: {err}")
                self.remote_db_connected = False
        
        if self.user_cache is None:
            self.create_user_info(self.user_id, int(time.time() * 1000))

    def get_ai_config(self, user_id: str, config_name: str, create: bool = False) -> Optional[Any]:
        user_info = self.get_user_info(user_id)
        if not user_info:
            return None
        ai_configs = user_info.get('ai_config', {})
        if config_name in ai_configs:
            return ai_configs[config_name]
        if create:
            ai_configs[config_name] = {}
            return ai_configs[config_name]
        return None

    def set_ai_instance_model_id(self, user_id: str, instance_name: str, model_id: str):
        ai_instance = self.get_ai_instance(user_id, instance_name)
        if ai_instance:
            ai_instance['model_id'] = model_id

    def get_ai_instance_model_id(self, user_id: str, instance_name: str) -> Optional[str]:
        ai_instance = self.get_ai_instance(user_id, instance_name)
        return ai_instance.get('model_id') if ai_instance and 'model_id' in ai_instance else None

    def set_ai_instance_tool_model_id(self, user_id: str, instance_name: str, model_id: str):
        ai_instance = self.get_ai_instance(user_id, instance_name)
        if ai_instance:
            ai_instance['tool_model_id'] = model_id

    def get_ai_instance_tool_model_id(self, user_id: str, instance_name: str) -> Optional[str]:
        ai_instance = self.get_ai_instance(user_id, instance_name)
        return ai_instance.get('tool_model_id') if ai_instance and 'tool_model_id' in ai_instance else None

    def create_user_info(self, user_id: str, timestamp: int):
        self.lock.acquire_lock()
        try:
            user_dict = self.new_user_dict(timestamp)
            self.user_cache = user_dict
            self.save_user_info(user_id, user_dict)
            print("创建新的用户id:\t", user_id)
        finally:
            self.lock.release()

    def destroy_user_info(self, user_id: str):
        self.lock.acquire_lock()
        try:
            if self.remote_db:
                self.remote_db.execute('DELETE FROM users WHERE user_id = $1', user_id)
            if self.local_db:
                with self.db_lock:
                    cursor = self.local_db.cursor()
                    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
                    self.local_db.commit()
            self.user_cache = None
            print("删除用户id:\t", user_id)
        finally:
            self.lock.release()

    def get_user_info(self, user_id: str) -> Optional[UserInfo]:
        user_info: Optional[UserInfo] = None
        self.lock.acquire_lock()
        try:
            if self.user_cache:
                return self.user_cache
            user_info = self.load_user(user_id)
            if user_info:
                self.user_cache = user_info
        finally:
            self.lock.release()
        return user_info

    def add_ai_instance_session(self, user_id: str, instance_name: str) -> Optional[Session]:
        session = None
        ai_instance = self.get_ai_instance(user_id, instance_name)
        if ai_instance:
            session_id = str(uuid.uuid4())
            session = self.create_ai_instance_session(session_id, int(time.time() * 1000))
            self.set_ai_instance_session(ai_instance, session_id, session)
            self.set_ai_instance_selected_session(user_id, instance_name, session_id)
        self.save_user_info_wrapper(user_id)
        return session

    def remove_ai_instance_session(self, user_id: str, instance_name: str, session_id: str) -> Optional[Session]:
        session = None
        ai_instance = self.get_ai_instance(user_id, instance_name)
        if ai_instance:
            self.destroy_ai_instance_session(ai_instance, session_id)
            session = self.get_ai_instance_session(user_id, instance_name)
            if not session:
                session = self.add_ai_instance_session(user_id, instance_name)
            self.save_user_info_wrapper(user_id)
        return session

    def get_ai_instance_sessions_snapshot(self, user_id: str, instance_name: str, attributes: List[str] = ["id", "selected", "last_modified_timestamp", "name", "is_ai_stream_transfer"]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        ai_instance = self.get_ai_instance(user_id, instance_name)
        if not ai_instance:
            return result
        sessions = ai_instance.get('sessions', {})
        for session_id, session_info in sessions.items():
            info: Dict[str, Any] = {}
            if "id" in attributes:
                info["id"] = session_id
            if "selected" in attributes:
                info["selected"] = (session_id == ai_instance.get('selected_session_id'))
            for key, value in session_info.items():
                if key in attributes:
                    info[key] = value
            result.append(info)
        result.sort(key=lambda x: x.get('last_modified_timestamp', 0), reverse=True)
        return result

    def set_ai_instance_selected_session(self, user_id: str, instance_name: str, session_id: str):
        ai_instance = self.get_ai_instance(user_id, instance_name)
        if ai_instance:
            ai_instance['selected_session_id'] = session_id
            self.save_user_info_wrapper(user_id)

    def set_ai_instance_session_name(self, user_id: str, instance_name: str, session_id: str, name: str) -> Optional[Session]:
        session = self.get_ai_instance_session(user_id, instance_name, session_id)
        if session:
            session['name'] = name
            self.save_user_info_wrapper(user_id)
        return session

    def set_conext_expand(self, user_id: str, instance_name: str, session_id: Optional[str], index: int, expand: Optional[bool] = None) -> Optional[Session]:
        session = self.get_ai_instance_session(user_id, instance_name, session_id)
        if session:
            history = session.get('history', [])
            if 0 <= index < len(history):
                history[index]['context_expand'] = expand
                self.save_user_info_wrapper(user_id)
        return session

    def remove_ai_instance_messages(self, user_id: str, instance_name: str, session_id: Optional[str] = None, remove_index_list: Optional[List[int]] = None) -> Optional[Session]:
        timestamp = int(time.time() * 1000)
        session = self.get_ai_instance_session(user_id, instance_name, session_id)
        if not session:
            return None
        if remove_index_list:
            session['history'] = [msg for idx, msg in enumerate(session['history']) if idx not in remove_index_list]
        else:
            session['history'] = []
        if len(session['history']) <= 0:
            session['history'].append(self.create_ai_instance_message(timestamp))
        session['name'] = self.get_session_name(session['history'])
        session['last_modified_timestamp'] = timestamp
        self.save_user_info_wrapper(user_id)
        return session

    def remove_ai_instance_cache(self, user_id: str, instance_name: str):
        session = self.get_ai_instance_session(user_id, instance_name)
        if not session:
            return
        session['cache'] = self.get_default_cache()
        self.save_user_info_wrapper(user_id)

    def update_user_info(self, user_id: str, instance_name: str, session_id: Optional[str] = None, message: Optional[Message] = None, cache: Optional[Dict[str, Any]] = None, message_replace: bool = False, index: int = -1):
        session = self.get_ai_instance_session(user_id, instance_name, session_id)
        if not session:
            return
        if message:
            messages = session.get('history', [])
            if messages is None:
                messages = []
                session['history'] = messages
            if message_replace and len(messages) > 0:
                if 0 <= index < len(messages):
                    messages[index] = message
            else:
                if index == -1 or index >= len(messages):
                    messages.append(message)
                else:
                    messages[index] = message
            session['last_modified_timestamp'] = int(time.time() * 1000)
            session['name'] = self.get_message_name(message)
        if cache:
            session['cache'].update(cache)
        self.save_user_info_wrapper(user_id)

    def update_user_info_by_session(self, user_id: str, session: Session, message: Optional[Message] = None, cache: Optional[Dict[str, Any]] = None, message_replace: bool = False, index: int = -1):
        if message:
            messages = session.get('history', [])
            if messages is None:
                messages = []
            if message_replace and len(messages) > 0:
                if 0 <= index < len(messages):
                    messages[index] = message
            else:
                if index == -1 or index >= len(messages):
                    messages.append(message)
                else:
                    messages[index] = message
            session['last_modified_timestamp'] = int(time.time() * 1000)
            session['name'] = self.get_message_name(message)
        if cache:
            session['cache'].update(cache)
        self.save_user_info_wrapper(user_id)

    def get_ai_instance_messages(self, user_id: str, instance_name: str, session_id: Optional[str] = None, deep_copy: bool = False) -> Optional[List[Message]]:
        session = self.get_ai_instance_session(user_id, instance_name, session_id)
        if not session:
            return None
        if deep_copy:
            return self.json_parser.parse(self.json_parser.to_json_str(session.get('history', [])))
        else:
            return session.get('history', [])

    def get_ai_instance_cache(self, user_id: str, instance_name: str) -> Cache:
        session = self.get_ai_instance_session(user_id, instance_name)
        if not session:
            return self.get_default_cache()
        return session.get('cache', self.get_default_cache())

    def get_ai_round(self, user_id: str, instance_name: str, session_id: Optional[str] = None) -> int:
        session = self.get_ai_instance_session(user_id, instance_name, session_id)
        if not session:
            return 1
        return session.get('round', 0)

    def add_ai_round(self, user_id: str, instance_name: str, session_id: Optional[str] = None):
        session = self.get_ai_instance_session(user_id, instance_name, session_id)
        if not session:
            return
        session['round'] = session.get('round', 0) + 1
        self.save_user_info_wrapper(user_id)

    def get_ai_instance_session(self, user_id: str, instance_name: str, session_id: Optional[str] = None) -> Optional[Session]:
        ai_instance = self.get_ai_instance(user_id, instance_name)
        if not ai_instance:
            return None
        session_id = session_id or ai_instance.get('selected_session_id')
        if session_id and session_id in ai_instance.get('sessions', {}):
            return ai_instance['sessions'][session_id]
        return None

    def get_user_tabel_db_text(self, blob_type: str = 'BLOB') -> str:
        return f"CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, data {blob_type} NOT NULL)"

    def __setup_local_database(self):
        if not self.local_db:
            return
        try:
            sql = self.get_user_tabel_db_text('BLOB')
            with self.db_lock:
                self.local_db.execute(sql)
                self.local_db.commit()
        except Exception as err:
            print(f"创建本地数据库表失败: {err}")
            raise err

    def sync_local_to_remote(self, local_users: List[Dict[str, Any]]):
        if not self.remote_db_connected or not self.remote_db:
            return
        try:
            self.remote_db.execute(self.get_user_tabel_db_text('BYTEA'))
            for user in local_users:
                self.save_user_info_to_remote(user['user_id'], user['data'])
            print("Local data synchronized to remote database")
        except Exception as err:
            print(f"Failed to sync local data to remote: {err}")

    def get_all_local_users(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not self.local_db:
            return rows
        with self.db_lock:
            cursor = self.local_db.execute("SELECT user_id, data FROM users")
            for row in cursor:
                rows.append({
                    'user_id': row['user_id'],
                    'data': row['data'] # 在 Python sqlite3 中，BLOB 通常直接作为 bytes 返回
                })
        return rows

    def save_user_info_to_remote(self, user_id: str, data: bytes):
        if not self.remote_db:
            return
        try:
            self.remote_db.execute(
                "INSERT INTO users (user_id, data) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET data = $2",
                user_id, data
            )
        except Exception as err:
            print(f"Failed to save user to remote: {err}")

    def load_user(self, user_id: str) -> Optional[UserInfo]:
        if self.remote_db_connected and self.remote_db:
            try:
                res = self.remote_db.fetchrow('SELECT data FROM users WHERE user_id = $1', user_id)
                if res:
                    return self.json_parser.parse(res['data'].decode('utf-8'))
            except Exception as err:
                print(f"Failed to load user from remote: {err}")
        if self.local_db:
            with self.db_lock:
                try:
                    cursor = self.local_db.execute('SELECT data FROM users WHERE user_id = ?', (user_id,))
                    row = cursor.fetchone()
                    if row and row['data']:
                        user_info = self.json_parser.parse(row['data'].decode('utf-8'))
                        return user_info
                except Exception as err:
                    print(f"Failed to load user from local: {err}")
        return None

    def save_user_info_wrapper(self, user_id: str):
        user_info = self.get_user_info(user_id)
        if user_info:
            self.save_user_info(user_id, user_info)

    def save_user_info(self, user_id: str, data: UserInfo):
        serialized = self.json_parser.to_json_str(data)
        data_bytes = serialized.encode('utf-8')
        if self.remote_db_connected and self.remote_db:
            try:
                self.save_user_info_to_remote(user_id, data_bytes)
            except Exception as err:
                print(f"Failed to save user to remote: {err}")
                self.remote_db_connected = False
        if self.local_db:
            with self.db_lock:
                try:
                    blob_data = sqlite3.Binary(data_bytes)
                    self.local_db.execute(
                        "INSERT OR REPLACE INTO users (user_id, data) VALUES (?, ?)",
                        (user_id, blob_data)
                    )
                    self.local_db.commit()
                    self.persist_database()
                except Exception as err:
                    print(f"Failed to save user to local: {err}")

    def persist_database(self):
        # 在 Python sqlite3 中，commit 通常已经写入磁盘，除非使用了内存数据库。
        # 如果是内存数据库需要导出，这里假设是文件数据库，commit 即可。
        # 如果需要强制同步，可以重新连接或使用 check_same_thread=False 的配置。
        pass

    def get_ai_instance(self, user_id: str, instance_name: str) -> Optional[AIInstance]:
        user_info = self.get_user_info(user_id)
        if not user_info:
            return None
        ai_instances = user_info.get('ai_instance', {})
        return ai_instances.get(instance_name)

    def new_user_dict(self, timestamp: int) -> UserInfo:
        session_id = str(uuid.uuid4())
        chat_instance: AIInstance = {
            'sessions': {
                session_id: self.create_ai_instance_session(session_id, timestamp)
            },
            'selected_session_id': session_id
        }
        return {
            'ai_config': {},
            'ai_instance': {'chat': chat_instance}
        }

    def create_ai_instance_session(self, session_id: str, timestamp: int) -> Session:
        message = self.create_ai_instance_message(timestamp)
        display_name = self.get_message_name(message)
        return {
            'session_id': session_id,
            'last_modified_timestamp': timestamp,
            'name': display_name,
            'round': 0,
            'history': [message],
            'cache': self.get_default_cache(),
            'is_ai_stream_transfer': False,
            'force_save': False,
            'refresh': False
        }

    def create_ai_instance_message(self, timestamp: int) -> Message:
        return {
            'role': "system",
            'content': self.get_time_text(timestamp),
            'timestamp': timestamp
        }

    def get_default_cache(self) -> Cache:
        return {
            'tools_usage': "",
            'tools_describe': "",
            'tool_calls': [],
            'context': "",
            'knowledge': "",
            'backup': "",
            'returns': {
                'ai': {
                    'ai_conclusion': ""
                }
            }
        }
    
    def set_ai_instance_session(self, ai_instance: AIInstance, session_id: str, session_data: Session):
        ai_instance['sessions'][session_id] = session_data

    def destroy_ai_instance_session(self, ai_instance: AIInstance, session_id: str):
        ai_instance['sessions'].pop(session_id, None)

    def get_session_name(self, history: List[Message]) -> str:
        if len(history) <= 0:
            return ''
        latest_message = history[0]
        for i in range(1, len(history)):
            current_message = history[i]
            if current_message['timestamp'] >= latest_message['timestamp']:
                latest_message = current_message
        return self.get_message_name(latest_message)

    def get_time_text(self, timestamp: int) -> str:
        """将时间戳转换为格式化的中文时间字符串"""
        # Python 中处理时间戳（注意 JS 时间戳通常是毫秒，Python 通常用秒，这里假设传入的是毫秒）
        # 如果 timestamp 是毫秒级，需要除以 1000
        if timestamp > 10000000000: # 简单判断是否为毫秒级时间戳
            dt = datetime.fromtimestamp(timestamp / 1000)
        else:
            dt = datetime.fromtimestamp(timestamp)
        # 格式化为 '年-月-日 小时:分钟:秒' 格式
        # 注意：Python 的 strftime 无法直接处理 locale 的月份/日期补零，这里手动格式化
        send_time = dt.strftime('%Y-%m-%d %H:%M:%S')
        return f"\n当前时间为：{send_time}\n"

    def get_message_name(self, message: Message) -> str:
        display_name = message['content']
        if len(display_name) > self.MAX_SESSION_NAME_LENGTH:
            display_name = display_name[:self.MAX_SESSION_NAME_LENGTH - 3] + '...'
        display_name = display_name.replace('<think>', '').replace('</think>', '')
        display_name = display_name.replace('<conclusion>', '').replace('</conclusion>', '')
        return display_name