"""
LLM 客户端模块
支持OpenAI格式的LLM API调用，兼容Kimi、GLM、DeepSeek等服务商
"""

import json
import os
import sys
from typing import Dict, List, Optional, Callable

# 设置模块搜索路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from openai import OpenAI
from prompt_templates import (
    SYSTEM_CHAT_HANDLER,
    SYSTEM_ANALYZE_REQUIREMENT,
    SYSTEM_CHUNK_ANALYZER,
    SYSTEM_FILENAME_GENERATOR,
    build_analyze_requirement_prompt,
    build_chunk_analysis_prompt,
    build_filename_generation_prompt,
    build_chat_message_prompt
)


class LLMClient:
    """LLM客户端，支持OpenAI格式API"""

    # 预设服务商配置
    PRESETS = {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4"
        },
        "kimi": {
            "base_url": "https://api.moonshot.cn/v1",
            "model": "moonshot-v1-8k"
        },
        "glm": {
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4"
        },
        "glm-coding": {
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "model": "glm-4-flashx"
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat"
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "model": "llama3"
        }
    }

    def __init__(self, config: Dict):
        """
        初始化LLM客户端

        参数：
            config: {
                "api_key": "sk-xxx",
                "preset": "kimi",  # 可选，使用预设配置
                "base_url": "...",  # 可选，自定义URL
                "model": "...",     # 可选，自定义模型
            }
        """
        self.config = config
        self.api_key = config.get("api_key", "")

        # 确定base_url和model
        if config.get("preset") in self.PRESETS:
            preset = self.PRESETS[config["preset"]]
            self.base_url = config.get("base_url") or preset["base_url"]
            self.model = config.get("model") or preset["model"]
        else:
            self.base_url = config.get("base_url")
            self.model = config.get("model")

        # 初始化OpenAI客户端
        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=60.0  # 默认60秒超时
            )
        except Exception as e:
            raise ConnectionError(f"无法初始化LLM客户端: {e}")

    def test_connection(self) -> Dict:
        """
        测试连接是否正常

        返回：
            {
                "success": true/false,
                "message": "测试结果",
                "response": "模型返回的内容"
            }
        """
        try:
            # 发送一个简单的测试请求，不要求JSON格式
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": "请简单回复'连接成功'"}
                ],
                max_tokens=10
            )
            response_text = response.choices[0].message.content
            return {
                "success": True,
                "message": "连接成功",
                "response": response_text
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"连接测试失败: {str(e)}",
                "response": None
            }

    def chat(
        self,
        messages: List[Dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
        stream: bool = False
    ) -> str:
        """
        发送聊天请求

        参数：
            messages: 消息列表，格式 [{"role": "user", "content": "..."}]
            temperature: 温度参数 (0-2)，越高越随机
            max_tokens: 最大生成token数
            response_format: 响应格式，如 {"type": "json_object"}
            stream: 是否流式输出

        返回：
            响应内容
        """
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature
            }

            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            if response_format:
                kwargs["response_format"] = response_format

            if stream:
                kwargs["stream"] = stream

            response = self.client.chat.completions.create(**kwargs)

            # 返回内容
            if stream:
                return response  # 流式响应
            else:
                return response.choices[0].message.content

        except Exception as e:
            raise RuntimeError(f"LLM调用失败: {e}")

    def analyze_requirement(
        self,
        user_description: str,
        pdf_info: Dict
    ) -> Dict:
        """
        分析用户需求，判断使用书签还是LLM

        返回：
            {
                "can_use_bookmark": true/false,
                "reason": "...",
                "requires_llm_analysis": true/false,
                "llm_analysis_type": "chunk_analysis" | "full_analysis"
            }
        """
        from prompt_templates import (
            SYSTEM_ANALYZE_REQUIREMENT,
            build_analyze_requirement_prompt
        )

        prompt = build_analyze_requirement_prompt(user_description, pdf_info)

        response = self.chat(
            messages=[
                {"role": "system", "content": SYSTEM_ANALYZE_REQUIREMENT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        result = json.loads(response)
        return result

    def analyze_chunk(
        self,
        chunk_content: str,
        chunk_info: Dict,
        previous_context: Optional[Dict],
        user_requirement: str,
        progress_callback: Optional[Callable] = None
    ) -> Dict:
        """
        分析单个块，识别章节

        参数：
            chunk_content: 块的文本内容
            chunk_info: 块信息
            previous_context: 前一个块的上下文
            user_requirement: 用户需求
            progress_callback: 进度回调函数

        返回：
            {
                "continuation": {...},
                "new_chapters": [...]
            }
        """
        from prompt_templates import (
            SYSTEM_CHUNK_ANALYZER,
            build_chunk_analysis_prompt
        )

        prompt = build_chunk_analysis_prompt(
            chunk_content,
            chunk_info,
            previous_context,
            user_requirement
        )

        if progress_callback:
            progress_callback(
                f"正在分析第{chunk_info['id']}块（第{chunk_info['read_range'][0]}-{chunk_info['read_range'][1]}页）..."
            )
            progress_callback(
                f"步骤 A: 准备 LLM 提示词（{len(prompt)} 字符）"
            )

        if progress_callback:
            progress_callback(
                f"步骤 B: 调用 LLM API..."
            )

        response = self.chat(
            messages=[
                {"role": "system", "content": SYSTEM_CHUNK_ANALYZER},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )

        if progress_callback:
            progress_callback(
                f"步骤 C: 解析 LLM 响应..."
            )

        result = json.loads(response)

        if progress_callback:
            progress_callback(
                f"第{chunk_info['id']}块分析完成，识别到{len(result.get('new_chapters', []))}个章节"
            )

        return result

    def generate_filename(
        self,
        chapters: List[Dict],
        user_rule: Optional[str] = None
    ) -> List[Dict]:
        """
        为章节生成文件名

        返回：
            [
                {
                    "chapter_title": "...",
                    "filename": "...",
                    "reason": "..."
                },
                ...
            ]
        """
        from prompt_templates import (
            SYSTEM_FILENAME_GENERATOR,
            build_filename_generation_prompt
        )

        prompt = build_filename_generation_prompt(chapters, user_rule)

        response = self.chat(
            messages=[
                {"role": "system", "content": SYSTEM_FILENAME_GENERATOR},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        result = json.loads(response)
        return result.get("filenames", [])

    def process_chat_message(
        self,
        user_input: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict:
        """
        处理Chat消息

        返回：
            {
                "summary": "...",
                "rule": {...},
                "needs_clarification": true/false,
                "questions": [...]
            }
        """
        from prompt_templates import (
            SYSTEM_CHAT_HANDLER,
            build_chat_message_prompt
        )

        prompt = build_chat_message_prompt(user_input, conversation_history)

        response = self.chat(
            messages=[
                {"role": "system", "content": SYSTEM_CHAT_HANDLER},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            response_format={"type": "json_object"}
        )

        result = json.loads(response)
        return result


class LLMError(Exception):
    """LLM错误基类"""
    pass


class LLMConnectionError(LLMError):
    """LLM连接错误"""
    pass


class LLMQuotaError(LLMError):
    """LLM配额不足错误"""
    pass


class LLMTimeoutError(LLMError):
    """LLM超时错误"""
    pass
