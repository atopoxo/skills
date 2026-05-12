import os
from typing import Dict, Any, Optional, List
from core.function.base_function import singleton
from core.json.json_parser import get_json_parser
from core.ai_model.base.ai_types import ModelInfo
from core.storage.storage import Storage
from core.ai_model.base.ai_model_base import AIModelBase
from core.context.context_mgr import ContextMgr

@singleton
class AIModelMgr:
    def __init__(self, config: Any, extension_name: str, storage: Storage, context_mgr: ContextMgr):
        self.json_parser = get_json_parser()
        self.models: Dict[str, AIModelBase] = {}
        self.model_configs: Dict[str, Any] = {}
        self.default_tool_model_id: Optional[str] = None
        self.config = config
        self.extension_name = extension_name
        self.storage = storage
        self.context_mgr = context_mgr
        
        model_config = self.get_config_from_file()
        self.default_tool_model_id = model_config.get('default_tool_model')
        self.set_model_configs(model_config.get("models", []))
    
    def set_selected_models(self, default_model_id: str, default_tool_model_id: str, user_id: str, instance_name: str):
        self.set_selected_model(default_model_id, user_id, instance_name)
        self.set_selected_tool_model(default_tool_model_id, user_id, instance_name)
    
    def set_selected_model(self, id: str, user_id: str, instance_name: str):
        selected_model = self.model_configs.get(id)
        if selected_model:
            self.storage.set_ai_instance_model_id(user_id, instance_name, id)

    def getSelectedModel(self):
        values = list(self.model_configs.values())
        if not values: 
            return None
        selected_model = values[0]
        return selected_model
    
    def set_selected_tool_model(self, id: str, user_id: str, instance_name: str):
        selected_model = self.model_configs.get(id)
        if selected_model:
            self.storage.set_ai_instance_tool_model_id(user_id, instance_name, id)
    
    def getSelectedToolModel(self):
        return self.model_configs.get(self.default_tool_model_id)
    
    def get_model_infos(self) -> List[ModelInfo]:
        return list(self.model_configs.values())
    
    def get_config_from_file(self) -> Any:
        try:
            config_path = os.path.join(os.path.dirname(__file__), '../../../../', 'assets/config/model_config.json')
            config_path = os.path.abspath(config_path)
            with open(config_path, 'r', encoding='utf-8') as f:
                raw_config = f.read()
            if raw_config:
                obj = self.json_parser.parse(raw_config)
                result = self.transform_valid_api_key(obj)
                return result
            else:
                return {}
        except Exception as error:
            print(f'加载模型配置失败: {error}')
            return {}
    
    def update_model(self, model_info: ModelInfo):
        self.model_configs[model_info.id] = model_info
    
    def remove_model(self, id: str):
        if id not in self.model_configs:
            return
        del self.model_configs[id]
    
    def save_model_config(self, key: str, value: Any):
        try:
            config_data = self.get_config_from_file()
            config_data[key] = value
            fixed_config_data = self.transform_invalid_api_key(config_data)
            
            config_path = os.path.join(os.path.dirname(__file__), '../../../', '../../assets/config/model_config.json')
            config_path = os.path.abspath(config_path)
            
            json_string = self.json_parser.to_json_str(fixed_config_data, 4)
            
            with open(config_path, 'w', encoding='utf8') as f:
                f.write(json_string)
            
            model_config = self.get_config_from_file()
            self.set_model_configs(model_config.get("models", []))
            print('模型配置已成功更新')
        except Exception as error:
            print(f'更新模型配置失败: {error}')
            return
    
    def get_model_config(self, id: str) -> Any:
        return self.model_configs.get(id)
    
    def set_model_configs(self, configs: List[Any]):
        for config in configs:
            self.set_model_config(config['id'], config)
    
    def set_model_config(self, id: str, config: Any):
        self.model_configs[id] = config
    
    def chat_stream(self, signal: Any, model_id: str, input_data: Any) -> Any:
        model_config = self.get_model_config(model_id)
        model = self.get_model(model_config)
        return model.chat_stream(signal, input_data)
    
    def get_model(self, model_config: Any) -> AIModelBase:
        id = model_config['id']
        if id not in self.models:
            self.create_model(model_config, id)
        
        model = self.models.get(id)
        if not model:
            raise Exception(f"Model {id} not found")
        return model
    
    def create_model(self, model_config: Any, id: str):
        platform = model_config['platform']
        code_name = model_config['code_name']
        try:
            from importlib import import_module
            model_file = import_module('core.ai_model.{platform}.models.{code_name}.modeling'.format(platform=platform, code_name=code_name))
            instance = model_file.get_class(model_config, {'storage': self.storage, 'context_mgr': self.context_mgr})
            self.models[id] = instance
        except ImportError:
            raise ImportError(f"Could not import module platform={platform},model_name={code_name}")
    
    def transform_valid_api_key(self, obj: Any) -> Any:
        if isinstance(obj, list):
            return [self.transform_valid_api_key(item) for item in obj]
        elif obj is not None and isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                if key == 'example_key':
                    result['api_key'] = "tc-" + str(value)
                else:
                    result[key] = self.transform_valid_api_key(value)
            return result
        else:
            return obj
    
    def transform_invalid_api_key(self, obj: Any) -> Any:
        if isinstance(obj, list):
            return [self.transform_invalid_api_key(item) for item in obj]
        elif obj is not None and isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                if key == 'api_key':
                    originalValue = value
                    if isinstance(originalValue, str) and originalValue.startswith('tc-'):
                        cleanedValue = originalValue[3:]  # 移除 'tc-' 前缀
                    else:
                        cleanedValue = originalValue
                    result['example_key'] = cleanedValue
                else:
                    result[key] = self.transform_invalid_api_key(value)
            return result
        else:
            return obj