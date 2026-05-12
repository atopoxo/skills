import random
import math
from typing import List, Dict, Any, Set
from urllib.parse import urlparse
from core.function.text_segmenter import TextSegmenter

# 模拟 SearchResultItem 接口
SearchResultItem = Dict[str, Any]

class BrowserError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.name = 'BrowserError'

class BrowserBase:
    def __init__(self):
        self.segmenter: TextSegmenter = TextSegmenter()
        self.domain_authorities: Dict[str, List[str]] = {
            'programming': [
                'github.com', 'stackoverflow.com', 'developer.mozilla.org', 
                'docs.microsoft.com', 'python.org', 'nodejs.org', 
                'reactjs.org', 'vuejs.org', 'angular.io', 'docker.com', 'kubernetes.io'
            ],
            'finance': [
                'bloomberg.com', 'reuters.com', 'investopedia.com', 'sec.gov', 
                'finra.org', 'nasdaq.com', 'nyse.com', 'federalreserve.gov', 
                'imf.org', 'worldbank.org'
            ],
            'medical': [
                'who.int', 'cdc.gov', 'nih.gov', 'webmd.com', 
                'mayoclinic.org', 'healthline.com', 'medscape.com', 'nejm.org'
            ]
        }

    def domain_specific_search(self, query: str, domain: str) -> str:
        final_domain = self.detect_search_domain(domain)
        if not final_domain:
            return query
        sites = self.domain_authorities.get(final_domain, [])
        if len(sites) == 0:
            return query
        selectedSites = []
        shuffled = sites.copy()
        random.shuffle(shuffled)
        for i in range(min(3, len(shuffled))):
            selectedSites.append(f"site:{shuffled[i]}")
        return f"({query}) ({' OR '.join(selectedSites)})"

    def detect_search_domain(self, domain: str) -> str:
        result = None
        if domain in ['programming', 'finance', 'medical']:
            result = domain
        else:
            result = None
        return result

    async def optimize_query(self, query: str, year: int = 1) -> str:
        boosted_query = query
        return f"{boosted_query}"

    def calculate_authority(self, link: str) -> Dict[str, Any]:
        result = {'name': '', 'score': 0}
        try:
            url = urlparse(link)
            domain = url.hostname if url.hostname else ""
            result['name'] = domain
            found = False
            for domains in self.domain_authorities.values():
                for authDomain in domains:
                    if authDomain in domain:
                        result['score'] = 1.0
                        found = True
                        break
                if found:
                    break
            if found:
                return result
            gov_patterns = ['.gov', '.gov.cn', '.gov.com', '.gov.hk', '.gov.mo', '.gov.tw']
            edu_patterns = ['.edu', '.edu.cn', '.edu.com', '.edu.hk', '.edu.mo', '.edu.tw']
            is_gov_domain = any(domain.endswith(suffix) for suffix in gov_patterns)
            is_edu_domain = any(domain.endswith(suffix) for suffix in edu_patterns)
            if is_gov_domain or is_edu_domain:
                result['score'] = 0.8
                return result
            if 'wikipedia.org' in domain:
                result['score'] = 0.9
                return result
            result['score'] = 0.5
            return result
        except Exception as ex:
            result['score'] = 0.5
            return result

    async def semantic_reranking(self, results: List[SearchResultItem], query: str) -> List[SearchResultItem]:
        try:
            query_keywords = self.segmenter.segment(query.lower())
            scored_results = []
            for item in results:
                content = f"{item['title']} {item['snippet']}"
                text_score = self.calculate_text_similarity(query, query_keywords, content)
                traditional_score = self.calculate_relevance(
                    query, item['title'], item['snippet'], item['link'], item.get('authority_score', 0)
                )
                final_score = (text_score * 0.7) + (traditional_score * 0.3)
                scored_results.append({**item, 'score': final_score})
            # 按分数降序排序
            return sorted(scored_results, key=lambda x: x['score'], reverse=True)
        except Exception as error:
            print(f'语义重排序失败，使用基础排序 {error}')
            scored_results = []
            for item in results:
                score = self.calculate_relevance(
                    query, item['title'], item['snippet'], item['link'], item.get('authority_score', 0)
                )
                scored_results.append({**item, 'score': score})
            return sorted(scored_results, key=lambda x: x['score'], reverse=True)

    def calculate_text_similarity(self, query: str, query_keywords: List[str], content: str) -> float:
        content_keywords = self.segmenter.segment(content.lower())
        
        # 计算交集
        set_q = set(query_keywords)
        set_c = set(content_keywords)
        intersection_set = set_q.intersection(set_c)
        union_set = set_q.union(set_c)
        jaccard_score = len(union_set) > 0 and len(intersection_set) / len(union_set) or 0
        
        # 模拟 BM25+ 分数
        bm25_score = self.bm25_plus_score(content, set_q)
        
        # 编辑距离分数
        edit_distance_score = 0
        if len(query) < 50:
            max_len = max(len(query), len(content))
            distance = self.levenshtein_distance(query, content)
            edit_distance_score = 1 - (distance / max_len)
        
        # 覆盖率分数
        coverage_score = len([kw for kw in query_keywords if kw in content]) / len(query_keywords) if len(query_keywords) > 0 else 0
        
        result = jaccard_score * 0.3 + bm25_score * 0.4 + edit_distance_score * 0.1 + coverage_score * 0.2
        return result 

    def force_decode(self, text: str) -> str:
        try:
            text = text.replace('<br>', '\n').replace('<br/>', '\n').replace('<br />', '\n')
            text = text.replace('</p>', '\n')
            # 移除所有HTML标签 (简单模拟，实际可能需要正则库 re)
            # 这里写一个简单的循环移除，仅作示意，复杂HTML建议用BeautifulSoup
            while '<' in text and '>' in text:
                start = text.find('<')
                end = text.find('>', start)
                if end != -1:
                    text = text[:start] + text[end+1:]
                else:
                    break
            text = text.replace('\n\n', '\n').strip()
            return text
        except Exception as error:
            return text

    def levenshtein_distance(self, a: str, b: str) -> int:
        matrix = [[0] * (len(a) + 1) for _ in range(len(b) + 1)]
        for i in range(len(a) + 1):
            matrix[0][i] = i
        for j in range(len(b) + 1):
            matrix[j][0] = j
        for j in range(1, len(b) + 1):
            for i in range(1, len(a) + 1):
                cost = 0 if a[i-1] == b[j-1] else 1
                matrix[j][i] = min(
                    matrix[j][i-1] + 1,
                    matrix[j-1][i] + 1,
                    matrix[j-1][i-1] + cost
                )
        return matrix[len(b)][len(a)]

    def calculate_relevance(self, query: str, title: str, snippet: str, link: str, authority_score: float) -> float:
        if not query or not title or not snippet:
            return 0
        query_words = self.segmenter.segment(query.lower())
        query_set = set(query_words)
        
        title_score = self.bm25_plus_score(title, query_set)
        snippet_score = self.bm25_plus_score(snippet, query_set)
        link_score = self.calculate_link_score(link, query_set)
        
        combined_score = (title_score * 0.4) + (snippet_score * 0.4) + (link_score * 0.1) + (authority_score * 0.1)
        return min(1.0, combined_score)

    def bm25_plus_score(self, text: str, query_set: Set[str]) -> float:
        words = self.segmenter.segment(text.lower())
        k1 = 1.5
        b = 0.75
        delta = 1.0
        
        score = 0
        doc_length = len(words)
        
        # 计算词频
        term_frequency_map = {}
        for word in words:
            term_frequency_map[word] = term_frequency_map.get(word, 0) + 1
            
        # 计算平均词频
        if len(term_frequency_map) > 0:
            avg_term_frequency = sum(term_frequency_map.values()) / len(term_frequency_map)
        else:
            avg_term_frequency = 0
            
        # 假设平均文档长度为 100
        length_ratio = 100
        for term in query_set:
            tf = term_frequency_map.get(term, 0)
            idf = 0
            if tf > 0 and avg_term_frequency > 0:
                idf = math.log(1 + (tf / avg_term_frequency))
            
            # BM25+ 公式
            if avg_term_frequency > 0 and doc_length > 0:
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (doc_length / length_ratio))
                if denominator > 0:
                    term_score = idf * (numerator / denominator + delta)
                    if not (term_score != term_score): # 检查 NaN (Python 中用 math.isnan)
                        score += term_score
                        
        # 归一化
        normalized_score = 1 - (2.71828 ** (-score)) # Math.exp(-score)
        return min(max(normalized_score, 0), 1)

    def calculate_link_score(self, link: str, query_set: Set[str]) -> float:
        lower_link = link.lower()
        score = 0
        # 解析 URL 路径
        try:
            path = urlparse(lower_link).path
            path_keywords = [p for p in path.split('/') if p]
            for term in query_set:
                if any(term in kw for kw in path_keywords):
                    score += 0.2
        except:
            pass
        return min(1.0, score)