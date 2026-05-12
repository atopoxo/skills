import requests
import html
import logging
from typing import Dict, List, Any
from dataclasses import dataclass
from core.function.base_function import singleton
from core.json.json_parser import get_json_parser
from tools.browser.browser_base import BrowserError, BrowserBase, SearchResultItem

@singleton
class Browser(BrowserBase):
    def __init__(self, config: Dict[str, Any]):
        super().__init__()
        self.json_parser = get_json_parser()
        self.extension_name: str = config.get('extension_name', '')

    def search(self, query: str, domain: str, num_results: int = 10) -> Dict[str, Any]:
        result = {
            "browserResult": {
                "showType": "browser_list",
                "returnType": "ai_tips",
                "value": []
            }
        }
        
        info = self.get_config()
        engine_id = info.get('engine_id')
        base_url = info.get('url')
        api_key = info.get('api_key')
        
        headers = { 
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        }
        
        domain_optimized_query = self.domain_specific_search(query, domain)
        optimized_query = self.optimize_query(domain_optimized_query)
        
        params = {
            "key": api_key,
            "cx": engine_id,
            "lr": "lang_zh-CN",
            "gl": "cn",
            "safe": "off",
            "q": optimized_query,
            "num": num_results,
            "start": 0,
        }
        
        search_results: List[SearchResultItem] = []

        # 分页循环逻辑
        for start_index in range(0, num_results, 10):
            params["num"] = min(num_results - start_index, 10)
            params["start"] = start_index + 1
            try:
                response = requests.get(
                    base_url, 
                    headers=headers, 
                    params=params, 
                    timeout=10
                )
                if response.status_code != 200:
                    raise Exception(f"HTTP错误: {response.status_code}")
                self.format_results(search_results, response.json(), query)
            except Exception as error:
                error_msg = str(error)
                logging.warning(f"搜索请求失败: {error_msg}")
                raise BrowserError("搜索请求失败")

        # 语义重排序
        reordered_results = self.semantic_reranking(search_results, query)
        
        # 过滤逻辑
        filtered_results = [
            item for item in reordered_results 
            if item.score >= 0.4 and 
            "pdf" not in item.link and 
            "404" not in item.title and 
            len(item.snippet) > 30
        ]
        
        # 截取前 num_results 个
        result["browserResult"]["value"] = filtered_results[:num_results]
        return result

    def get_config(self) -> Dict[str, Any]:
        id_val = "google search engine"
        infos = [{
                    "id": "google search engine",
                    "name": "google搜索引擎",
                    "engine_id": "26b0febeef29f46a8",
                    "url": "https://customsearch.googleapis.com/customsearch/v1",
                    "example_key": "AIzaSyCjIhwUAZHWR5xPtRz*Kgk1*iU7af7dDBM",
                    "show_config": False
                }]
        
        info = next((info for info in infos if info.get('id') == id_val), {"name": ""})
        return info

    def format_results(self, results: List[SearchResultItem], raw_data: Dict[str, Any], query: str) -> None:
        if "items" not in raw_data or not isinstance(raw_data["items"], list):
            return
        for item in raw_data["items"]:
            try:
                raw_snippet = item.get("snippet", "")
                decoded_snippet = self.decode_snippet(raw_snippet, "无摘要")
                final_snippet = self.generate_contextual_snippet(decoded_snippet, query)
                title = self.decode_snippet(item.get("title", ""), "无标题")
                link = item.get("link", "")
                authority_data = self.calculate_authority(link)

                results.append(SearchResultItem(
                    title=title,
                    snippet=final_snippet,
                    link=link,
                    authority=authority_data["name"],
                    score=0.0, # 临时分数
                    authority_score=authority_data["score"]
                ))
            except Exception as error:
                error_msg = str(error)
                item_str = str(item) # 替代 jsonParser.toJsonStr
                logging.error(f"结果格式化失败 | 条目: {item_str} | 错误: {error_msg}")

    def decode_snippet(self, text: str, default_value: str) -> str:
        if not text:
            return default_value
        try:
            # Python 的 html.unescape 对应 he.decode
            return html.unescape(text)
        except Exception as error:
            logging.error(f"Snippet解码失败 | 原始文本: {text[:50]}... | 错误: {error}")
            return default_value

    def generate_contextual_snippet(self, snippet: str, query: str) -> str:
        # 简单的句子分割，兼容中英文标点
        import re
        sentences = re.split(r'[.!?。！？]\s+', snippet)
        
        # 假设 self.segmenter 已存在，这里做简单的 fallback
        if hasattr(self, 'segmenter') and self.segmenter:
            keywords = self.segmenter.segment(query.lower())
        else:
            keywords = query.lower().split()
            
        best_sentence = ''
        max_count = 0
        for sentence in sentences:
            lower_sentence = sentence.lower()
            count = sum(1 for keyword in keywords if keyword in lower_sentence)
            if count > max_count:
                max_count = count
                best_sentence = sentence
                
        if len(best_sentence) > 0:
            return best_sentence
        else:
            return snippet[:150] + ('...' if len(snippet) > 150 else '')