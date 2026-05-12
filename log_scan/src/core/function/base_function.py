import time
import re
import datetime
import os
import chardet
import codecs
from typing import Optional, Union, Dict, TypedDict
from enum import Enum
from copy import deepcopy

BufferType = Union[bytes, bytearray, memoryview]

class FileSelection(TypedDict):
    start: Dict
    end: Dict

class SingletonEnumMeta(type(Enum)):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(SingletonEnumMeta, cls).__call__(*args, **kwargs)
        return cls._instances[cls]

class SingletonEnum(Enum, metaclass=SingletonEnumMeta):
    pass
    
def singleton(cls):
    instances = {}
    def wrapper(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    wrapper.__wrapped__ = cls
    wrapper.__name__ = cls.__name__
    return wrapper

def time_int():
    return int(time.time())

def update_data(dest, src):
    dest.update(src)

def is_number(s):
    if s is None:
        return False
    return re.match(r'^-?\d+(?:\.\d+)?$', s) is not None

def int_or_none(value):
    try:
        return int(value)  # type: ignore
    except (TypeError, ValueError):
        return None
    
def get_local_dir_size(dir, ignore_symlinks=True):
    size = 0
    if os.path.exists(dir):
        for dirpath, _, filenames in os.walk(dir):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if ignore_symlinks and os.path.islink(filepath):
                    continue
                try:
                    size += os.path.getsize(filepath)
                except Exception as ex:
                    continue
    return size

def get_class_instance(class_name: str, module=None, config=None):
    try:
        if class_name != "":
            if module:
                cls_wrapper = getattr(module, class_name, None)  # 可能得到的是装饰器wrapper
            else:
                cls_wrapper = globals().get(class_name)
            if not cls_wrapper:
                raise ValueError(f"Class '{class_name}' not found")
            original_cls = getattr(cls_wrapper, '__wrapped__', None)  # 获取原始类
            cls = original_cls if original_cls else cls_wrapper
            instance = cls_wrapper(config) if config else cls_wrapper()
            return cls, instance
        else:
            return None, None
    except Exception as ex:
        raise RuntimeError(f"Class resolution failed: {str(ex)}")
    
def get_class_method(class_name: str, method_name: str, module=None, config=None):
    try:
        if class_name != "":
            return method_name
        else:
            if module:
                method = getattr(module, method_name, None)
            else:
                method = globals().get(method_name)
            if not method:
                raise ValueError(f"Method '{method_name}' not found in global")
            return method
    except Exception as ex:
        raise RuntimeError(f"Method resolution failed: {str(ex)}")
    
def get_current_time_str():
    now = datetime.datetime.now()
    formatted_date = now.strftime("%Y年%m月%d日 %H:%M")
    return formatted_date

def get_encoding(buffer: BufferType) -> str:
    detection = chardet.detect(buffer)
    encoding = detection.get('encoding', 'gbk')
    if not encoding:
        encoding = 'gbk'
    if encoding.upper() not in ['GB2312', 'GBK', 'UTF-8', 'ISO8859-2']:
        encoding = 'GBK'
    return encoding

def get_file_content(
    file_path: Optional[str] = None, 
    buffer: Optional[BufferType] = None, 
    encoding: Optional[str] = None, 
    start_pos: Optional[int] = None, 
    end_pos: Optional[int] = None
) -> str:
    if buffer is None and file_path is not None:
        with open(file_path, 'rb') as f:
            buffer = f.read()
    if buffer is None:
        raise ValueError("必须提供 file_path 或 buffer")
    if encoding is None:
        encoding = get_encoding(buffer)
    try:
        content = codecs.decode(buffer, encoding, errors='replace')
    except (LookupError, UnicodeDecodeError):
        try:
            content = codecs.decode(buffer, 'utf-8', errors='replace')
        except:
            content = codecs.decode(buffer, 'gbk', errors='replace')
    if start_pos is not None or end_pos is not None:
        start = start_pos if start_pos is not None else 0
        end = end_pos if end_pos is not None else len(content)
        content = content[start:end]

    return content

# 模拟lodash的merge函数
def merge(*objects):
    """简单实现类似lodash merge的功能"""
    if not objects:
        return {}
    
    result = {}
    for obj in objects:
        if obj:
            result.update(obj)
    return result

def read_file_context(file_path: str, target_line: int, context_lines: int = 0, encoding: str = None, content_type: str = 'text') -> Optional[Dict]:
    result = {}
    if file_path is not None:
        with open(file_path, 'rb') as f:
            buffer = f.read()
    if encoding is None:
        encoding = get_encoding(buffer)
    try:
        if buffer is not None:
            if content_type == 'byte':
                content = buffer.decode(encoding, errors='ignore')
                content = content.replace('\r\n', '\n').replace('\r', '\n')
                content_bytes = bytes(content, encoding)
                lines = content.split('\n')
                current_line = target_line - 1
                
                start_line = max(0, current_line - context_lines)
                start_char = 0
                prefix_text = '\n'.join(lines[:start_line])
                if start_line > 0:
                    prefix_text += '\n'
                start_pos = len(prefix_text.encode(encoding))
                start_pos += start_char

                end_line = min(len(lines) - 1, current_line + context_lines)
                target_text = '\n'.join(lines[:end_line])
                end_char = len(lines[end_line].encode(encoding)) + 1
                if end_line > 0:
                    target_text += '\n'
                end_pos = len(target_text.encode(encoding))
                end_pos += end_char

                result = {
                    'encoding': encoding,
                    'select_content': content_bytes[start_pos:end_pos],
                    'file_content': content_bytes,
                    "selection": {
                        "start": {
                            "pos": start_pos,
                            "line": start_line,
                            "character": start_char
                        },
                        "end": {
                            "pos": end_pos,
                            "line": end_line,
                            "character": end_char
                        }
                    }
                }
            else:
                content = buffer.decode(encoding, errors='ignore')
                content = content.replace('\r\n', '\n').replace('\r', '\n')
                lines = content.split('\n')

                current_line = target_line - 1
                start_line = max(0, current_line - context_lines)
                end_line = min(len(lines), current_line + context_lines)

                start_char = 0
                end_char = len(lines[end_line]) + 1
                start_pos = 0
                for i in range(start_line):
                    start_pos += len(lines[i]) + 1
                start_pos += start_char
                end_pos = 0
                for i in range(end_line):
                    end_pos += len(lines[i]) + 1
                end_pos += end_char
                result = {
                    'encoding': encoding,
                    'select_content': content[start_pos:end_pos],
                    'file_content': content,
                    "selection": {
                        "start": {
                            "pos": start_pos,
                            "line": start_line,
                            "character": start_char
                        },
                        "end": {
                            "pos": end_pos,
                            "line": end_line,
                            "character": end_char
                        }
                    }
                }
            return result
    except:
        return None
    
def merge_dicts(base: Optional[Dict], override: Optional[Dict]) -> Dict:
    """模拟 lodash merge 的简单深合并函数"""
    result = deepcopy(base) if base else {}
    if override:
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = merge_dicts(result[key], value)
            else:
                result[key] = deepcopy(value)
    return result

def is_numeric(value):
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False