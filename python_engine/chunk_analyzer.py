"""
分块分析引擎模块
核心的分块处理逻辑，包括跨块章节处理
"""

import os
import sys
from typing import Dict, List, Optional, Callable

# 设置模块搜索路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from pdf_extractor import PDFExtractor
from llm_client import LLMClient
from progress_reporter import ProgressReporter
from error_handler import ErrorHandler


class ChunkAnalyzer:
    """分块分析引擎"""

    def __init__(
        self,
        pdf_extractor: PDFExtractor,
        llm_client: LLMClient,
        progress_reporter: ProgressReporter,
        error_handler: ErrorHandler
    ):
        """
        初始化分块分析引擎

        参数：
            pdf_extractor: PDF提取器
            llm_client: LLM客户端
            progress_reporter: 进度报告器
            error_handler: 错误处理器
        """
        self.pdf_extractor = pdf_extractor
        self.llm_client = llm_client
        self.progress_reporter = progress_reporter
        self.error_handler = error_handler

    def calculate_chunks(
        self,
        total_pages: int,
        chunk_size: int = 100,
        overlap_size: int = 20
    ) -> List[Dict]:
        """
        计算分块策略

        参数：
            total_pages: 总页数
            chunk_size: 每块大小（页数）
            overlap_size: 重叠区大小（页数）

        返回：
            块列表：
            [
                {
                    'id': 0,
                    'read_range': (1, 100),
                    'process_range': (1, 100)
                },
                ...
            ]
        """
        chunks = []
        current_page = 1
        chunk_id = 0

        while current_page <= total_pages:
            # 读取范围（包含重叠）
            read_start = current_page
            read_end = min(current_page + chunk_size - 1, total_pages)

            # 实际处理范围（跳过重叠）
            if chunk_id == 0:
                process_start = current_page
            else:
                process_start = current_page + overlap_size

            process_end = read_end

            chunks.append({
                'id': chunk_id,
                'read_range': (read_start, read_end),
                'process_range': (process_start, process_end)
            })

            # 如果已经读到最后一页，退出循环
            if read_end == total_pages:
                break

            # 下一块的起始（重叠）
            current_page = read_end - overlap_size + 1
            chunk_id += 1

        return chunks

    def analyze_all_chunks(
        self,
        chunks: List[Dict],
        user_requirement: str,
        max_chars_per_page: int = 500
    ) -> List[Dict]:
        """
        分析所有块

        参数：
            chunks: 块列表
            user_requirement: 用户需求
            max_chars_per_page: 每页最大字符数

        返回：
            合并后的章节列表
        """
        all_chapters = []
        previous_chunk_end = None

        for i, chunk in enumerate(chunks):
            # 更新进度
            self.progress_reporter.report_progress(
                'analyzing',
                (i / len(chunks)) * 100,
                f'正在分析块 {i + 1}/{len(chunks)} (第{chunk["read_range"][0]}-{chunk["read_range"][1]}页)'
            )

            # 重试循环
            max_retries = 3
            retry_count = 0
            success = False

            while retry_count < max_retries and not success:
                try:
                    # 提取块内容
                    chunk_content = self.pdf_extractor.extract_for_llm(
                        chunk,
                        max_chars_per_page
                    )

                    # 分析当前块
                    result = self.analyze_single_chunk(
                        chunk,
                        chunk_content,
                        previous_chunk_end,
                        user_requirement
                    )

                    # 处理延续章节
                    if result.get('continuation', {}).get('has_continuation'):
                        continuation = result['continuation']
                        if all_chapters:
                            # 找到上一个章节，更新结束页
                            all_chapters[-1]['end_page'] = continuation.get('end_page')

                    # 添加新章节
                    new_chapters = result.get('new_chapters', [])

                    # 规范化章节数据，确保所有必需字段都存在
                    normalized_chapters = []
                    for chapter in new_chapters:
                        normalized = {
                            'title': chapter.get('title', 'Unknown'),
                            'start_page': chapter.get('start_page', 0),
                            'end_page': chapter.get('end_page', 0),
                            'filename': chapter.get('filename', f"chapter_{len(all_chapters) + len(normalized_chapters)}.pdf"),
                            'level': chapter.get('level', 0),
                            'confidence': chapter.get('confidence', 0.0),
                            'reason': chapter.get('reason', '')
                        }
                        normalized_chapters.append(normalized)

                    all_chapters.extend(normalized_chapters)

                    # 保存当前块的上下文
                    if new_chapters:
                        previous_chunk_end = {
                            'title': new_chapters[-1]['title'],
                            'end_page': new_chapters[-1]['end_page']
                        }

                    # 成功处理，跳出重试循环
                    success = True

                except Exception as e:
                    # 错误处理
                    handle_result = self.error_handler.handle_error(
                        e,
                        {'chunk_id': chunk['id']}
                    )

                    if handle_result['action'] == 'retry':
                        retry_count += 1
                        if retry_count >= max_retries:
                            # 达到最大重试次数，跳过当前块
                            break
                        # continue 会在 while 循环中重试
                        continue
                    elif handle_result['action'] == 'skip':
                        # 跳过当前块，跳出重试循环
                        break
                    else:
                        # 中断处理
                        raise

        return all_chapters

    def analyze_single_chunk(
        self,
        chunk_info: Dict,
        chunk_content: str,
        previous_context: Optional[Dict],
        user_requirement: str
    ) -> Dict:
        """
        分析单个块

        参数：
            chunk_info: 块信息
            chunk_content: 块内容
            previous_context: 前一个块的上下文
            user_requirement: 用户需求

        返回：
            {
                'continuation': {...},
                'new_chapters': [...]
            }
        """
        # 调用LLM分析
        result = self.llm_client.analyze_chunk(
            chunk_content,
            chunk_info,
            previous_context,
            user_requirement,
            lambda msg: self.progress_reporter.report_progress(
                'analyzing',
                (chunk_info['id'] / 10) * 100,  # 估算进度
                msg
            )
        )

        # 验证结果
        validated = self._validate_chunk_result(result, chunk_info)

        return validated

    def _validate_chunk_result(
        self,
        result: Dict,
        chunk_info: Dict
    ) -> Dict:
        """
        验证块分析结果

        参数：
            result: LLM返回的结果
            chunk_info: 块信息

        返回：
            验证后的结果
        """
        # 验证延续信息
        continuation = result.get('continuation', {})
        if continuation.get('has_continuation'):
            end_page = continuation.get('end_page')
            read_start, read_end = chunk_info['read_range']

            # 检查页码是否在范围内
            if end_page and (end_page < read_start or end_page > read_end):
                # 页码超出范围，移除延续信息
                continuation['has_continuation'] = False

        # 验证新章节
        new_chapters = result.get('new_chapters', [])
        validated_chapters = []

        for chapter in new_chapters:
            start_page = chapter.get('start_page')
            end_page = chapter.get('end_page')
            read_start, read_end = chunk_info['read_range']

            # 检查页码范围
            if start_page and (start_page < read_start or start_page > read_end):
                continue  # 起始页超出范围，跳过

            if end_page and end_page > read_end:
                # 结束页超出范围，截断
                chapter['end_page'] = read_end

            # 检查逻辑
            if start_page and end_page and start_page > end_page:
                continue  # 起始页大于结束页，跳过

            validated_chapters.append(chapter)

        result['new_chapters'] = validated_chapters

        return result

    def merge_chapters(
        self,
        chapters: List[Dict]
    ) -> List[Dict]:
        """
        合并章节，处理连续的章节

        参数：
            chapters: 章节列表

        返回：
            合并后的章节列表
        """
        if not chapters:
            return []

        # 按页码排序
        chapters.sort(key=lambda x: x['start_page'])

        merged = []

        for chapter in chapters:
            if not merged:
                merged.append(chapter)
                continue

            last = merged[-1]

            # 检查是否连续
            if chapter['start_page'] == last['end_page'] + 1:
                # 连续，合并标题
                last['title'] = f"{last['title']} & {chapter['title']}"
                last['end_page'] = chapter['end_page']
                last['filename'] = self._merge_filenames(
                    last['filename'],
                    chapter['filename']
                )
            else:
                # 不连续，直接添加
                merged.append(chapter)

        return merged

    def _merge_filenames(self, filename1: str, filename2: str) -> str:
        """合并文件名"""
        # 移除扩展名
        name1 = filename1.replace('.pdf', '')
        name2 = filename2.replace('.pdf', '')

        # 合并
        merged = f"{name1}_{name2}"

        return f"{merged}.pdf"

    def detect_cross_chunk_issues(
        self,
        chapters: List[Dict],
        total_pages: int
    ) -> List[str]:
        """
        检测跨块问题

        参数：
            chapters: 章节列表
            total_pages: 总页数

        返回：
            问题列表
        """
        issues = []

        # 检查页码重叠
        for i in range(len(chapters) - 1):
            current = chapters[i]
            next_chapter = chapters[i + 1]

            if current['end_page'] >= next_chapter['start_page']:
                issues.append(
                    f"页码重叠: {current['title']} ({current['start_page']}-{current['end_page']}) "
                    f"和 {next_chapter['title']} ({next_chapter['start_page']}-{next_chapter['end_page']})"
                )

        # 检查页码空缺
        for i in range(len(chapters) - 1):
            current = chapters[i]
            next_chapter = chapters[i + 1]

            gap = next_chapter['start_page'] - current['end_page'] - 1
            if gap > 5:  # 空缺超过5页
                issues.append(
                    f"页码空缺: {current['title']} 和 {next_chapter['title']} 之间有 {gap} 页未分配"
                )

        # 检查是否覆盖所有页
        if chapters:
            first_start = chapters[0]['start_page']
            last_end = chapters[-1]['end_page']

            if first_start > 1:
                issues.append(f"前 {first_start - 1} 页未包含在任何章节中")

            if last_end < total_pages:
                issues.append(f"后 {total_pages - last_end} 页未包含在任何章节中")

        return issues

    def validate_final_result(
        self,
        chapters: List[Dict],
        total_pages: int
    ) -> Dict:
        """
        验证最终结果

        参数：
            chapters: 章节列表
            total_pages: 总页数

        返回：
            {
                'valid': True/False,
                'issues': [...],
                'warnings': [...]
            }
        """
        issues = self.detect_cross_chunk_issues(chapters, total_pages)

        # 检查章节数量
        if not chapters:
            return {
                'valid': False,
                'issues': ['未检测到任何章节'],
                'warnings': []
            }

        # 检查异常章节
        warnings = []
        for chapter in chapters:
            page_count = chapter['end_page'] - chapter['start_page'] + 1

            # 太短（可能是误检）
            if page_count < 3:
                warnings.append(
                    f"章节过短: {chapter['title']} 只有 {page_count} 页"
                )

            # 太长（可能是多个章节合并）
            if page_count > 200:
                warnings.append(
                    f"章节过长: {chapter['title']} 有 {page_count} 页，可能包含多个章节"
                )

        valid = len(issues) == 0

        return {
            'valid': valid,
            'issues': issues,
            'warnings': warnings
        }
