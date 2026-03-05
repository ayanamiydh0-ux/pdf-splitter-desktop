"""
PDF 分割器模块
执行PDF分割操作
"""

import os
import sys
from typing import Dict, List, Optional

# 设置模块搜索路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from PyPDF2 import PdfReader, PdfWriter


class PDFSplitter:
    """PDF分割器"""

    def __init__(self, pdf_path: str):
        """
        初始化PDF分割器

        参数：
            pdf_path: PDF文件路径
        """
        self.pdf_path = pdf_path
        self.reader = PdfReader(pdf_path)
        self.total_pages = len(self.reader.pages)

    def split_by_chapters(
        self,
        chapters: List[Dict],
        output_dir: str,
        filename_template: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> List[Dict]:
        """
        按章节分割PDF

        参数：
            chapters: 章节列表，格式：
                [
                    {
                        'title': '章节标题',
                        'start_page': 起始页码,
                        'end_page': 结束页码,
                        'filename': '文件名.pdf'
                    },
                    ...
                ]
            output_dir: 输出目录
            filename_template: 文件名模板（可选）
            progress_callback: 进度回调函数

        返回：
            分割结果列表：
                [
                    {
                        'chapter': {...},
                        'filename': 'Session_1.pdf',
                        'path': '/path/to/file.pdf',
                        'page_count': 10,
                        'file_size': 12345
                    },
                    ...
                ]
        """
        results = []
        total_chapters = len(chapters)

        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)

        for i, chapter in enumerate(chapters):
            # 更新进度
            if progress_callback:
                progress_callback(f"正在分割: {chapter.get('title', f'Chapter {i+1}')} ({i+1}/{total_chapters})")

            # 执行分割
            result = self._split_single_chapter(chapter, output_dir, filename_template)
            results.append(result)

        return results

    def _split_single_chapter(
        self,
        chapter: Dict,
        output_dir: str,
        filename_template: Optional[str] = None
    ) -> Dict:
        """
        分割单个章节

        参数：
            chapter: 章节信息
            output_dir: 输出目录
            filename_template: 文件名模板

        返回：
            分割结果
        """
        # 获取页码范围
        start_page = chapter.get('start_page', 1)
        end_page = chapter.get('end_page', self.total_pages)

        # 转换为0索引
        start_page_idx = start_page - 1
        end_page_idx = end_page - 1

        # 验证页码范围
        if start_page_idx < 0:
            start_page_idx = 0
        if end_page_idx >= self.total_pages:
            end_page_idx = self.total_pages - 1

        # 创建新的PDF写入器
        writer = PdfWriter()

        # 复制页面
        for page_num in range(start_page_idx, end_page_idx + 1):
            writer.add_page(self.reader.pages[page_num])

        # 生成文件名
        filename = chapter.get('filename', f'chapter_{start_page}.pdf')
        if filename_template:
            filename = self._apply_filename_template(filename_template, chapter, filename)

        # 确保扩展名
        if not filename.lower().endswith('.pdf'):
            filename += '.pdf'

        # 保存文件
        output_path = os.path.join(output_dir, filename)

        try:
            with open(output_path, 'wb') as f:
                writer.write(f)

            # 获取文件信息
            file_size = os.path.getsize(output_path)
            page_count = end_page_idx - start_page_idx + 1

            return {
                'chapter': chapter,
                'filename': filename,
                'path': output_path,
                'page_count': page_count,
                'file_size': file_size,
                'success': True
            }

        except Exception as e:
            return {
                'chapter': chapter,
                'filename': filename,
                'path': output_path,
                'page_count': 0,
                'file_size': 0,
                'success': False,
                'error': str(e)
            }

    def _apply_filename_template(
        self,
        template: str,
        chapter: Dict,
        default_filename: str
    ) -> str:
        """
        应用文件名模板

        模板变量：
            {title} - 章节标题
            {start_page} - 起始页码
            {end_page} - 结束页码
            {page_count} - 页数
            {index} - 章节索引

        参数：
            template: 模板字符串
            chapter: 章节信息
            default_filename: 默认文件名

        返回：
            应用模板后的文件名
        """
        try:
            # 替换模板变量
            filename = template.format(
                title=chapter.get('title', ''),
                start_page=chapter.get('start_page', 0),
                end_page=chapter.get('end_page', 0),
                page_count=chapter.get('end_page', 0) - chapter.get('start_page', 0) + 1,
                index=chapter.get('index', 0)
            )
            return filename
        except Exception:
            # 模板应用失败，使用默认文件名
            return default_filename

    def split_by_page_ranges(
        self,
        page_ranges: List[tuple],
        output_dir: str,
        prefix: str = 'output'
    ) -> List[Dict]:
        """
        按页码范围分割PDF

        参数：
            page_ranges: 页码范围列表，如 [(1, 10), (11, 20)]
            output_dir: 输出目录
            prefix: 文件名前缀

        返回：
            分割结果列表
        """
        results = []

        for i, (start_page, end_page) in enumerate(page_ranges):
            chapter = {
                'title': f'{prefix}_{i+1}',
                'start_page': start_page,
                'end_page': end_page,
                'filename': f'{prefix}_{i+1}.pdf'
            }

            result = self._split_single_chapter(chapter, output_dir)
            results.append(result)

        return results

    def split_by_pages(
        self,
        pages_per_file: int,
        output_dir: str,
        prefix: str = 'part'
    ) -> List[Dict]:
        """
        按固定页数分割PDF

        参数：
            pages_per_file: 每个文件的页数
            output_dir: 输出目录
            prefix: 文件名前缀

        返回：
            分割结果列表
        """
        page_ranges = []
        total_pages = self.total_pages

        current_page = 1
        file_num = 1

        while current_page <= total_pages:
            end_page = min(current_page + pages_per_file - 1, total_pages)
            page_ranges.append((current_page, end_page))
            current_page = end_page + 1
            file_num += 1

        return self.split_by_page_ranges(page_ranges, output_dir, prefix)

    def extract_page(
        self,
        page_num: int,
        output_path: str
    ) -> bool:
        """
        提取单个页面

        参数：
            page_num: 页码（从1开始）
            output_path: 输出文件路径

        返回：
            True/False
        """
        try:
            # 转换为0索引
            page_idx = page_num - 1

            if page_idx < 0 or page_idx >= self.total_pages:
                return False

            # 创建新的PDF写入器
            writer = PdfWriter()
            writer.add_page(self.reader.pages[page_idx])

            # 保存文件
            with open(output_path, 'wb') as f:
                writer.write(f)

            return True

        except Exception:
            return False

    def merge_selected_pages(
        self,
        page_numbers: List[int],
        output_path: str
    ) -> bool:
        """
        合并选定的页面

        参数：
            page_numbers: 页码列表（从1开始）
            output_path: 输出文件路径

        返回：
            True/False
        """
        try:
            # 创建新的PDF写入器
            writer = PdfWriter()

            for page_num in page_numbers:
                # 转换为0索引
                page_idx = page_num - 1

                if 0 <= page_idx < self.total_pages:
                    writer.add_page(self.reader.pages[page_idx])

            # 保存文件
            with open(output_path, 'wb') as f:
                writer.write(f)

            return True

        except Exception:
            return False

    def get_total_pages(self) -> int:
        """获取总页数"""
        return self.total_pages

    def get_file_size(self) -> int:
        """获取文件大小（字节）"""
        try:
            return os.path.getsize(self.pdf_path)
        except Exception:
            return 0

    def get_file_size_mb(self) -> float:
        """获取文件大小（MB）"""
        return self.get_file_size() / (1024 * 1024)
