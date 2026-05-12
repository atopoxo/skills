import re
from typing import List

# 模拟 Intl.Segmenter 的 Python 实现
# Python 标准库没有直接的 Intl.Segmenter，这里使用 regex 模拟其提取 "WordLike" 的行为
class IntlSegmenter:
    def __init__(self, locales=None, granularity='word'):
        # 使用正则表达式匹配单词字符（包括 Unicode）和空白
        # \w 匹配字母数字和下划线，\s 匹配空白
        self.pattern = re.compile(r'\w+|\s+|[^\w\s]', re.UNICODE)

    def segment(self, text: str):
        # 返回一个生成器，模拟 Iterable
        for match in self.pattern.finditer(text):
            segment_text = match.group()
            # 模拟 isWordLike: 如果不是纯空白或纯标点，则视为类似单词
            is_word_like = bool(re.match(r'\w', segment_text, re.UNICODE))
            yield {'segment': segment_text, 'isWordLike': is_word_like}

class TinySegmenter:
    def __init__(self):
        # 简单的基于正则的分词，作为 tiny-segmenter 的替代品
        self.pattern = re.compile(r'\w+|[^\w\s]', re.UNICODE)

    def segment(self, text: str) -> List[str]:
        return self.pattern.findall(text)

class TextSegmenter:
    def __init__(self):
        self.segmenter = None
        self.use_intl_segmenter = self.__is_intl_segmenter_available()
        
        if self.use_intl_segmenter:
            self.segmenter = IntlSegmenter(None, granularity='word')
        else:
            print('使用轻量级分词器处理多语言文本，建议升级到 Node.js 18+ 以获得更好的分词效果')
            self.segmenter = TinySegmenter()

    def segment(self, text: str) -> List[str]:
        if not text:
            return []
        if self.use_intl_segmenter:
            return self.__segment_with_intl(text)
        else:
            return self.__segment_with_tiny(text)

    def __is_intl_segmenter_available(self) -> bool:
        try:
            test_segmenter = IntlSegmenter('en', granularity='word')
            test_segments = list(test_segmenter.segment('test'))
            return len(test_segments) > 0
        except Exception:
            return False

    def __segment_with_intl(self, text: str) -> List[str]:
        try:
            segments = self.segmenter.segment(text)
            tokens = []
            for item in segments:
                if item['isWordLike']:
                    tokens.append(item['segment'])
            return tokens
        except Exception:
            return self.__segment_with_tiny(text)

    def __segment_with_tiny(self, text: str) -> List[str]:
        # 模拟 .filter(token => token.trim().length > 0)
        # 和 .filter(token => !/^[\s\p{P}]+$/u.test(token))
        tokens = self.segmenter.segment(text)
        result = []
        for token in tokens:
            if not token.strip():
                continue
            if re.fullmatch(r'[\s\W]+', token):
                continue
            result.append(token)
        return result