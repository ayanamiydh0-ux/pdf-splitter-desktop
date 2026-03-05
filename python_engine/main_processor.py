"""
PDF 拆分工具 - 主处理器
协调所有模块的工作流程
"""

import json
import os
import sys
from typing import Dict, List, Optional, Callable

# 设置模块搜索路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from llm_client import LLMClient
from chat_handler import ChatHandler
from bookmark_extractor import BookmarkExtractor
from pdf_extractor import PDFExtractor
from chunk_analyzer import ChunkAnalyzer
from filename_generator import FilenameGenerator
from progress_reporter import ProgressReporter


class MainProcessor:
    """PDF拆分工具主处理器"""

    def __init__(
        self,
        llm_config: Optional[Dict] = None,
        chunk_size: int = 30,
        overlap_size: int = 10,
        send_callback: Optional[Callable] = None
    ):
        """
        初始化主处理器

        参数：
            llm_config: LLM配置
            chunk_size: 分块大小（页数）
            overlap_size: 重叠大小（页数）
            send_callback: 进度回调函数
        """
        self.llm_config = llm_config or {}
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size
        self.send_callback = send_callback

        # 初始化子模块
        self.llm_client = None
        if llm_config and llm_config.get('api_key'):
            try:
                self.llm_client = LLMClient(llm_config)
            except Exception as e:
                # 不在初始化时测试连接，避免阻塞
                self.llm_client = None

        self.chat_handler = None
        if self.llm_client:
            self.chat_handler = ChatHandler(self.llm_client)

        self.bookmark_extractor = None
        self.pdf_extractor = None
        self.chunk_analyzer = None
        self.filename_generator = FilenameGenerator()
        self.pdf_splitter = None
        self.progress_reporter = ProgressReporter(send_callback)

        # 当前处理状态
        self.current_pdf_path = None
        self.current_chapters = None

    def test_llm_connection(self) -> Dict:
        """
        测试LLM连接

        返回：
            {
                "success": true/false,
                "message": "测试结果",
                "response": "模型返回的内容"
            }
        """
        if not self.llm_config or not self.llm_config.get('api_key'):
            return {
                "success": False,
                "message": "未配置API密钥",
                "response": None
            }

        if not self.llm_client:
            try:
                self.llm_client = LLMClient(self.llm_config)
            except Exception as e:
                return {
                    "success": False,
                    "message": f"初始化失败: {str(e)}",
                    "response": None
                }

        return self.llm_client.test_connection()

    def process_chat_message(self, message: Dict) -> Dict:
        """
        处理Chat消息

        参数：
            message: {
                'type': 'text' | 'image' | 'markdown',
                'content': str | bytes,
                'metadata': dict
            }

        返回：
            {
                'response': str,
                'extracted_rule': dict,
                'needs_clarification': bool,
                'clarification_questions': list
            }
        """
        self.progress_reporter.send_progress("步骤 1/3: 初始化 LLM 客户端...")

        # 确保 ChatHandler 和 LLMClient 已初始化
        # 注意：每次调用都重新检查并初始化，而不是依赖之前的状态
        if not self.llm_client:
            return {
                'response': '请先配置LLM API Key',
                'extracted_rule': {},
                'needs_clarification': False,
                'clarification_questions': []
            }

        self.progress_reporter.send_progress("步骤 2/3: 初始化 Chat 处理器...")
        if not self.chat_handler and self.llm_client:
            from chat_handler import ChatHandler
            self.chat_handler = ChatHandler(self.llm_client)

        if not self.chat_handler:
            raise RuntimeError("未初始化Chat处理器，请先配置LLM")

        self.progress_reporter.send_progress("步骤 3/3: 调用 LLM API 处理消息...")

        return self.chat_handler.process_message(
            message,
            progress_callback=self.progress_reporter.send_progress
        )

    def analyze_pdf(
        self,
        file_path: str,
        user_requirement: str,
        user_naming_rule: Optional[str] = None
    ) -> Dict:
        """
        分析PDF文件

        参数：
            file_path: PDF文件路径
            user_requirement: 用户需求描述
            user_naming_rule: 用户命名规则（可选）

        返回：
            {
                'chapters': [...],
                'strategy': 'bookmark' | 'llm',
                'valid': bool,
                'issues': [...],
                'warnings': [...]
            }
        """
        # 更新进度
        self.progress_reporter.send_progress(
            "正在打开PDF文件..."
        )

        # 初始化提取器
        from pdf_extractor import PDFExtractor
        from filename_generator import FilenameGenerator
        from chunk_analyzer import ChunkAnalyzer
        from error_handler import ErrorHandler

        # 提取PDF信息
        self.current_pdf_path = file_path

        # PDFExtractor 需要每次创建新的实例
        self.progress_reporter.send_progress("步骤 1/5: 初始化 PDF 提取器...")
        self.pdf_extractor = PDFExtractor(file_path)

        # 获取总页数，设置 total_pages
        total_pages = self.pdf_extractor.get_total_pages()
        self.progress_reporter.report_analysis_start(total_pages)
        self.progress_reporter.send_progress(f"步骤 2/5: PDF 共 {total_pages} 页")

        # [DEBUG] 跳过书签提取，直接使用 LLM 分析
        self.progress_reporter.send_progress("步骤 3/5: 跳过书签提取，直接使用 LLM 分析")

        # 使用LLM分析
        if not self.llm_client:
            raise RuntimeError("未配置LLM，无法分析PDF")

        self.progress_reporter.send_progress("步骤 4/5: 使用 LLM 分析 PDF 结构...")

        # 初始化 ChunkAnalyzer
        self.progress_reporter.send_progress("步骤 4.1/5: 初始化分块分析器...")
        if not self.chunk_analyzer:
            error_handler = ErrorHandler(
                progress_callback=self.progress_reporter.send_progress
            )
            self.chunk_analyzer = ChunkAnalyzer(
                pdf_extractor=self.pdf_extractor,
                llm_client=self.llm_client,
                progress_reporter=self.progress_reporter,
                error_handler=error_handler
            )

        # 计算分块策略
        self.progress_reporter.send_progress("步骤 4.2/5: 计算分块策略...")
        total_pages = self.pdf_extractor.get_total_pages()
        chunks = self.chunk_analyzer.calculate_chunks(
            total_pages,
            chunk_size=self.chunk_size,
            overlap_size=self.overlap_size
        )
        self.progress_reporter.send_progress(f"步骤 4.3/5: 共 {len(chunks)} 个分块，开始分析...")

        # 分析每个块
        chapters = self.chunk_analyzer.analyze_all_chunks(
            chunks,
            user_requirement,
            max_chars_per_page=500
        )

        self.current_chapters = chapters

        # 发送分析完成消息（包含 chapters 数据）
        self.progress_reporter.report_analysis_complete(chapters)

        return {
            'chapters': chapters,
            'strategy': 'llm',
            'valid': True,
            'issues': [],
            'warnings': []
        }

    def split_pdf(
        self,
        output_dir: str,
        chapters: List[Dict],
        filename_template: Optional[str] = None
    ) -> List[Dict]:
        """
        分割PDF文件

        参数：
            output_dir: 输出目录
            chapters: 章节列表
            filename_template: 文件名模板（可选）

        返回：
            [
                {
                    'filename': '...',
                    'path': '...',
                    'page_count': 10,
                    'file_size': 12345,
                    'success': True,
                    'error': None
                },
                ...
            ]
        """
        if not self.current_pdf_path:
            raise RuntimeError("未加载PDF文件")

        self.progress_reporter.send_progress(f"步骤 1/3: 准备分割 PDF，共 {len(chapters)} 个章节...")

        # 确保PDFSplitter已初始化
        self.progress_reporter.send_progress("步骤 2/3: 初始化 PDF 分割器...")
        if not self.pdf_splitter:
            from pdf_splitter import PDFSplitter
            self.pdf_splitter = PDFSplitter(self.current_pdf_path)

        # 分割PDF
        self.progress_reporter.send_progress("步骤 3/3: 执行 PDF 分割...")
        results = self.pdf_splitter.split_by_chapters(
            chapters,
            output_dir,
            filename_template,
            progress_callback=self.progress_reporter.send_progress
        )

        self.progress_reporter.send_progress(f"分割完成！生成 {len(results)} 个文件")

        return results

    def export_analysis_result(self, output_path: str) -> bool:
        """
        导出分析结果

        参数：
            output_path: 输出文件路径

        返回：
            是否成功
        """
        if not self.current_chapters:
            return False

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'pdf_path': self.current_pdf_path,
                    'chapters': self.current_chapters
                }, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"导出失败: {e}")
            return False

    def import_analysis_result(self, input_path: str) -> bool:
        """
        导入分析结果

        参数：
            input_path: 输入文件路径

        返回：
            是否成功
        """
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.current_pdf_path = data.get('pdf_path')
                self.current_chapters = data.get('chapters')
            return True
        except Exception as e:
            print(f"导入失败: {e}")
            return False
