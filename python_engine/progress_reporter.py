"""
进度报告器模块
推送进度事件到前端
"""

import time
from typing import Dict, Callable, List, Optional


class ProgressReporter:
    """进度报告器"""

    def __init__(self, send_callback: Optional[Callable] = None):
        """
        初始化进度报告器

        参数：
            send_callback: 发送进度到前端的回调函数
        """
        self.send = send_callback or self._default_callback
        self.start_time = time.time()
        self._reset_state()

    def _reset_state(self):
        """重置状态"""
        self.pages_analyzed = 0
        self.total_pages = 0
        self.chapters_detected = []
        self.files_created = []
        self.token_consumed = 0
        self.start_time = time.time()
        self.current_stage = 'idle'

    def reset(self):
        """重置报告器状态"""
        self._reset_state()

    def _default_callback(self, data: Dict):
        """默认回调函数（如果未提供）"""
        print(f"[Progress] {data}")

    def send_progress(self, data: Dict):
        """发送进度事件"""
        self.send(data)

    def _get_elapsed_time(self) -> float:
        """获取已运行时间（秒）"""
        return time.time() - self.start_time

    def _get_timestamp(self) -> int:
        """获取当前时间戳（毫秒）"""
        return int(time.time() * 1000)

    # ==================== 通用进度 ====================

    def report_progress(
        self,
        stage: str,
        progress: float,
        message: str,
        extra_data: Optional[Dict] = None
    ):
        """
        报告通用进度

        参数：
            stage: 当前阶段
            progress: 进度百分比 (0-100)
            message: 进度消息
            extra_data: 额外数据
        """
        self.current_stage = stage

        data = {
            'type': 'progress',
            'stage': stage,
            'progress': progress,
            'message': message,
            'elapsed_time': self._get_elapsed_time(),
            'timestamp': self._get_timestamp()
        }

        if extra_data:
            data.update(extra_data)

        self.send(data)

    def report_stage_start(self, stage: str, message: str):
        """报告阶段开始"""
        self.report_progress(stage, 0, message)

    def report_stage_complete(self, stage: str, message: str):
        """报告阶段完成"""
        self.report_progress(stage, 100, message)

    # ==================== 分析阶段 ====================

    def report_analysis_start(self, total_pages: int):
        """报告分析开始"""
        self.total_pages = total_pages
        self.current_stage = 'analyzing'
        self.report_stage_start('analyzing', f'开始分析PDF，共{total_pages}页')

    def report_page_analyzed(self, page_num: int):
        """报告分析到某页"""
        self.pages_analyzed = page_num

        # 计算进度
        progress = (page_num / self.total_pages * 100) if self.total_pages > 0 else 0

        self.report_progress(
            'analyzing',
            progress,
            f'已分析 {page_num}/{self.total_pages} 页'
        )

    def report_chunk_analyzed(self, chunk_id: int, chapters_found: int):
        """报告分析完一个块"""
        self.report_progress(
            'analyzing',
            (self.pages_analyzed / self.total_pages * 100) if self.total_pages > 0 else 0,
            f'分析块 {chunk_id} 完成，识别到 {chapters_found} 个章节'
        )

    def report_analysis_complete(self, chapters: List[Dict]):
        """报告分析完成"""
        self.chapters_detected = chapters
        self.current_stage = 'analysis_complete'

        self.send({
            'type': 'analysis_complete',
            'chapters': chapters,
            'count': len(chapters),
            'pages_analyzed': self.pages_analyzed,
            'total_pages': self.total_pages,
            'elapsed_time': self._get_elapsed_time(),
            'timestamp': self._get_timestamp()
        })

    # ==================== 分割阶段 ====================

    def report_split_start(self, total_files: int):
        """报告分割开始"""
        self.current_stage = 'splitting'
        self.report_stage_start('splitting', f'开始分割PDF，共{total_files}个文件')

    def report_file_created(self, filename: str, file_num: int, total_files: int):
        """报告创建一个文件"""
        progress = (file_num / total_files * 100) if total_files > 0 else 0

        self.report_progress(
            'splitting',
            progress,
            f'已创建 {file_num}/{total_files}: {filename}'
        )

    def report_split_complete(self, results: List[Dict]):
        """报告分割完成"""
        self.files_created = results
        self.current_stage = 'split_complete'

        total_size = sum(r.get('file_size', 0) for r in results)

        self.send({
            'type': 'split_complete',
            'results': results,
            'count': len(results),
            'total_size': total_size,
            'elapsed_time': self._get_elapsed_time(),
            'timestamp': self._get_timestamp()
        })

    # ==================== Token统计 ====================

    def report_token_consumed(self, tokens: int, details: Optional[Dict] = None):
        """报告Token消耗"""
        self.token_consumed += tokens

        data = {
            'type': 'token_consumed',
            'tokens': tokens,
            'total_tokens': self.token_consumed,
            'timestamp': self._get_timestamp()
        }

        if details:
            data['details'] = details

        self.send(data)

    # ==================== 错误报告 ====================

    def report_error(self, stage: str, error: str, error_type: str = 'error'):
        """报告错误"""
        self.send({
            'type': 'error',
            'stage': stage,
            'error': error,
            'error_type': error_type,
            'elapsed_time': self._get_elapsed_time(),
            'timestamp': self._get_timestamp()
        })

    def report_warning(self, stage: str, warning: str):
        """报告警告"""
        self.send({
            'type': 'warning',
            'stage': stage,
            'warning': warning,
            'elapsed_time': self._get_elapsed_time(),
            'timestamp': self._get_timestamp()
        })

    # ==================== 综合报告 ====================

    def report_summary(self):
        """报告综合进度"""
        self.send({
            'type': 'summary',
            'stage': self.current_stage,
            'pages_analyzed': self.pages_analyzed,
            'total_pages': self.total_pages,
            'chapters_detected': len(self.chapters_detected),
            'files_created': len(self.files_created),
            'token_consumed': self.token_consumed,
            'elapsed_time': self._get_elapsed_time(),
            'timestamp': self._get_timestamp()
        })

    # ==================== 辅助方法 ====================

    def update_total_pages(self, total_pages: int):
        """更新总页数"""
        self.total_pages = total_pages

    def add_chapters(self, chapters: List[Dict]):
        """添加检测到的章节"""
        self.chapters_detected.extend(chapters)

    def add_files(self, files: List[Dict]):
        """添加创建的文件"""
        self.files_created.extend(files)

    def add_tokens(self, tokens: int):
        """添加Token消耗"""
        self.token_consumed += tokens
