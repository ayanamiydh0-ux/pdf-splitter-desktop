"""
PDF 文本提取器模块
提取PDF文本内容，支持按页提取
"""

from typing import Dict, List, Optional
from PyPDF2 import PdfReader
import re


class PDFExtractor:
    """PDF文本提取器"""

    def __init__(self, pdf_path: str):
        """
        初始化PDF提取器

        参数：
            pdf_path: PDF文件路径
        """
        self.pdf_path = pdf_path
        self.reader = PdfReader(pdf_path)
        self.total_pages = len(self.reader.pages)

    def extract_all_pages(self) -> List[Dict]:
        """
        提取所有页面的文本

        返回：
            页面列表，格式：
            [
                {
                    'page_num': 1,
                    'text': '页面文本内容',
                    'word_count': 100,
                    'has_content': True
                },
                ...
            ]
        """
        pages_data = []

        for page_num, page in enumerate(self.reader.pages, start=1):
            page_data = self.extract_page(page_num)
            pages_data.append(page_data)

        return pages_data

    def extract_page(self, page_num: int) -> Dict:
        """
        提取指定页面的文本

        参数：
            page_num: 页码（从1开始）

        返回：
            页面信息：
            {
                'page_num': 页码,
                'text': '文本内容',
                'word_count': 词数,
                'has_content': True/False,
                'is_title_page': True/False,
                'header': '页眉',
                'footer': '页脚'
            }
        """
        # 获取页面对象（转换为0索引）
        page = self.reader.pages[page_num - 1]

        # 提取文本
        text = page.extract_text()

        # 检测页眉页脚
        header, footer = self._extract_header_footer(text)

        # 检测是否为标题页
        is_title = self._is_title_page(text)

        # 计算词数
        word_count = len(text.split()) if text else 0

        return {
            'page_num': page_num,
            'text': text or '',
            'word_count': word_count,
            'has_content': len(text.strip()) > 0,
            'is_title_page': is_title,
            'header': header,
            'footer': footer
        }

    def extract_pages_range(
        self,
        start_page: int,
        end_page: int,
        max_chars_per_page: Optional[int] = None
    ) -> List[Dict]:
        """
        提取指定范围的页面

        参数：
            start_page: 起始页码（从1开始）
            end_page: 结束页码（从1开始）
            max_chars_per_page: 每页最大字符数（用于节省token）

        返回：
            页面列表
        """
        pages_data = []

        for page_num in range(start_page, end_page + 1):
            page_data = self.extract_page(page_num)

            # 限制字符数
            if max_chars_per_page and len(page_data['text']) > max_chars_per_page:
                page_data['text'] = page_data['text'][:max_chars_per_page]
                page_data['truncated'] = True

            pages_data.append(page_data)

        return pages_data

    def extract_for_llm(
        self,
        chunk_info: Dict,
        max_chars_per_page: int = 500
    ) -> str:
        """
        提取用于LLM分析的内容（优化版）

        参数：
            chunk_info: {
                'id': 块ID,
                'read_range': (起始页, 结束页),
                'process_range': (起始页, 结束页)
            }
            max_chars_per_page: 每页最大字符数

        返回：
            格式化后的文本内容
        """
        read_start, read_end = chunk_info['read_range']
        pages = self.extract_pages_range(read_start, read_end, max_chars_per_page)

        # 格式化为LLM可读的格式
        formatted_lines = []

        for page in pages:
            page_num = page['page_num']
            text = page['text']

            if not text:
                continue

            # 标记标题页
            marker = " ⭐ 标题页" if page['is_title_page'] else ""

            formatted_lines.append(f"[PAGE {page_num}]{marker}")
            formatted_lines.append(text)
            formatted_lines.append("")  # 空行分隔

        return "\n".join(formatted_lines)

    def _extract_header_footer(self, text: str) -> tuple:
        """
        提取页眉页脚

        参数：
            text: 页面文本

        返回：
            (header, footer)
        """
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        if len(lines) < 3:
            return '', ''

        # 假设第一行是页眉，最后一行是页脚
        header = lines[0]
        footer = lines[-1]

        # 如果页眉/页脚太长（超过50字符），可能不是
        if len(header) > 50:
            header = ''
        if len(footer) > 50:
            footer = ''

        return header, footer

    def _is_title_page(self, text: str) -> bool:
        """
        判断是否为标题页

        参数：
            text: 页面文本

        返回：
            True/False
        """
        if not text or len(text) < 10:
            return False

        lines = [line.strip() for line in text.split('\n')[:5]]

        # 检查前几行是否有标题特征
        for line in lines:
            if not line:
                continue

            # 特征1：短且独立
            if len(line) < 100:
                # 特征2：有编号
                title_patterns = [
                    r'^\d+\.?',                  # 1. 或 1
                    r'^Chapter\s+\d+',          # Chapter 1
                    r'^CHAPTER\s+[IVX]+',       # CHAPTER I
                    r'^SESSION\s+\d+',          # SESSION 1
                    r'^PAPER\s+\d+',            # PAPER 1.1.1
                    r'^Section\s+\d+',          # Section 1
                    r'^[IVX]+\.?',              # I. II. III.
                    r'^[A-Z]+\s+\d+',          # A 1, B 2
                ]

                for pattern in title_patterns:
                    if re.match(pattern, line, re.IGNORECASE):
                        return True

                # 特征3：全大写
                if line.isupper() and 5 < len(line) < 50:
                    return True

                # 特征4：首字母大写
                if line.istitle() and 5 < len(line) < 50:
                    return True

        return False

    def get_total_pages(self) -> int:
        """获取总页数"""
        return self.total_pages

    def get_page_text(self, page_num: int, max_chars: Optional[int] = None) -> str:
        """
        获取指定页的文本

        参数：
            page_num: 页码（从1开始）
            max_chars: 最大字符数

        返回：
            页面文本
        """
        page_data = self.extract_page(page_num)
        text = page_data['text']

        if max_chars and len(text) > max_chars:
            text = text[:max_chars]

        return text

    def detect_empty_pages(self) -> List[int]:
        """
        检测空页或几乎空页

        返回：
            空页页码列表
        """
        empty_pages = []

        for page_num in range(1, self.total_pages + 1):
            page_data = self.extract_page(page_num)

            # 词数少于10认为是空页
            if page_data['word_count'] < 10:
                empty_pages.append(page_num)

        return empty_pages

    def get_document_statistics(self) -> Dict:
        """
        获取文档统计信息

        返回：
            {
                'total_pages': 总页数,
                'total_words': 总词数,
                'total_chars': 总字符数,
                'title_pages': 标题页数量,
                'empty_pages': 空页数量
            }
        """
        all_pages = self.extract_all_pages()

        total_words = sum(p['word_count'] for p in all_pages)
        total_chars = sum(len(p['text']) for p in all_pages)
        title_pages = sum(1 for p in all_pages if p['is_title_page'])
        empty_pages = sum(1 for p in all_pages if p['word_count'] < 10)

        return {
            'total_pages': self.total_pages,
            'total_words': total_words,
            'total_chars': total_chars,
            'title_pages': title_pages,
            'empty_pages': empty_pages
        }
