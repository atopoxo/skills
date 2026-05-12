# -*- coding: utf-8 -*-
import re
from pathlib import Path


class ErrorLogAppender:
    """将 input/cache/*.log 中匹配 <ERROR:*>: 的行拼接到 input/server.log 末尾."""

    ERROR_PATTERN = re.compile(r'<ERROR:\d+>:')

    def __init__(self, base_dir=None):
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
        self.base_dir = Path(base_dir)
        self.cache_dir = self.base_dir / 'input' / 'cache'
        self.target_log = self.base_dir / 'input' / 'server.log'

    def _detect_encoding(self, filepath):
        try:
            import chardet
            with open(filepath, 'rb') as f:
                raw = f.read(200000)
            result = chardet.detect(raw)
            return result['encoding'] or 'utf-8'
        except ImportError:
            pass
        for enc in ['utf-8', 'gbk', 'gb18030', 'latin-1']:
            try:
                with open(filepath, 'r', encoding=enc) as f:
                    f.read(100000)
                return enc
            except (UnicodeDecodeError, UnicodeError):
                continue
        return 'latin-1'

    def _extract_error_lines(self, filepath):
        encoding = self._detect_encoding(filepath)
        matched = []
        with open(filepath, 'r', encoding=encoding, errors='replace') as f:
            for line in f:
                if self.ERROR_PATTERN.search(line):
                    matched.append(line.rstrip('\n\r'))
        return matched

    def run(self):
        log_files = sorted(self.cache_dir.glob('*.log'))
        if not log_files:
            print(f"[error_log_append] 未在 {self.cache_dir} 找到 .log 文件")
            return

        target_encoding = self._detect_encoding(self.target_log)

        entries = []
        total = 0
        for fp in log_files:
            lines = self._extract_error_lines(fp)
            if lines:
                entries.append((fp.name, lines))
                total += len(lines)
                print(f"  {fp.name}: {len(lines)} 条 ERROR 行")
            else:
                print(f"  {fp.name}: 无 ERROR 行")

        if not entries:
            print("[error_log_append] 未找到任何 ERROR 行")
            return

        # 检查目标文件末尾是否有换行，没有则先补一个
        need_newline = False
        if self.target_log.exists() and self.target_log.stat().st_size > 0:
            with open(self.target_log, 'rb') as f:
                f.seek(-1, 2)
                need_newline = f.read(1) != b'\n'

        with open(self.target_log, 'a', encoding=target_encoding) as f:
            if need_newline:
                f.write('\n')
            for filename, lines in entries:
                f.write(f'---{{{filename}}}---\n')
                for line in lines:
                    f.write(line + '\n')

        print(f"\n[error_log_append] 已将 {total} 条 ERROR 行(来自 {len(entries)} 个文件)追加到 {self.target_log}")


def main():
    ErrorLogAppender().run()


if __name__ == '__main__':
    main()
