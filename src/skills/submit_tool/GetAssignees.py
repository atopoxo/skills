import json
import requests
import hashlib
import time
import sys
import logging
import datetime

import skills.submit_tool.ProcessEXUser as ProcessEXUser
def process_workitem_data(rsp):
    # 1. 定位核心数据层（必选，所有用户信息都在data下）
    if not isinstance(rsp.get('data'), dict):
        # print("数据异常：无有效data字段")
        return rsp
    
    data = rsp['data']
    # 定义需要处理的用户相关字段（单字典/字典列表），后续新增字段直接加在这里即可
    user_fields = ['creator', 'assignees', 'openPermissionsInfo']
    
    # 2. 先收集所有需要修正的w_开头userId，批量调用函数（减少函数调用次数，优化性能）
    need_fix_user_ids = set()  # 用集合避免重复userId
    for field in user_fields:
        field_value = data.get(field)
        if not field_value:
            continue  # 字段为空，跳过
        
        # 处理【单个用户字典】（如creator）
        if isinstance(field_value, dict) and 'userId' in field_value:
            user_id = field_value['userId']
            if user_id.startswith('w_'):
                need_fix_user_ids.add(user_id)
        
        # 处理【用户字典列表】（如assignees、openPermissionsInfo）
        elif isinstance(field_value, list):
            for user_dict in field_value:
                if isinstance(user_dict, dict) and 'userId' in user_dict:
                    user_id = user_dict['userId']
                    if user_id.startswith('w_'):
                        need_fix_user_ids.add(user_id)
    
    # 3. 批量调用函数获取正确邮箱（无需要修正的userId则跳过）
    correct_email_map = {}
    target_status = ["active"]  # 按你的实际业务需求传值，可自定义
    if need_fix_user_ids:
        result = ProcessEXUser.call_wps_get_ex_user(list(need_fix_user_ids), target_status)
        user_list = result.get("data", {}).get("items", [])
        for user in user_list:
            user_id = user.get('ex_user_id')
            if user_id:
                correct_email_map[user_id] = user.get('email')
                #print(f"已修正邮箱的用户：{user_id} -> {user.get('email')}")
    
    # 4. 遍历更新所有用户字典的邮箱字段
    for field in user_fields:
        field_value = data.get(field)
        if not field_value:
            continue
        
        # 处理单个用户字典
        if isinstance(field_value, dict) and 'userId' in field_value:
            user_id = field_value['userId']
            if user_id in correct_email_map:
                field_value['email'] = correct_email_map[user_id]
                field_value['userId'] = correct_email_map[user_id].split('@')[0]
        
        # 处理用户字典列表
        elif isinstance(field_value, list):
            for user_dict in field_value:
                if isinstance(user_dict, dict) and 'userId' in user_dict:
                    user_id = user_dict['userId']
                    if user_id in correct_email_map:
                        user_dict['email'] = correct_email_map[user_id]
                        user_dict['userId'] = correct_email_map[user_id].split('@')[0]
    
    return rsp

if __name__ == "__main__":
	url = "https://gep.seasungame.com/api/devsimple-open/workitem/workItemInfo/"
	url += "742143"
	r = requests.request("GET", url)
	rsp = json.loads(r.text)
	processed_rsp = process_workitem_data(rsp)
	print(json.dumps(processed_rsp, indent=2, ensure_ascii=False))
