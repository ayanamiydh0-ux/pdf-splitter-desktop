#!/usr/bin/env python3
"""
PDF 智能拆分工具 - 桌面版引擎
支持流式处理大文件
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass, asdict

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


class PDFSplitter:
    """PDF 拆分器"""

    # 章节标题匹配模式
    CHAPTER_PATTERNS = [
        # 数字 + 标题模式（论文会话）：1 Plenary - Invited Papers
        (r'^\d+\s+[A-Z][a-z]+[\w\s&\-]+', 1),
        # Section 1
        (r'^(Section|SECTION)\s+\d+\s+[A-Z]', 1),
        # 第1章 / 第一章
        (r'^第[一二三四五六七八九十0-9]+章\s+[\u4e00-\u9fa5]{2,}', 1),
        # Abstract / Introduction / Conclusion / Foreword / Awards
        (r'^(Abstract|Introduction|Conclusion|References|Appendix|Foreword|Awards)\s*$', 1),
    ]

    # 排除的关键词（页眉、脚注等）
    EXCLUDED_KEYWORDS = [
        'DIGEST OF TECHNICAL PAPERS',
        'Abstracting is permitted',
        'Libraries are perm',
        'W ILEY',
        'WILEY',
        'PRESS',
        'PROFESSIONAL',
        'INTENTIONALLY LEFT BLANK',
        'This Page Intentionally',
        'Page Intentionally',
        'F1:',
        'C - SECOND FLOOR',
        'FOOTHILL',
        'REGIONAL CHAIR',
        'AMERICAS',
        'EUROPE',
        'ASIA',
        'arxiv.org',
        'doi.org',
        'http://',
        'https://',
    ]

    # 单位和测量值（用于排除纯技术参数）
    UNIT_PATTERNS = [
        r'^[\d.]+\s*(GHz|THz|GS/s|pJ/b|Gb/s|nm|V|mA)$',
        r'^\d+\.?\d*\s*(GHz|THz|GS/s|pJ/b|Gb/s|nm|V|mA)\s*$',
    ]

    def is_valid_chapter_title(self, line: str) -> bool:
        """
        检查是否是有效的章节标题

        排除：
        - 只包含数字和单位
        - URL/引用
        - 页面标注（如页码、标注）
        - 过短或过长的行
        """
        line_upper = line.upper()
        line_lower = line.lower()
        line_stripped = line.strip()

        # 检查排除关键词
        for keyword in self.EXCLUDED_KEYWORDS:
            if keyword.upper() in line_upper:
                return False

        # 排除包含 DIGEST OF TECHNICAL PAPERS 的行（页眉）
        if 'DIGEST OF TECHNICAL PAPERS' in line_upper:
            return False

        # 排除纯数字或单位
        if re.match(r'^[\d\s\.\-/]+[a-zA-Z]{0,3}$', line_stripped):
            return False

        # 排除URL/引用格式
        if 'https://' in line_lower or 'http://' in line_lower:
            return False
        if re.search(r'arxiv\.org|doi\.org', line_lower):
            return False

        # 排除纯单位格式（使用更精确的模式）
        for pattern in self.UNIT_PATTERNS:
            if re.match(pattern, line_stripped):
                return False

        # 排除标注行（如括号内容、页码标注）
        if re.match(r'^\[\d+\]', line_stripped) or re.match(r'^\d+\s+l[oa]n[eg]', line_lower):
            return False

        # 清理点号（目录中的对齐点）
        cleaned_line = re.sub(r'\.{3,}', '', line_stripped)

        # 标题至少要有2个单词（中文除外）
        word_count = len(cleaned_line.split())
        if word_count < 2 and not re.search(r'[\u4e00-\u9fa5]', line):
            return False

        return True

    def __init__(self, max_size_mb: float = 5.0, max_chars: int = 50000):
        self.max_size_mb = max_size_mb
        self.max_chars = max_chars
        self.max_bytes = int(max_size_mb * 1024 * 1024)

    def analyze_pdf(self, pdf_path: str, progress_callback=None):
        """
        分析PDF章节结构

        Args:
            pdf_path: PDF文件路径
            progress_callback: 进度回调函数 (progress, message, chapters)

        Returns:
            章节列表
        """
        chapters = []

        with open(pdf_path, 'rb') as file:
            pdf_reader = PdfReader(file)
            total_pages = len(pdf_reader.pages)

            # 发送总页数信息
            if progress_callback:
                progress_callback(0, f"PDF共{total_pages}页，开始分析...", None)

            # 先尝试从目录页提取章节（ISSCC会议论文集格式）
            toc_found = False
            for i in range(min(10, total_pages)):  # 检查前10页
                page = pdf_reader.pages[i]
                text = page.extract_text() or ""

                # 检查是否包含目录标识
                if 'TABLE OF CONTENTS' in text.upper() or 'PAPER SESSIONS' in text.upper():
                    toc_found = True
                    chapters = self._extract_from_toc(text, i + 1, total_pages)
                    if progress_callback:
                        progress_callback(50, f"从目录提取到 {len(chapters)} 个章节", None)
                    break

            # 如果没找到目录，使用传统扫描方法
            if not toc_found:
                current_chapter = None
                current_content = []

                for i, page in enumerate(pdf_reader.pages):
                    page_num = i + 1
                    text = page.extract_text() or ""

                    # 每10页或最后一页发送进度
                    if progress_callback and (page_num % 10 == 0 or page_num == total_pages):
                        progress = (page_num / total_pages) * 50  # 分析阶段占50%
                        progress_callback(progress, f"正在分析第{page_num}/{total_pages}页...", None)

                    # 检测章节
                    lines = text.split('\n')
                    chapter_found = False

                    for line in lines[:15]:  # 检查前15行
                        line = line.strip()
                        if not line or len(line) > 200:  # 跳过空行和过长的行
                            continue

                        # 验证是否是有效的章节标题
                        if not self.is_valid_chapter_title(line):
                            continue

                        for pattern, level in self.CHAPTER_PATTERNS:
                            if re.match(pattern, line, re.IGNORECASE):
                                # 保存上一个章节
                                if current_chapter:
                                    current_chapter.end_page = page_num - 1
                                    current_chapter.content = '\n'.join(current_content)
                                    chapters.append(current_chapter)

                                # 创建新章节
                                current_chapter = Chapter(
                                    title=line[:100],
                                    start_page=page_num,
                                    end_page=page_num,
                                    content="",
                                    level=level
                                )
                                current_content = [text]
                                chapter_found = True

                                if progress_callback:
                                    progress_callback(
                                        (page_num / total_pages) * 50,
                                        f"发现章节: {line[:50]}...",
                                        None
                                    )
                                break

                    if chapter_found:
                        break

                if not chapter_found and current_chapter:
                    current_content.append(text)

                # 保存最后一个章节
                if current_chapter:
                    current_chapter.end_page = total_pages
                    current_chapter.content = '\n'.join(current_content)
                    chapters.append(current_chapter)

            # 如果没有检测到章节，把整个文档作为一个章节
            if not chapters:
                full_content = '\n'.join([
                    pdf_reader.pages[i].extract_text() or ""
                    for i in range(total_pages)
                ])
                chapters.append(Chapter(
                    title="完整文档",
                    start_page=1,
                    end_page=total_pages,
                    content=full_content,
                    level=1
                ))

        return chapters

    def _extract_from_toc(self, toc_text: str, toc_page: int, total_pages: int) -> list:
        """
        从目录文本中提取章节信息

        Args:
            toc_text: 目录页的文本
            toc_page: 目录页码
            total_pages: 总页数

        Returns:
            章节列表
        """
        chapters = []
        lines = toc_text.split('\n')

        # 找到 PAPER SESSIONS 部分的开始
        in_paper_sessions = False
        current_chapter_num = 0
        next_start_page = toc_page + 1  # 默认目录后下一页开始

        for i, line in enumerate(lines):
            line = line.strip()

            # 进入 PAPER SESSIONS 部分
            if 'PAPER SESSIONS' in line.upper():
                in_paper_sessions = True
                continue

            if not in_paper_sessions:
                continue

            # 匹配目录中的章节格式：数字 + 标题
            # 格式如: "1    Plenary - Invited Papers.........................8"
            match = re.match(r'^(\d+)\s+(.+?)\.{3,}', line)
            if match:
                chapter_num = int(match.group(1))
                title = match.group(2).strip()

                # 尝试提取页码（在点号后面）
                page_match = re.search(r'\.{3,}(\d+)$', line)
                if page_match:
                    next_start_page = int(page_match.group(1))

                chapters.append(Chapter(
                    title=title,
                    start_page=next_start_page,
                    end_page=total_pages,  # 会后续被更新
                    content="",
                    level=1
                ))
                current_chapter_num = chapter_num

        # 更新章节的结束页码
        for i in range(len(chapters) - 1):
            chapters[i].end_page = chapters[i + 1].start_page - 1

        # 过滤掉无效的章节（标题太短或包含无关内容）
        valid_chapters = []
        for ch in chapters:
            if len(ch.title) >= 3 and not any(k in ch.title.upper() for k in self.EXCLUDED_KEYWORDS):
                valid_chapters.append(ch)

        return valid_chapters

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
                    progress = 50 + ((i + 1) / total_chapters) * 50  # 拆分阶段占50%
                    progress_callback(progress, f"正在拆分: {chapter['title'][:40]}...", None)

                # 创建PDF writer
                writer = PdfWriter()
                start_page = chapter['start_page'] - 1  # 转为0-based
                end_page = chapter['end_page']

                for page_idx in range(start_page, end_page):
                    if page_idx < len(reader.pages):
                        writer.add_page(reader.pages[page_idx])

                # 生成文件名
                safe_title = re.sub(r'[^\w\s-]', '', chapter['title'])[:30].strip()
                filename = f"{i+1:02d}_{safe_title}.pdf"
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
            chapters = splitter.analyze_pdf(args.input, send_progress)

            # 发送最终结果
            result = {
                'type': 'complete',
                'chapters': [
                    {
                        'title': ch.title,
                        'start_page': ch.start_page,
                        'end_page': ch.end_page,
                        'level': ch.level
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
