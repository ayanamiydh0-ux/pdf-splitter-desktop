"""
错误处理器模块
统一错误处理和恢复机制
"""

from typing import Dict, List, Optional, Callable
from enum import Enum


class ErrorPriority(Enum):
    """错误优先级"""
    P1 = "critical"      # 阻断性，必须立即处理
    P2 = "high"          # 高优先级，影响结果质量
    P3 = "medium"        # 中优先级，可容忍
    P4 = "low"           # 低优先级，边缘情况


class ErrorCategory(Enum):
    """错误类别"""
    API_CONNECTION = "api_connection"
    API_QUOTA = "api_quota"
    API_TIMEOUT = "api_timeout"
    PDF_READ = "pdf_read"
    PDF_INVALID = "pdf_invalid"
    TOKEN_LIMIT = "token_limit"
    CHUNK_SPLIT = "chunk_split"
    PAGE_OVERLAP = "page_overlap"
    USER_MISUNDERSTANDING = "user_misunderstanding"
    VALIDATION_FAILED = "validation_failed"
    FILENAME_CONFLICT = "filename_conflict"
    FILENAME_INVALID = "filename_invalid"
    CHUNK_CONSISTENCY = "chunk_consistency"
    LLM_NO_STRUCTURE = "llm_no_structure"
    USER_CANCELLED = "user_cancelled"
    UNKNOWN = "unknown"


class PDFError(Exception):
    """PDF错误基类"""
    def __init__(self, message: str, category: ErrorCategory, priority: ErrorPriority):
        self.message = message
        self.category = category
        self.priority = priority
        super().__init__(self.message)


class APIConnectionError(PDFError):
    """API连接错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.API_CONNECTION, ErrorPriority.P1)


class APIQuotaError(PDFError):
    """API配额不足错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.API_QUOTA, ErrorPriority.P1)


class APITimeoutError(PDFError):
    """API超时错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.API_TIMEOUT, ErrorPriority.P1)


class PDFReadError(PDFError):
    """PDF读取错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.PDF_READ, ErrorPriority.P1)


class PDFInvalidError(PDFError):
    """PDF无效错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.PDF_INVALID, ErrorPriority.P1)


class TokenLimitError(PDFError):
    """Token超限错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.TOKEN_LIMIT, ErrorPriority.P1)


class ChunkSplitError(PDFError):
    """块分割错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.CHUNK_SPLIT, ErrorPriority.P2)


class PageOverlapError(PDFError):
    """页码重叠错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.PAGE_OVERLAP, ErrorPriority.P2)


class UserUnderstandingError(PDFError):
    """用户需求理解错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.USER_MISUNDERSTANDING, ErrorPriority.P2)


class ValidationError(PDFError):
    """验证失败错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.VALIDATION_FAILED, ErrorPriority.P2)


class FilenameConflictError(PDFError):
    """文件名冲突错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.FILENAME_CONFLICT, ErrorPriority.P3)


class FilenameInvalidError(PDFError):
    """文件名非法错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.FILENAME_INVALID, ErrorPriority.P3)


class ChunkConsistencyError(PDFError):
    """跨块一致性错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.CHUNK_CONSISTENCY, ErrorPriority.P3)


class LLMNoStructureError(PDFError):
    """LLM无法识别结构错误"""
    def __init__(self, message: str):
        super().__init__(message, ErrorCategory.LLM_NO_STRUCTURE, ErrorPriority.P3)


class UserCancelledError(PDFError):
    """用户取消错误"""
    def __init__(self, message: str = "用户取消了操作"):
        super().__init__(message, ErrorCategory.USER_CANCELLED, ErrorPriority.P3)


class ErrorHandler:
    """错误处理器"""

    def __init__(
        self,
        progress_callback: Optional[Callable] = None,
        user_callback: Optional[Callable] = None
    ):
        """
        初始化错误处理器

        参数：
            progress_callback: 进度回调函数
            user_callback: 用户交互回调函数
        """
        self.progress_callback = progress_callback
        self.user_callback = user_callback
        self.recovery_attempts = {}
        self.max_attempts = 3

    def handle_error(
        self,
        error: Exception,
        context: Optional[Dict] = None
    ) -> Dict:
        """
        处理错误

        参数：
            error: 异常对象
            context: 错误上下文信息

        返回：
            处理结果：
            {
                'action': 'retry' | 'skip' | 'abort' | 'manual_intervention',
                'message': '处理消息',
                'should_continue': True/False
            }
        """
        # 如果是PDFError，直接处理
        if isinstance(error, PDFError):
            return self._handle_pdf_error(error, context)

        # 如果是其他异常，转换为PDFError
        pdf_error = self._convert_to_pdf_error(error)
        return self._handle_pdf_error(pdf_error, context)

    def _convert_to_pdf_error(self, error: Exception) -> PDFError:
        """将普通异常转换为PDFError"""
        error_msg = str(error)
        error_type = type(error).__name__

        # 根据错误消息判断类型
        if 'connection' in error_msg.lower():
            return APIConnectionError(error_msg)
        elif 'quota' in error_msg.lower() or 'insufficient' in error_msg.lower():
            return APIQuotaError(error_msg)
        elif 'timeout' in error_msg.lower():
            return APITimeoutError(error_msg)
        elif 'token' in error_msg.lower() and 'limit' in error_msg.lower():
            return TokenLimitError(error_msg)
        else:
            return PDFError(error_msg, ErrorCategory.UNKNOWN, ErrorPriority.P4)

    def _handle_pdf_error(
        self,
        error: PDFError,
        context: Optional[Dict]
    ) -> Dict:
        """处理PDFError"""
        error_key = f"{error.category.value}_{context.get('chunk_id', '0')}"

        # 检查重试次数
        attempts = self.recovery_attempts.get(error_key, 0)

        # 根据优先级处理
        if error.priority == ErrorPriority.P1:
            return self._handle_critical_error(error, attempts, error_key, context)
        elif error.priority == ErrorPriority.P2:
            return self._handle_high_priority_error(error, attempts, error_key, context)
        elif error.priority == ErrorPriority.P3:
            return self._handle_medium_priority_error(error, context)
        else:
            return self._handle_low_priority_error(error, context)

    def _handle_critical_error(
        self,
        error: PDFError,
        attempts: int,
        error_key: str,
        context: Optional[Dict]
    ) -> Dict:
        """处理阻断性错误"""
        # API连接/配额/超时错误
        if error.category in [
            ErrorCategory.API_CONNECTION,
            ErrorCategory.API_QUOTA,
            ErrorCategory.API_TIMEOUT
        ]:
            if attempts < self.max_attempts:
                # 自动重试
                self.recovery_attempts[error_key] = attempts + 1

                return {
                    'action': 'retry',
                    'message': f'{error.message}，正在重试 ({attempts + 1}/{self.max_attempts})...',
                    'should_continue': True,
                    'delay': 2 * (attempts + 1)  # 指数退避
                }

        # PDF读取/无效错误
        if error.category in [ErrorCategory.PDF_READ, ErrorCategory.PDF_INVALID]:
            return {
                'action': 'abort',
                'message': f'PDF文件错误: {error.message}，请检查文件',
                'should_continue': False
            }

        # Token超限错误
        if error.category == ErrorCategory.TOKEN_LIMIT:
            return {
                'action': 'abort',
                'message': f'Token超限: {error.message}，请调整分块大小',
                'should_continue': False
            }

        return {
            'action': 'abort',
            'message': f'严重错误: {error.message}',
            'should_continue': False
        }

    def _handle_high_priority_error(
        self,
        error: PDFError,
        attempts: int,
        error_key: str,
        context: Optional[Dict]
    ) -> Dict:
        """处理高优先级错误"""
        # 块分割/页码重叠错误
        if error.category in [ErrorCategory.CHUNK_SPLIT, ErrorCategory.PAGE_OVERLAP]:
            if attempts < 2:
                # 自动重试
                self.recovery_attempts[error_key] = attempts + 1

                return {
                    'action': 'retry',
                    'message': f'检测到页码问题，正在重新分析 ({attempts + 1}/2)...',
                    'should_continue': True
                }
            else:
                # 需要用户确认
                return {
                    'action': 'manual_intervention',
                    'message': f'页码问题无法自动修复: {error.message}',
                    'should_continue': False,
                    'requires_confirmation': True
                }

        # 用户需求理解/验证失败错误
        if error.category in [
            ErrorCategory.USER_MISUNDERSTANDING,
            ErrorCategory.VALIDATION_FAILED
        ]:
            return {
                'action': 'manual_intervention',
                'message': f'分析结果可能有误: {error.message}，请确认',
                'should_continue': False,
                'requires_confirmation': True
            }

        return {
            'action': 'skip',
            'message': f'跳过错误: {error.message}',
            'should_continue': True
        }

    def _handle_medium_priority_error(
        self,
        error: PDFError,
        context: Optional[Dict]
    ) -> Dict:
        """处理中优先级错误"""
        # 文件名冲突/非法错误 - 自动修正
        if error.category in [
            ErrorCategory.FILENAME_CONFLICT,
            ErrorCategory.FILENAME_INVALID
        ]:
            return {
                'action': 'skip',
                'message': f'文件名问题已自动修正',
                'should_continue': True
            }

        # 跨块一致性错误 - 重试
        if error.category == ErrorCategory.CHUNK_CONSISTENCY:
            return {
                'action': 'retry',
                'message': '检测到跨块一致性问题，正在重新分析...',
                'should_continue': True
            }

        # LLM无法识别结构
        if error.category == ErrorCategory.LLM_NO_STRUCTURE:
            return {
                'action': 'skip',
                'message': '无法识别PDF结构，建议使用书签拆分',
                'should_continue': True
            }

        return {
            'action': 'skip',
            'message': f'已忽略: {error.message}',
            'should_continue': True
        }

    def _handle_low_priority_error(
        self,
        error: PDFError,
        context: Optional[Dict]
    ) -> Dict:
        """处理低优先级错误"""
        # 用户取消
        if error.category == ErrorCategory.USER_CANCELLED:
            return {
                'action': 'abort',
                'message': '操作已取消',
                'should_continue': False
            }

        # 未知错误
        return {
            'action': 'skip',
            'message': f'未知错误: {error.message}',
            'should_continue': True
        }

    def report_error(self, error: Exception, context: Optional[Dict] = None):
        """报告错误到进度回调"""
        if self.progress_callback:
            self.progress_callback({
                'type': 'error',
                'error': str(error),
                'error_type': type(error).__name__,
                'context': context or {}
            })
