"""
LLM 提示词模板模块
定义所有LLM调用的提示词模板
"""
import json

# ==================== 系统提示词 ====================

SYSTEM_CHAT_HANDLER = """
你是PDF拆分规则专家。你的任务是与用户沟通，理解他们的拆分需求，并生成结构化的拆分规则。

工作流程：
1. 仔细阅读用户的描述（文字、文档或图片）
2. 如果描述不清晰，主动提问澄清
3. 总结你的理解，让用户确认
4. 生成精确的结构化规则

常见拆分类型：
- 学术会议论文（SESSION / PAPER）
- 技术手册（Chapter / Section）
- 法律文档（Article / Clause）
- 教材（Unit / Lesson）

规则格式：
- 使用正则表达式匹配章节标题
- 支持层级结构
- 可以指定包含/排除的页面类型

记住：你的理解越准确，拆分效果越好。不确定时一定要问！
"""

SYSTEM_ANALYZE_REQUIREMENT = """
你是PDF拆分专家。你的任务是分析用户的拆分需求，判断能否通过书签简单解决，如果不行则需要通过LLM全文分析。

判断逻辑：
1. 如果用户想要"按章节拆分"、"按目录拆分"、"按SESSION拆分"等标准需求 → 优先用书签
2. 如果用户有特殊要求（"只提取包含某关键词的章节"、"拆分特定范围"等） → 需要LLM分析

返回JSON格式：
{
  "can_use_bookmark": true/false,
  "reason": "判断原因",
  "requires_llm_analysis": true/false,
  "llm_analysis_type": "chunk_analysis" | "full_analysis"
}
"""

SYSTEM_CHUNK_ANALYZER = """
你是PDF拆分专家。你的任务是识别PDF中的章节边界，确保拆分准确。

核心要求：
1. 检查重叠区是否有前一个章节的延续
2. 如果有延续，确定章节的准确结束页
3. 如果开始新章节，识别章节标题和起始页
4. 确保不把一个章节错误地拆分成两个

会话(SESSION)标题格式（ISSCC会议）：
- 格式：ISSCC 2026 / SESSION X / [SESSION_NAME]
- 示例：ISSCC 2026 / SESSION 1 / PLENARY
- 示例：ISSCC 2026 / SESSION 2 / PROCESSORS
- 示例：ISSCC 2026 / SESSION 3 / WEARABLE AND WIRELESS BIOMEDICAL SYSTEMS
- 注意：标题出现在每个会话的第一页开头
- 重要：每个会话的多个页面都会有相同的标题（作为页眉），只报告每个SESSION编号的第一次出现

判断依据：
- 章节标题：独立成行、字号较大、有编号
- 内容连贯性：延续的内容通常无明显的章节标题
- 章节编号变化：SESSION 1 → SESSION 2 → SESSION 3
- 章节边界：通常有明确的开始标记

返回JSON格式：
{
  "continuation": {
    "has_continuation": true/false,
    "previous_chapter": "SESSION 1",
    "end_page": 120
  },
  "new_chapters": [
    {
      "title": "SESSION 2 - PROCESSORS",
      "start_page": 44,
      "end_page": 75,
      "filename": "Session_2_Processors.pdf",
      "confidence": 0.95,
      "reason": "第44页开始SESSION 2标题"
    }
  ]
}

注意：
- 页码必须准确
- 范围不能重叠
- 必须覆盖用户要求的所有内容
- 只报告每个SESSION编号的第一次出现（不要报告重复的页眉）
"""

SYSTEM_FILENAME_GENERATOR = """
你是文件名生成专家。你的任务是根据用户需求，为识别到的章节生成文件名。

规则：
1. 文件名只包含英文、数字、下划线、连字符
2. 避免特殊字符（/\\:*?"<>|）
3. 保持可读性和语义清晰
4. 文件名不要太长（建议100字符以内）

常见命名模式：
- "Chapter 1" → "01_Chapter_1.pdf"
- "SESSION 1 - Analog Design" → "Session_1_Analog_Design.pdf"
- "1.1 Power Management" → "1.1_Power_Management.pdf"

返回JSON格式：
{
  "filenames": [
    {
      "chapter_title": "Chapter 1",
      "filename": "01_Chapter_1.pdf",
      "reason": "根据用户要求：编号+标题"
    }
  ]
}
"""

# ==================== 用户提示词模板 ====================

def build_analyze_requirement_prompt(user_description: str, pdf_info: dict) -> str:
    """
    构建需求分析提示词
    """
    return f"""
用户拆分需求：
{user_description}

PDF信息：
- 文件路径：{pdf_info.get('path', 'N/A')}
- 总页数：{pdf_info.get('total_pages', 'N/A')}

请分析这个任务能否通过PDF书签解决：
- 如果用户想要"按章节拆分"、"按目录拆分" → 用书签
- 如果用户有特殊要求（"只提取包含某关键词的章节"等） → 用LLM分析

判断并返回JSON：
{{
  "can_use_bookmark": true/false,
  "reason": "判断原因",
  "requires_llm_analysis": true/false,
  "llm_analysis_type": "chunk_analysis" | "full_analysis"
}}
"""


def build_chunk_analysis_prompt(
    chunk_content: str,
    chunk_info: dict,
    previous_context: dict,
    user_requirement: str
) -> str:
    """
    构建分块分析提示词
    """
    # 处理 JSON 格式的 user_requirement，转换为自然语言描述
    try:
        import json
        parsed_requirement = json.loads(user_requirement)

        # 从 JSON 中提取关键信息并转换为自然语言
        requirement_description = ""

        if 'structure' in parsed_requirement:
            structures = parsed_requirement['structure']
            requirement_description += "识别的章节结构：\n"
            for struct in structures:
                name = struct.get('name', '章节')
                pattern = struct.get('pattern', '')
                description = struct.get('description', '')
                requirement_description += f"- {name}：{description}\n"
                if pattern and '正则' in pattern:
                    requirement_description += f"  重要：会话标题格式为 'ISSCC 2026 / SESSION X / [SESSION_NAME]'\n"
                    requirement_description += f"  例如：'ISSCC 2026 / SESSION 1 / PLENARY'\n"
                    requirement_description += f"  例如：'ISSCC 2026 / SESSION 2 / PROCESSORS'\n"

        if 'filters' in parsed_requirement:
            filters = parsed_requirement['filters']
            requirement_description += "\n页面过滤规则：\n"
            if filters.get('ignore_pages'):
                requirement_description += f"- 忽略页面：{', '.join(filters['ignore_pages'])}\n"
            if filters.get('include_pages'):
                requirement_description += f"- 包含页面：{', '.join(filters['include_pages'])}\n"

        if 'special_rules' in parsed_requirement:
            special_rules = parsed_requirement['special_rules']
            requirement_description += "\n特殊规则：\n"
            for rule in special_rules:
                requirement_description += f"- {rule}\n"

        # 使用处理后的描述而不是原始 JSON
        user_requirement_display = requirement_description
    except (json.JSONDecodeError, TypeError):
        # 如果不是 JSON 格式，直接使用原始内容
        user_requirement_display = user_requirement

    prompt = f"""
用户拆分需求：
{user_requirement_display}

当前块信息：
- 块编号：{chunk_info['id']}
- 读取范围：第{chunk_info['read_range'][0]}-{chunk_info['read_range'][1]}页
- 处理范围：第{chunk_info['process_range'][0]}-{chunk_info['process_range'][1]}页

"""

    if previous_context:
        prompt += f"""
前一个块的上下文信息：
- 最后一个章节："{previous_context.get('title', 'N/A')}"
- 结束页：{previous_context.get('end_page', 'N/A')}

注意：{previous_context.get('end_page')}-{chunk_info['read_range'][0]}是重叠区，
请检查这些页面是否是前一个章节的延续。
"""

    prompt += f"""
当前块内容（第{chunk_info['read_range'][0]}-{chunk_info['read_range'][1]}页）：
{chunk_content}

任务：
1. 检查重叠区是否有前一个章节的延续
2. 如果有延续，确定章节的结束页
3. 识别新章节的起始页和标题
4. 生成文件名（根据用户需求）

返回JSON：
{{
  "continuation": {{
    "has_continuation": true/false,
    "previous_chapter": "章节标题",
    "end_page": 页码
  }},
  "new_chapters": [
    {{
      "title": "章节标题",
      "start_page": 起始页码,
      "end_page": 结束页码,
      "filename": "文件名.pdf",
      "confidence": 置信度(0-1),
      "reason": "判断依据"
    }}
  ]
}}
"""

    return prompt


def build_filename_generation_prompt(
    chapters: list,
    user_rule: str = None
) -> str:
    """
    构建文件名生成提示词
    """
    prompt = f"""
识别到的章节：
"""

    for i, chapter in enumerate(chapters):
        prompt += f"""
{i+1}. 标题：{chapter.get('title', 'N/A')}
   起始页：{chapter.get('start_page', 'N/A')}
   结束页：{chapter.get('end_page', 'N/A')}
"""

    if user_rule:
        prompt += f"""
用户命名规则：{user_rule}

请根据用户要求生成文件名。
"""
    else:
        prompt += """
用户未指定命名规则，请生成合理的文件名。
建议格式：编号 + 下划线 + 标题（如：01_Chapter_1.pdf）
"""

    prompt += """
返回JSON：
{
  "filenames": [
    {
      "chapter_title": "章节标题",
      "filename": "文件名.pdf",
      "reason": "生成依据"
    }
  ]
}
"""

    return prompt


def build_chat_message_prompt(
    user_input: str,
    conversation_history: list = None
) -> str:
    """
    构建Chat对话提示词
    """
    prompt = f"""
用户的输入：
{user_input}

"""

    if conversation_history:
        prompt += f"""
对话历史：
"""
        for msg in conversation_history[-5:]:  # 最近5轮
            role = "用户" if msg.get('role') == 'user' else "助手"
            content = msg.get('content', '')
            prompt += f"{role}: {content}\n"

    prompt += """
请分析用户的输入，生成结构化的拆分规则。

返回JSON：
{
  "summary": "用自然语言总结你的理解",
  "rule": {
    "structure": [
      {
        "level": 0,
        "name": "章节名称",
        "pattern": "正则表达式",
        "description": "描述"
      }
    ],
    "filters": {
      "ignore_pages": ["扉页", "目录", "版权页"],
      "include_pages": ["参考文献", "附录"]
    },
    "special_rules": ["特殊处理规则"]
  },
  "needs_clarification": true/false,
  "questions": ["需要用户澄清的问题"]
}
"""

    return prompt
