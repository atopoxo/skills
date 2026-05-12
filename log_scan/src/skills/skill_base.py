from typing import Dict
from core.json.json_parser import get_json_parser

class SkillBase:
    def __init__(self, config_path):
        self.json_parser = get_json_parser()
        self.config = self._load_config(config_path)
    
    def _load_config(self, path: str) -> Dict:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw_config = f.read()
            if raw_config:
                return self.json_parser.parse(raw_config)
            else:
                return {}
        except Exception as error:
            print(f'自定义配置失败: {error}')
            return {}