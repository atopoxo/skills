# -*- coding: utf-8 -*-
import json
from jsoncomment import JsonComment
import datetime
from typing import Any, Dict, Union
from core.function.base_function import *
from core.logs.log_manager import log_mgr
from core.json.json_utils import *
from collections import OrderedDict
import xml.etree.cElementTree as ET

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        return super(DateTimeEncoder, self).default(obj)
    
@singleton
class JsonParser():
    def __init__(self, config = None):
        self._init_variable()

    def _init_variable(self):
        self.JSON_SCHEMA = """
        {
            "command": {
                "name": "command name",
                "args": {
                    "arg name": "value"
                }
            },
            "thoughts":
            {
                "text": "thought",
                "reasoning": "reasoning",
                "plan": "- short bulleted\n- list that conveys\n- long-term plan",
                "criticism": "constructive self-criticism",
                "speak": "thoughts summary to say to user"
            }
        }
        """

    def read_json_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                parser = JsonComment()
                data = parser.loads(content)
                # # 移除块注释
                # content_cleaned = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
                # # 移除行注释并处理尾逗号
                # content_cleaned = re.sub(r'//.*', '', content_cleaned)
                # # 修复对象/数组中的尾逗号
                # data = re.sub(r',(\s*[}\]])', r'\1', content_cleaned)
                return data
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            print(f"解析JSON文件时发生错误: {file_path}")
            return None
        except Exception as e:
            print(f"读取文件时发生未知错误: {e}")
            return None
    
    def parse(self, json_str: str, func = None, data = None, try_to_fix: bool = True) -> Union[str, Dict[Any, Any]]:
        try:
            json_str = json_str.replace("\t", "")
            return json.loads(json_str)
        except json.JSONDecodeError as _:  # noqa: F841
            try:
                json_str = correct_json(json_str)
                return json.loads(json_str)
            except json.JSONDecodeError as _:  # noqa: F841
                pass
        # Let's do something manually:
        # sometimes GPT responds with something BEFORE the braces:
        # "I'm sorry, I don't understand. Please try again."
        # {"text": "I'm sorry, I don't understand. Please try again.",
        #  "confidence": 0.0}
        # So let's try to find the first brace and then parse the rest
        #  of the string
        try:
            brace_index = json_str.index("{")
            json_str = json_str[brace_index:]
            last_brace_index = json_str.rindex("}")
            json_str = json_str[: last_brace_index + 1]
            return json.loads(json_str)
        # Can throw a ValueError if there is no "{" or "}" in the json_str
        except (json.JSONDecodeError, ValueError) as e:  # noqa: F841
            if try_to_fix:
                log_mgr.warn(
                    "Warning: Failed to parse AI output, attempting to fix."
                    "\n If you see this warning frequently, it's likely that"
                    " your prompt is confusing the AI. Try changing it up"
                    " slightly."
                )
                # Now try to fix this up using the ai_functions
                ai_fixed_json = self.fix_json(json_str, func, data, self.JSON_SCHEMA)

                if ai_fixed_json != "failed":
                    return json.loads(ai_fixed_json)
                else:
                    # This allows the AI to react to the error message,
                    #   which usually results in it correcting its ways.
                    log_mgr.error("Failed to fix AI output, telling the AI.")
                    return json_str
            else:
                raise e

    def fix_json(self, json_str: str, func, data, schema: str) -> str:
        """Fix the given JSON string to make it parseable and fully compliant with the provided schema."""
        # Try to fix the JSON using GPT:
        function_string = "def fix_json(json_str: str, func, data, schema:str=None) -> str:"
        args = [f"'''{json_str}'''", f"'''{schema}'''"]
        description_string = (
            "Fixes the provided JSON string to make it parseable"
            " and fully compliant with the provided schema.\n If an object or"
            " field specified in the schema isn't contained within the correct"
            " JSON, it is omitted.\n This function is brilliant at guessing"
            " when the format is incorrect."
        )

        # If it doesn't already start with a "`", add one:
        if not json_str.startswith("`"):
            json_str = "```json\n" + json_str + "\n```"
        if func:
            result_string = func(function_string, args, description_string, data)
            log_mgr.debug("------------ JSON FIX ATTEMPT ---------------")
            log_mgr.debug(f"Original JSON: {json_str}")
            log_mgr.debug("-----------")
            log_mgr.debug(f"Fixed JSON: {result_string}")
            log_mgr.debug("----------- END OF FIX ATTEMPT ----------------")

            try:
                json.loads(result_string)  # just check the validity
                return result_string
            except:  # noqa: E722
                # Get the call stack:
                # import traceback
                # call_stack = traceback.format_exc()
                # print(f"Failed to fix JSON: '{json_str}' "+call_stack)
                return "failed"
            
    def to_xml(self, json_data, str_on = True, factory=ET.Element):
        """Convert a JSON string into an XML string.
        Whatever Element implementation we could import will be used by
        default; if you want to use something else, pass the Element class
        as the factory parameter.
        """
        result = None
        if not isinstance(json_data, dict):
            json_data = json.loads(json_data)

        elem = self._internal_to_elem(json_data, factory)
        if str_on:
            result = ET.tostring(elem)
        else:
            result = elem
        return result
    
    def to_json_str(self, data, ensure_ascii=False, cls=DateTimeEncoder, indent=0):
        return json.dumps(data, ensure_ascii=ensure_ascii, cls=cls, indent=indent)
    
    def write_to_file(self, data, file_path, ensure_ascii=False, cls=DateTimeEncoder, indent=0, encoding='utf-8'):
        json_str = self.to_json_str(data, ensure_ascii=ensure_ascii, cls=cls, indent=indent)
        with open(file_path, 'w', encoding=encoding) as f:
            f.write(json_str)

    def read_from_file(self, file_path, encoding='utf-8'):
        with open(file_path, 'r', encoding=encoding) as f:
            json_str = f.read()
            return json.loads(json_str)
    
    def _internal_to_elem(self, pfsh, factory=ET.Element):
        """Convert an internal dictionary (not JSON!) into an Element.
        Whatever Element implementation we could import will be
        used by default; if you want to use something else, pass the
        Element class as the factory parameter.
        """
        attribs = OrderedDict()
        text = None
        tail = None
        sublist = []
        tag = list(pfsh.keys())
        if len(tag) != 1:
            raise ValueError("Illegal structure with multiple tags: %s" % tag)
        tag = tag[0]
        value = pfsh[tag]
        if isinstance(value, dict):
            for k, v in list(value.items()):
                if k[:1] == "@":
                    attribs[k[1:]] = v
                elif k == "#text":
                    text = v
                elif k == "#tail":
                    tail = v
                elif isinstance(v, list):
                    for v2 in v:
                        sublist.append(self._internal_to_elem({k: v2}, factory=factory))
                else:
                    sublist.append(self._internal_to_elem({k: v}, factory=factory))
        else:
            text = value
        e = factory(tag, attribs)
        for sub in sublist:
            e.append(sub)
        e.text = text
        e.tail = tail
        return e
            
def get_json_parser(config = None):
    return JsonParser(config)

json_parser = get_json_parser()