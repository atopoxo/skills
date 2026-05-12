import requests
import time
import hashlib
import hmac
import json
from typing import List, Dict, Optional
import logging

# 配置日志
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# -------------------------- 替换为你的应用配置 --------------------------
CLIENT_ID = "AK20240417WXSMKO"          # 开放平台应用详情页获取
CLIENT_SECRET = "9c9444bdf30c4f41b316b49f42101c49"  # 开放平台应用详情页获取（请勿泄露）
# -----------------------------------------------------------------------

# -------------------------- 应用级 Token 自动获取逻辑 --------------------------
TOKEN_URL = "https://openapi.wps.cn/oauth2/token"  # 固定接口地址
current_tenant_token = {
    "access_token": "",
    "expire_time": 0  # 记录token过期时间（时间戳）
}

def get_tenant_access_token() -> Optional[str]:
    """
    自动获取/刷新应用级 Tenant Access Token（grant_type=client_credentials）
    :return: 有效的 access_token（失败返回 None）
    """
    global current_tenant_token
    current_time = time.time()

    # 1. 检查当前 token 是否有效（未过期），有效则直接返回
    if current_tenant_token["access_token"] and current_time < current_tenant_token["expire_time"]:
        return current_tenant_token["access_token"]

    # 2. Token 过期或未获取，重新请求
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"  # 文档要求的固定格式
    }
    data = {
        "grant_type": "client_credentials",  # 固定值，应用级授权类型
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }

    try:
        response = requests.post(
            url=TOKEN_URL,
            headers=headers,
            data=data,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()

        if not result.get("access_token"):
            logger.error(f"获取 Token 失败，响应无 access_token：{result}")
            return None

        expire_time = current_time + result["expires_in"] - 60
        current_tenant_token = {
            "access_token": result["access_token"],
            "expire_time": expire_time
        }
        return result["access_token"]

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP请求失败，状态码：{response.status_code}，错误信息：{e}，响应内容：{response.text}")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"网络连接失败：{e}")
    except requests.exceptions.Timeout as e:
        logger.error(f"请求超时：{e}")
    except Exception as e:
        logger.error(f"获取 Token 未知异常：{str(e)}", exc_info=True)

    return None

API_URL = "https://openapi.wps.cn/v7/users/by_ex_user_ids"
HTTP_METHOD = "POST"
CONTENT_TYPE = "application/json"

def generate_kso1_signature(
    app_secret: str,
    http_method: str,
    content_type: str,
    kso_date: str,
    request_body: str
) -> str:
    """生成 KSO-1 签名（与之前逻辑一致，无需修改）"""
    body_md5 = hashlib.md5(request_body.encode("utf-8")).hexdigest().lower()
    sign_string = f"{http_method}\n{content_type}\n{kso_date}\n{body_md5}\n"
    signature = hmac.new(
        app_secret.encode("utf-8"),
        sign_string.encode("utf-8"),
        digestmod=hashlib.sha256
    ).digest()
    signature_b64 = signature.hex()
    signed_headers = "content-type;x-kso-date"
    return f"KSO1-HMAC-SHA256 Credential={CLIENT_ID}, SignedHeaders={signed_headers}, Signature={signature_b64}"

def get_rfc1123_date() -> str:
    """生成 RFC1123 格式时间戳（与之前一致）"""
    return time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime())

def call_wps_get_ex_user(
    ex_user_ids: List[str],
    status_list: List[str] = None
) -> Optional[Dict]:
    """调用查询用户接口（核心修改：使用应用级 Token）"""
    access_token = get_tenant_access_token()
    if not access_token:
        logger.error("获取有效 Tenant Access Token 失败，终止查询")
        return None

    # 2. 构造请求体（与之前一致）
    if status_list is None:
        status_list = ["active"]
    request_body = {
        "ex_user_ids": ex_user_ids,
        "status": status_list
    }
    request_body_str = json.dumps(request_body, separators=(",", ":"))

    kso_date = get_rfc1123_date()
    kso_authorization = generate_kso1_signature(
        app_secret=CLIENT_SECRET,
        http_method=HTTP_METHOD,
        content_type=CONTENT_TYPE,
        kso_date=kso_date,
        request_body=request_body_str
    )

    headers = {
        "Content-Type": CONTENT_TYPE,
        "X-Kso-Date": kso_date,
        "X-Kso-Authorization": kso_authorization,
        "Authorization": f"Bearer {access_token}"
    }

    try:
        response = requests.post(
            url=API_URL,
            headers=headers,
            data=request_body_str,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        return result
    except requests.exceptions.HTTPError as e:
        logger.error(f"查询失败，状态码：{response.status_code}，错误信息：{e}，响应内容：{response.text}")
    except Exception as e:
        logger.error(f"查询未知异常：{str(e)}", exc_info=True)
    return None

def parse_response(result: Dict) -> List[Dict]:
    if not result or result.get("code") != 0:
        logger.error(f"响应异常，code：{result.get('code')}，msg：{result.get('msg')}")
        return []
    user_list = result.get("data", {}).get("items", [])
    return user_list

if __name__ == "__main__":
    target_ex_user_ids = ["w_chensheng"]
    target_status = ["active"]

    response_result = call_wps_get_ex_user(target_ex_user_ids, target_status)
    if response_result:
        user_list = parse_response(response_result)
        for idx, user in enumerate(user_list, 1):
            print(f"邮箱：{user.get('email', '无（未申请权限）')}")