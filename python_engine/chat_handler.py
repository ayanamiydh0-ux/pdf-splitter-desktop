"""
Chat 处理器模块
处理用户通过Chat输入的拆分需求
"""

import json
import os
import sys
from typing import Dict, List, Optional

# 设置模块搜索路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from llm_client import LLMClient


class ChatHandler:
    """Chat消息处理器"""

    def __init__(self, llm_client: LLMClient):
        """
        初始化Chat处理器

        参数：
            llm_client: LLM客户端实例
        """
        self.llm_client = llm_client
        self.conversation_history = []
        self.extracted_rule = None

    def process_message(
        self,
        message: Dict,
        progress_callback: Optional[callable] = None
    ) -> Dict:
        """
        处理用户消息

        参数：
            message: {
                'type': 'text' | 'image' | 'markdown',
                'content': str | bytes,
                'metadata': dict
            }
            progress_callback: 进度回调函数

        返回：
            {
                'response': str,              # 助手回复
                'extracted_rule': dict,      # 提取的规则
                'needs_clarification': bool, # 是否需要澄清
                'clarification_questions': list
            }
        """
        try:
            # 1. 提取内容
            if progress_callback:
                progress_callback("步骤 1: 提取消息内容...")
            extracted_content = self._extract_content(message)

            if progress_callback:
                progress_callback("步骤 2: 正在理解你的需求...")

            # 2. 添加到对话历史
            self.conversation_history.append({
                "role": "user",
                "content": extracted_content,
                "metadata": message.get("metadata", {})
            })

            # 3. 调用LLM处理
            if progress_callback:
                progress_callback("步骤 3: 调用 LLM API...")
            result = self.llm_client.process_chat_message(
                extracted_content,
                self.conversation_history[:-1]  # 不包括当前消息
            )

            # 4. 记录助手回复
            self.conversation_history.append({
                "role": "assistant",
                "content": result.get("summary", "")
            })

            # 5. 保存提取的规则
            self.extracted_rule = result.get("rule", {})

            if progress_callback:
                progress_callback("步骤 4: 需求理解完成")

            return {
                'response': result.get("summary", ""),
                'extracted_rule': self.extracted_rule,
                'needs_clarification': result.get("needs_clarification", False),
                'clarification_questions': result.get("questions", [])
            }

        except Exception as e:
            if progress_callback:
                progress_callback(f"处理失败: {str(e)}")
            raise

    def _extract_content(self, message: Dict) -> str:
        """
        从消息中提取文本内容

        参数：
            message: 消息对象

        返回：
            提取的文本内容
        """
        message_type = message.get('type', 'text')

        if message_type == 'text':
            return message.get('content', '')

        elif message_type == 'image':
            # TODO: 实现OCR
            return self._extract_text_from_image(message.get('content'))

        elif message_type == 'markdown':
            return self._parse_markdown(message.get('content'))

        elif message_type == 'file':
            # 读取文件内容
            return self._read_file(message.get('content'))

        return ''

    def _extract_text_from_image(self, image_data: bytes) -> str:
        """
        从图片中提取文字（OCR）

        参数：
            image_data: 图片字节数据

        返回：
            提取的文本
        """
        # TODO: 集成OCR库（如pytesseract或EasyOCR）
        return f"[OCR] 图片内容提取功能待实现"

    def _parse_markdown(self, markdown_text: str) -> str:
        """
        解析Markdown文本

        参数：
            markdown_text: Markdown文本

        返回：
            解析后的纯文本
        """
        # 简单的Markdown解析
        lines = markdown_text.split('\n')
        parsed = []

        for line in lines:
            # 移除Markdown标记
            cleaned = line.lstrip('#').lstrip('-').lstrip('*').strip()
            if cleaned:
                parsed.append(cleaned)

        return '\n'.join(parsed)

    def _read_file(self, file_path: str) -> str:
        """
        读取文件内容

        参数：
            file_path: 文件路径

        返回：
            文件内容
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            return f"读取文件失败: {str(e)}"

    def clear_history(self):
        """清空对话历史"""
        self.conversation_history = []
        self.extracted_rule = None

    def get_conversation_history(self) -> List[Dict]:
        """获取对话历史"""
        return self.conversation_history

    def get_extracted_rule(self) -> Optional[Dict]:
        """获取提取的规则"""
        return self.extracted_rule

    def update_rule(self, rule: Dict):
        """
        更新提取的规则

        参数：
            rule: 新的规则
        """
        self.extracted_rule = rule
