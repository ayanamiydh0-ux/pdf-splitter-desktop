#!/usr/bin/env python3
"""
PDF 智能拆分工具 - 桌面版引擎
支持流式处理大文件，使用策略模式实现可扩展的章节识别
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod

try:
    from PyPDF2 import PdfReader, PdfWriter
except ImportError:
    print(json.dumps({
        "error": "需要安装 PyPDF2: pip install PyPDF2"
    }))
    sys.exit(1)


@dataclass
class Chapter:
    """章节数据结构"""
    title: str
    start_page: int
    end_page: int
    content: str = ""
    level: int = 1
    chapter_number: str = ""  # 章节编号，如 "1.1"


class BaseSplitStrategy(ABC):
    """章节识别策略抽象基类"""

    @abstractmethod
    def analyze_page(self, header: str) -> str:
        """
        分析页面页眉，返回页面类型

        Args:
            header: 页眉文本

        Returns:
            'NEW_CHAPTER' - 新章节开始
            'VALID_CONTENT' - 有效内容（属于当前章节）
            'INVALID' - 无关内容（需要跳过）
        """

    @abstractmethod
    def extract_chapter_number(self, header: str) -> str:
        """
        从页眉中提取章节编号

        Args:
            header: 页眉文本

        Returns:
            章节编号字符串，如 "1.1"
        """

    @abstractmethod
    def extract_title(self, page_text: str) -> str:
        """
        从页面文本中提取章节标题（第一行内容）

        Args:
            page_text: 页面文本

        Returns:
            章节标题
        """


class ISSCCSessionStrategy(BaseSplitStrategy):
    """ISSCC会议论文集子主题拆分策略"""

    # 新章节页眉模式：SESSION X / TYPE / Y.Z（必须在行尾）
    NEW_CHAPTER_PATTERN = re.compile(
        r'SESSION\s+\d+\s*/\s*[\w\s]+\s*/\s*\d+\.\d+\s*$',
        re.IGNORECASE
    )

    # 章节编号提取模式：Y.Z（只在SESSION后面的Y.Z）
    CHAPTER_NUMBER_PATTERN = re.compile(r'SESSION\s+\d+\s*/\s*[\w\s]+\s*/\s*(\d+\.\d+)\s*$', re.IGNORECASE)

    # Figure页眉模式：Figure x.y.z
    FIGURE_PATTERN = re.compile(r'^Figure\s+\d+\.\d+\.\d+', re.IGNORECASE)

    # 时间页眉模式：ISSCC 2026 / February 16, 2026 / 10:45 AM
    TIME_PATTERN = re.compile(
        r'ISSCC\s+\d+\s*/\s*\w+\s+\d+,\s+\d+\s*/\s*\d+:\d+\s*(AM|PM)',
        re.IGNORECASE
    )

    # 无关页眉模式：PROGRAM, DIGEST OF TECHNICAL PAPERS 等
    INVALID_KEYWORDS = ['PROGRAM', 'DIGEST OF TECHNICAL PAPERS', 'TABLE OF CONTENTS']

    # 当前跟踪的章节页眉
    current_chapter_header: Optional[str] = None
    # 当前跟踪的章节编号
    current_chapter_number: Optional[str] = None

    def analyze_page(self, header: str) -> str:
        """
        分析页面页眉类型

        Args:
            header: 页眉文本

        Returns:
            'NEW_CHAPTER' - 新章节开始（章节编号发生变化）
            'VALID_CONTENT' - 有效内容（时间页眉、当前章节页眉）
            'INVALID' - 无关内容
        """
        if not header or not header.strip():
            return 'INVALID'

        header_upper = header.upper()

        # 先检查是否为章节页眉模式（优先）
        if self.NEW_CHAPTER_PATTERN.search(header):
            # 提取章节号（从SESSION页眉）
            session_chapter_number = self.extract_chapter_number(header)

            if not session_chapter_number:
                return 'INVALID'

            # 如果章节号与当前相同，属于当前章节
            if self.current_chapter_number and session_chapter_number == self.current_chapter_number:
                return 'VALID_CONTENT'

            # 章节号不同，可能是新章节
            # 但需要进一步验证：版权行中是否有章节号
            # 如果没有，说明这只是同一大章节内的续页，不是新的子章节
            return 'NEW_CHAPTER'

        # 再检查是否为时间页眉
        if self.TIME_PATTERN.search(header):
            return 'VALID_CONTENT'

        # 检查是否为Figure页（属于有效内容）
        if self.FIGURE_PATTERN.search(header):
            return 'VALID_CONTENT'

        # 检查是否为无关页
        for keyword in self.INVALID_KEYWORDS:
            if keyword in header_upper:
                return 'INVALID'

        # 其他情况都视为无效页
        return 'INVALID'

    def extract_chapter_number(self, header: str) -> str:
        """
        从页眉中提取章节编号（x.x 格式）

        Args:
            header: 页眉文本

        Returns:
            章节编号，如 "1.1"
        """
        match = self.CHAPTER_NUMBER_PATTERN.search(header)
        if match:
            return match.group(1)  # 返回捕获的章节编号，不是整个匹配
        return ""

    def extract_title(self, page_text: str) -> str:
        """
        从页面文本中提取标题（页眉行的下一行）

        Args:
            page_text: 页面文本

        Returns:
            标题文本
        """
        lines = page_text.split('\n')

        # 先找到页眉行（包含SESSION模式的行）
        header_line_idx = None
        for i, line in enumerate(lines):
            line_strip = line.strip()
            if line_strip and self.NEW_CHAPTER_PATTERN.search(line_strip):
                header_line_idx = i
                break

        # 如果找到页眉行，尝试提取标题
        if header_line_idx is not None:
            title = None
            check_line = header_line_idx + 1

            # 检查SESSION后面的几行，找到真正的标题
            while check_line < len(lines):
                current_line = lines[check_line].strip()
                if not current_line:
                    check_line += 1
                    continue

                # 如果这行包含版权信息
                if '979-8-3315-8936' in current_line:
                    # 检查是否有章节号（如 IEEE1.0, IEEE1.）
                    # 匹配模式：ISBN/价格 ©年份IEEE + 可选的章节号
                    match = re.search(r'^[\d\-/]+\$\d+\.?\d*\s+©\d+\s+IEEE(\d+\.?\d*)?\s*', current_line)
                    if match:
                        # 提取标题（去掉版权前缀后的内容）
                        title = re.sub(r'^[\d\-/]+\$\d+\.?\d*\s+©\d+\s+IEEE(\d+\.?\d*)?\s*', '', current_line)
                        # 如果有章节号（如 "1.0"），可能标题在同一行的后面
                        # 如果没有章节号，标题可能在下一行
                        if match.group(1):  # 有章节号
                            # 清理引用标记
                            title = re.sub(r'^\[[\d,-]+\]\s*,?\s*', '', title)
                            if title and len(title.strip()) > 3:
                                return title[:100]
                            check_line += 1
                            continue
                        else:
                            # 没有章节号，标题在下一行
                            check_line += 1
                            continue
                    else:
                        # 无法匹配版权模式，跳到下一行
                        check_line += 1
                        continue

                # 如果这行是Figure，跳过
                elif current_line.startswith('Figure'):
                    check_line += 1
                    continue

                # 如果这行以引用标记开头，清理后检查
                elif current_line.startswith('[') and ']' in current_line:
                    # 清理引用标记
                    cleaned = re.sub(r'^\[[\d,-]+\]\s*,?\s*', '', current_line)
                    if cleaned and len(cleaned) > 3:
                        return cleaned[:100]
                    check_line += 1
                    continue

                # 其他情况，可能是真正的标题
                else:
                    # 排除页眉相关内容和无效关键词
                    line_upper = current_line.upper()
                    invalid_keywords = ['SESSION', 'ISSCC', 'DIGEST', 'PAPERS', 'TABLE OF CONTENTS']
                    has_invalid = any(keyword in line_upper for keyword in invalid_keywords)
                    has_bullet = '•' in current_line

                    # 如果不包含无效关键词且不是页码行，可能是真正的标题
                    if not has_invalid and not has_bullet and len(current_line) > 3:
                        return current_line[:100]
                    check_line += 1
                    continue

        # 兜策略就用旧逻辑
        for line in lines:
            line = line.strip()
            if line and len(line) > 3:  # 跳过太短的行
                # 排除页眉（包含 SESSION 或 ISSCC）
                line_upper = line.upper()
                invalid_keywords = ['SESSION', 'ISSCC', 'DIGEST', 'PAPERS']
                has_invalid = any(keyword in line_upper for keyword in invalid_keywords)
                has_bullet = '•' in line

                if not has_invalid and not has_bullet:
                    return line[:100]  # 限制标题长度
        return "Untitled"


class PDFSplitter:
    """PDF 拆分器 - 支持策略模式"""

    def _has_chapter_number_in_copyright(self, page_text: str) -> bool:
        """
        检查版权行是否有章节号（如 IEEE1.0, IEEE1.）

        Args:
            page_text: 页面文本

        Returns:
            True 如果版权行有章节号，False 否则
        """
        lines = page_text.split('\n')
        for line in lines:
            line_strip = line.strip()
            # 查找包含版权信息的行
            if '979-8-3315-8936' in line_strip and '©' in line_strip:
                # 检查IEEE后面是否有章节号（如 1.0, 1., 4.2等）
                match = re.search(r'IEEE(\d+\.?\d*)\s+', line_strip)
                return match is not None
        return False

    def __init__(self):
        pass

    def analyze_pdf(self, pdf_path: str, strategy: BaseSplitStrategy,
                   progress_callback=None, debug: bool = False) -> List[Chapter]:
        """
        使用指定策略分析PDF章节结构

        Args:
            pdf_path: PDF文件路径
            strategy: 章节识别策略
            progress_callback: 进度回调函数 (progress, message, chapters)
            debug: 是否输出调试信息

        Returns:
            章节列表
        """
        chapters = []
        current_chapter = None

        # 重置策略状态
        if isinstance(strategy, ISSCCSessionStrategy):
            strategy.current_chapter_header = None
            strategy.current_chapter_number = None

        with open(pdf_path, 'rb') as file:
            pdf_reader = PdfReader(file)
            total_pages = len(pdf_reader.pages)

            if progress_callback:
                progress_callback(0, f"PDF共{total_pages}页，开始分析...", None)

            for i, page in enumerate(pdf_reader.pages):
                page_num = i + 1  # 1-based 页码
                text = page.extract_text() or ""

                # 提取页眉（智能查找真正的页眉）
                header = self._extract_header(text, strategy)

                # 分析页面类型
                page_type = strategy.analyze_page(header)

                if debug:
                    print(f"Page {page_num}: Type={page_type}, Header='{header[:50]}'")

                # 每10页发送进度
                if progress_callback and (page_num % 10 == 0 or page_num == total_pages):
                    progress = (page_num / total_pages) * 50
                    progress_callback(progress, f"正在分析第{page_num}/{total_pages}页...", None)

                # 处理页面类型
                if page_type == 'NEW_CHAPTER':
                    # 提取SESSION章节号
                    session_chapter_number = strategy.extract_chapter_number(header)

                    # 确定是否为新章节：
                    # 情况1: SESSION章节号与当前不同（如 1.3 → 1.4）→ 新章节
                    # 情况2: SESSION章节号相同，但版权行有章节号 → 新子章节
                    is_new_chapter = False

                    if strategy.current_chapter_number and session_chapter_number != strategy.current_chapter_number:
                        # SESSION章节号变化，这是新章节
                        is_new_chapter = True
                    elif self._has_chapter_number_in_copyright(text):
                        # 版权行有章节号，这是新子章节
                        is_new_chapter = True

                    if is_new_chapter:
                        # 保存上一个章节
                        if current_chapter:
                            current_chapter.end_page = page_num - 1
                            chapters.append(current_chapter)

                        # 创建新章节
                        chapter_number = session_chapter_number
                        title = strategy.extract_title(text)

                        current_chapter = Chapter(
                            title=title,
                            start_page=page_num,
                            end_page=page_num,
                            content="",
                            level=1,
                            chapter_number=chapter_number
                        )

                        # 更新策略状态
                        if isinstance(strategy, ISSCCSessionStrategy):
                            strategy.current_chapter_header = header
                            strategy.current_chapter_number = chapter_number

                        if progress_callback:
                            progress_callback(
                                (page_num / total_pages) * 50,
                                f"发现章节: {title[:50]}... (编号: {chapter_number})",
                                None
                            )

                elif page_type == 'VALID_CONTENT':
                    # 属于当前章节，继续
                    continue

                elif page_type == 'INVALID':
                    # 无关页，结束当前章节
                    if current_chapter:
                        current_chapter.end_page = page_num - 1
                        chapters.append(current_chapter)
                        current_chapter = None
                        # 重置策略状态
                        if isinstance(strategy, ISSCCSessionStrategy):
                            strategy.current_chapter_header = None
                            strategy.current_chapter_number = None

            # 保存最后一个章节
            if current_chapter:
                current_chapter.end_page = total_pages
                chapters.append(current_chapter)

        if progress_callback:
            progress_callback(50, f"分析完成！共找到 {len(chapters)} 个章节", None)

        return chapters

    def _extract_header(self, page_text: str, strategy=None) -> str:
        """
        从页面文本中提取页眉

        优先查找真正的页眉（SESSION），其次查找时间格式

        Args:
            page_text: 页面文本
            strategy: 章节识别策略（用于获取模式）

        Returns:
            页眉文本
        """
        if not page_text:
            return ""

        lines = page_text.split('\n')

        # 如果提供了策略，使用策略中的模式来查找真正的页眉
        if strategy and isinstance(strategy, ISSCCSessionStrategy):
            # 在整个页面文本中查找匹配 SESSION 模式的行（优先）
            for line in lines:
                line_strip = line.strip()
                if strategy.NEW_CHAPTER_PATTERN.search(line_strip):
                    return line_strip

            # 没有找到SESSION模式，查找时间模式
            for line in lines:
                line_strip = line.strip()
                if strategy.TIME_PATTERN.search(line_strip):
                    return line_strip

        # 没有找到特定模式的页眉，返回第一行
        for line in lines:
            line = line.strip()
            if line:
                return line
        return ""

    def split_pdf(self, pdf_path: str, output_dir: str, chapters: List[dict],
                  progress_callback=None):
        """
        拆分PDF

        Args:
            pdf_path: 输入PDF路径
            output_dir: 输出目录
            chapters: 要拆分的章节列表
            progress_callback: 进度回调

        Returns:
            生成的文件列表
        """
        output_files = []

        with open(pdf_path, 'rb') as f:
            reader = PdfReader(f)
            total_chapters = len(chapters)

            for i, chapter in enumerate(chapters):
                # 发送进度
                if progress_callback:
                    progress = 50 + ((i + 1) / total_chapters) * 50
                    progress_callback(progress, f"正在拆分: {chapter['title'][:40]}...", None)

                # 创建PDF writer
                writer = PdfWriter()
                start_page = chapter['start_page'] - 1  # 转为0-based
                end_page = chapter['end_page']  # end_page是包含性的

                for page_idx in range(start_page, end_page):
                    if page_idx < len(reader.pages):
                        writer.add_page(reader.pages[page_idx])

                # 生成文件名：编号_标题.pdf
                chapter_number = chapter.get('chapter_number', str(i + 1))
                safe_title = re.sub(r'[^\w\s-]', '', chapter['title'])[:30].strip()
                filename = f"{chapter_number}_{safe_title}.pdf"
                output_path = Path(output_dir) / filename

                # 写入文件
                with open(output_path, 'wb') as out_f:
                    writer.write(out_f)

                file_size = output_path.stat().st_size
                output_files.append({
                    'name': filename,
                    'path': str(output_path),
                    'size': f"{file_size / 1024:.1f} KB",
                    'pages': end_page - start_page
                })

                # 释放内存
                del writer

        return output_files


def main():
    """命令行入口 - 用于桌面应用调用"""
    parser = argparse.ArgumentParser()
    parser.add_argument('--action', choices=['analyze', 'split'], required=True)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', default=None)
    parser.add_argument('--chapters', default=None, help='章节JSON字符串')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')

    args = parser.parse_args()

    splitter = PDFSplitter()

    def send_progress(progress, message, data):
        """发送进度到stdout"""
        output = {
            'type': 'progress',
            'progress': progress,
            'message': message
        }
        if data:
            output['data'] = data
        print(json.dumps(output, ensure_ascii=False))
        sys.stdout.flush()

    try:
        if args.action == 'analyze':
            # 使用 ISSCC 会议论文集策略
            strategy = ISSCCSessionStrategy()
            chapters = splitter.analyze_pdf(args.input, strategy, send_progress, debug=args.debug)

            # 发送最终结果
            result = {
                'type': 'complete',
                'chapters': [
                    {
                        'title': ch.title,
                        'start_page': ch.start_page,
                        'end_page': ch.end_page,
                        'level': ch.level,
                        'chapter_number': ch.chapter_number
                    }
                    for ch in chapters
                ]
            }
            print(json.dumps(result, ensure_ascii=False))

        elif args.action == 'split':
            if not args.chapters:
                raise ValueError("拆分操作需要提供 --chapters 参数")

            chapters = json.loads(args.chapters)
            output_dir = args.output or Path(args.input).parent / "split_output"
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            files = splitter.split_pdf(args.input, output_dir, chapters, send_progress)

            result = {
                'type': 'complete',
                'files': files,
                'output_dir': str(output_dir)
            }
            print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        error_result = {
            'type': 'error',
            'error': str(e)
        }
        print(json.dumps(error_result, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
