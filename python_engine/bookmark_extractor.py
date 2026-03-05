"""
书签提取器模块
从PDF提取书签/大纲结构
"""

from typing import Dict, List, Optional
from PyPDF2 import PdfReader


class BookmarkExtractor:
    """PDF书签提取器"""

    def __init__(self, pdf_path: str):
        """
        初始化书签提取器

        参数：
            pdf_path: PDF文件路径
        """
        self.pdf_path = pdf_path
        self.reader = PdfReader(pdf_path)

    def extract_bookmarks(self) -> List[Dict]:
        """
        提取PDF书签结构

        返回：
            书签列表，格式：
            [
                {
                    'level': 0,
                    'title': '章节标题',
                    'page_num': 页码,
                    'children': [子书签]
                },
                ...
            ]

            如果没有书签，返回空列表
        """
        outline = self.reader.outline

        if not outline:
            return []

        bookmarks = self._process_outline(outline)
        return bookmarks

    def _process_outline(self, outline_items, level: int = 0) -> List[Dict]:
        """
        递归处理书签结构

        参数：
            outline_items: 书签项列表
            level: 层级

        返回：
            处理后的书签列表
        """
        bookmarks = []

        for item in outline_items:
            if isinstance(item, list):
                # 递归处理子书签
                bookmarks.extend(self._process_outline(item, level))
                continue

            # 获取标题
            title = item.title if hasattr(item, 'title') else str(item)

            # 获取页码
            page_num = self._get_page_number(item)

            bookmark = {
                'level': level,
                'title': title,
                'page_num': page_num
            }

            # 处理子书签
            if isinstance(item, dict) and item.get('children'):
                bookmark['children'] = self._process_outline(
                    item['children'],
                    level + 1
                )

            bookmarks.append(bookmark)

        return bookmarks

    def _get_page_number(self, item) -> int:
        """
        获取书签对应的页码

        参数：
            item: 书签项

        返回：
            页码（从1开始）
        """
        try:
            if hasattr(item, 'dest'):
                # 使用destination获取页码
                page_num = self.reader.get_destination_page_number(item.dest)
                return page_num + 1  # 转为1索引

            elif isinstance(item, dict) and item.get('dest'):
                page_num = self.reader.get_destination_page_number(item['dest'])
                return page_num + 1

            else:
                # 如果无法获取页码，返回0表示未知
                return 0

        except Exception:
            return 0

    def extract_chapters_from_bookmarks(self) -> List[Dict]:
        """
        从书签提取章节信息

        返回：
            章节列表，格式：
            [
                {
                    'title': '章节标题',
                    'start_page': 起始页码,
                    'end_page': 结束页码,
                    'level': 层级,
                    'filename': '建议的文件名.pdf'
                },
                ...
            ]
        """
        bookmarks = self.extract_bookmarks()

        if not bookmarks:
            return []

        chapters = self._convert_bookmarks_to_chapters(bookmarks)
        return chapters

    def _convert_bookmarks_to_chapters(self, bookmarks: List[Dict]) -> List[Dict]:
        """
        将书签转换为章节列表

        参数：
            bookmarks: 书签列表

        返回：
            章节列表
        """
        # 扁平化书签树
        flattened = self._flatten_bookmarks(bookmarks)

        # 按层级分组
        chapters = self._group_by_level(flattened)

        # 计算页码范围
        for i in range(len(chapters)):
            if i < len(chapters) - 1:
                chapters[i]['end_page'] = chapters[i + 1]['start_page'] - 1
            else:
                # 最后一章，到文档结尾
                chapters[i]['end_page'] = len(self.reader.pages)

        # 生成文件名
        for chapter in chapters:
            chapter['filename'] = self._generate_filename(chapter)

        return chapters

    def _flatten_bookmarks(self, bookmarks: List[Dict], level: int = 0) -> List[Dict]:
        """
        扁平化书签树（只保留顶层或指定层级）

        参数：
            bookmarks: 书签列表
            level: 当前层级

        返回：
            扁平化的书签列表
        """
        flattened = []

        for bookmark in bookmarks:
            # 添加当前书签
            flattened.append({
                'title': bookmark['title'],
                'start_page': bookmark['page_num'],
                'level': bookmark['level']
            })

            # 递归处理子书签
            if 'children' in bookmark:
                flattened.extend(
                    self._flatten_bookmarks(bookmark['children'], level + 1)
                )

        return flattened

    def _group_by_level(self, flattened: List[Dict]) -> List[Dict]:
        """
        按层级分组，默认只取层级0的书签

        参数：
            flattened: 扁平化的书签列表

        返回：
            章节列表
        """
        # 只取顶层书签（level=0）
        top_level = [b for b in flattened if b['level'] == 0]

        # 按页码排序
        top_level.sort(key=lambda x: x['start_page'])

        return top_level

    def _generate_filename(self, chapter: Dict) -> str:
        """
        生成文件名

        参数：
            chapter: 章节信息

        返回：
            文件名
        """
        title = chapter['title']
        # 清理特殊字符
        title = self._sanitize_filename(title)
        return f"{title}.pdf"

    def _sanitize_filename(self, filename: str) -> str:
        """
        清理文件名，移除非法字符

        参数：
            filename: 原始文件名

        返回：
            清理后的文件名
        """
        # Windows非法字符
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')

        # 移除多余下划线
        while '__' in filename:
            filename = filename.replace('__', '_')

        # 限制长度
        if len(filename) > 100:
            filename = filename[:100]

        return filename.strip('_')

    def has_bookmarks(self) -> bool:
        """
        检查PDF是否有书签

        返回：
            True/False
        """
        return self.reader.outline is not None and len(self.reader.outline) > 0

    def get_bookmark_statistics(self) -> Dict:
        """
        获取书签统计信息

        返回：
            {
                'has_bookmarks': True/False,
                'total_bookmarks': 总书签数,
                'max_level': 最大层级,
                'pages_with_bookmarks': 有书签的页码列表
            }
        """
        bookmarks = self.extract_bookmarks()

        if not bookmarks:
            return {
                'has_bookmarks': False,
                'total_bookmarks': 0,
                'max_level': 0,
                'pages_with_bookmarks': []
            }

        # 计算统计信息
        total = len(bookmarks)
        max_level = max(b['level'] for b in bookmarks)
        pages = sorted(set(b['page_num'] for b in bookmarks))

        return {
            'has_bookmarks': True,
            'total_bookmarks': total,
            'max_level': max_level,
            'pages_with_bookmarks': pages
        }
