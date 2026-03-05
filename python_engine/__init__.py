"""
PDF 拆分工具 - Python 引擎
"""

import os
import sys

# 设置模块搜索路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from llm_client import LLMClient
from chat_handler import ChatHandler
from bookmark_extractor import BookmarkExtractor
from pdf_extractor import PDFExtractor
from pdf_splitter import PDFSplitter
from chunk_analyzer import ChunkAnalyzer
from filename_generator import FilenameGenerator
from progress_reporter import ProgressReporter
from error_handler import ErrorHandler, PDFError
from main_processor import MainProcessor

__all__ = [
    'LLMClient',
    'ChatHandler',
    'BookmarkExtractor',
    'PDFExtractor',
    'PDFSplitter',
    'ChunkAnalyzer',
    'FilenameGenerator',
    'ProgressReporter',
    'ErrorHandler',
    'PDFError',
    'MainProcessor'
]
