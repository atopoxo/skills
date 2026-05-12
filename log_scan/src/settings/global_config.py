import os
from typing import Any, Dict
from core.json.json_parser import get_json_parser

class GlobalConfig:
    def __init__(self):
        self.json_parser = get_json_parser()

    def get_config(self) -> Any:
        try:
            config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'assets', 'config', 'global_config.json')
            with open(config_path, 'r', encoding='utf-8') as f:
                raw_config = f.read()
            if raw_config:
                obj = self.json_parser.parse(raw_config)
                result = self.__transform_valid_api_key(obj)
                return result
            else:
                return {}
        except Exception as error:
            print(f'加载全局配置失败: {error}')
            return []

    def __transform_valid_api_key(self, obj: Any) -> Any:
        if isinstance(obj, list):
            return [self.__transform_valid_api_key(item) for item in obj]
        elif obj is not None and isinstance(obj, dict):
            result: Dict[str, Any] = {}
            result = {}
            for key, value in obj.items():
                if key == 'example_key':
                    if isinstance(value, str):
                        replaced_value = value.replace('*', '-')
                    else:
                        replaced_value = value
                    result['api_key'] = replaced_value
                else:
                    result[key] = self.__transform_valid_api_key(value)
            return result
        else:
            return obj