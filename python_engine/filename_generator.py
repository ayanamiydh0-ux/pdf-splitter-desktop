"""
文件名生成器模块
为拆分后的章节生成文件名
"""

import re
from typing import Dict, List, Optional


class FilenameGenerator:
    """文件名生成器"""

    # 非法字符映射
    INVALID_CHARS = {
        '/': '_',
        '\\\\': '_',
        ':': '_',
        '*': '_',
        '?': '',
        '"': '_',
        '<': '_',
        '>': '_',
        '|': '_',
        ' ': '_',  # 可选：空格转下划线
    }

    def __init__(self, user_rule: Optional[str] = None):
        """
        初始化文件名生成器

        参数：
            user_rule: 用户自定义命名规则
        """
        self.user_rule = user_rule

    def generate_filename(
        self,
        chapter_title: str,
        chapter_info: Optional[Dict] = None,
        llm_client: Optional[object] = None
    ) -> str:
        """
        为章节生成文件名

        参数：
            chapter_title: 章节标题
            chapter_info: 章节信息（可选）
            llm_client: LLM客户端（用于自定义规则）

        返回：
            文件名（不含扩展名）
        """
        if not chapter_title:
            return "untitled"

        # 如果有自定义规则，使用LLM生成
        if self.user_rule and llm_client:
            return self._generate_with_llm(chapter_title, chapter_info, llm_client)

        # 否则使用默认规则
        return self._generate_default(chapter_title, chapter_info)

    def generate_filenames(
        self,
        chapters: List[Dict],
        llm_client: Optional[object] = None
    ) -> List[Dict]:
        """
        批量生成文件名

        参数：
            chapters: 章节列表
            llm_client: LLM客户端

        返回：
            包含文件名的章节列表
        """
        if self.user_rule and llm_client:
            # 使用LLM批量生成
            return self._generate_batch_with_llm(chapters, llm_client)
        else:
            # 默认规则批量生成
            for chapter in chapters:
                chapter['filename'] = self.generate_filename(
                    chapter.get('title', ''),
                    chapter
                )
            return chapters

    def _generate_default(
        self,
        chapter_title: str,
        chapter_info: Optional[Dict] = None
    ) -> str:
        """
        使用默认规则生成文件名

        默认规则：编号 + 下划线 + 标题

        参数：
            chapter_title: 章节标题
            chapter_info: 章节信息

        返回：
            文件名
        """
        # 提取编号
        number = self._extract_number(chapter_title)

        # 提取标题部分（去除编号）
        title = self._extract_title_without_number(chapter_title)

        # 组合：编号 + 下划线 + 标题
        if number and title:
            filename = f"{number}_{title}"
        elif number:
            filename = number
        else:
            filename = title

        # 清理特殊字符
        filename = self._sanitize_filename(filename)

        return filename

    def _generate_with_llm(
        self,
        chapter_title: str,
        chapter_info: Optional[Dict],
        llm_client
    ) -> str:
        """
        使用LLM生成文件名

        参数：
            chapter_title: 章节标题
            chapter_info: 章节信息
            llm_client: LLM客户端

        返回：
            文件名
        """
        try:
            # 调用LLM生成
            result = llm_client.generate_filename(
                [chapter_info or {'title': chapter_title}],
                self.user_rule
            )

            if result and len(result) > 0:
                filename = result[0].get('filename', '')
                return self._sanitize_filename(filename)
        except Exception:
            # LLM失败，回退到默认规则
            pass

        return self._generate_default(chapter_title, chapter_info)

    def _generate_batch_with_llm(
        self,
        chapters: List[Dict],
        llm_client
    ) -> List[Dict]:
        """
        使用LLM批量生成文件名

        参数：
            chapters: 章节列表
            llm_client: LLM客户端

        返回：
            更新后的章节列表
        """
        try:
            # 调用LLM批量生成
            results = llm_client.generate_filename(chapters, self.user_rule)

            # 将结果应用到章节列表
            if len(results) == len(chapters):
                for i, chapter in enumerate(chapters):
                    chapter['filename'] = self._sanitize_filename(
                        results[i].get('filename', '')
                    )
            else:
                # 数量不匹配，使用默认规则
                for chapter in chapters:
                    chapter['filename'] = self.generate_filename(
                        chapter.get('title', ''),
                        chapter
                    )
        except Exception:
            # LLM失败，使用默认规则
            for chapter in chapters:
                chapter['filename'] = self.generate_filename(
                    chapter.get('title', ''),
                    chapter
                )

        return chapters

    def _sanitize_filename(self, filename: str) -> str:
        """
        清理文件名，移除非法字符

        参数：
            filename: 原始文件名

        返回：
            清理后的文件名
        """
        # 替换非法字符
        for invalid, replacement in self.INVALID_CHARS.items():
            filename = filename.replace(invalid, replacement)

        # 移除多余下划线
        while '__' in filename:
            filename = filename.replace('__', '_')

        # 移除首尾特殊字符
        filename = filename.strip('_-.')

        # 限制长度（避免文件名过长）
        if len(filename) > 100:
            filename = filename[:100]

        # 如果处理后为空，使用默认名称
        if not filename:
            filename = "untitled"

        return filename

    def _extract_number(self, text: str) -> str:
        """
        从文本中提取编号

        参数：
            text: 文本

        返回：
            编号字符串
        """
        # 尝试匹配各种编号格式
        patterns = [
            r'^(\d+(?:\.\d+)*)',         # 1, 1.1, 1.1.1
            r'^Chapter\s+(\d+)',         # Chapter 1
            r'^SESSION\s+(\d+)',         # SESSION 1
            r'^PAPER\s+(\d+(?:\.\d+)*)', # PAPER 1.1.1
            r'^Section\s+(\d+(?:\.\d+)*)',# Section 1.1
            r'^([IVX]+)',                # I, II, III, IV
        ]

        for pattern in patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                number = match.group(1)
                # 转换罗马数字
                if re.match(r'^[IVX]+$', number):
                    number = self._roman_to_arabic(number)
                return number

        return ''

    def _extract_title_without_number(self, text: str) -> str:
        """
        从文本中提取标题部分（去除编号）

        参数：
            text: 文本

        返回：
            标题部分
        """
        # 尝试匹配各种编号格式并移除
        patterns = [
            r'^\d+(?:\.\d+)*\s*[-:]?\s*',  # 1 - 或 1: 或 1
            r'^Chapter\s+\d+\s*[-:]?\s*',   # Chapter 1 -
            r'^SESSION\s+\d+\s*[-:]?\s*',   # SESSION 1 -
            r'^PAPER\s+\d+(?:\.\d+)*\s*[-:]?\s*',  # PAPER 1.1.1 -
            r'^Section\s+\d+(?:\.\d+)*\s*[-:]?\s*',  # Section 1.1 -
            r'^[IVX]+\.\s*',                # I, II, III, IV
        ]

        for pattern in patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # 移除首尾空格
        text = text.strip()

        return text

    def _roman_to_arabic(self, roman: str) -> str:
        """
        将罗马数字转换为阿拉伯数字

        参数：
            roman: 罗马数字字符串

        返回：
            阿拉伯数字字符串
        """
        roman_values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
        total = 0
        prev_value = 0

        for char in reversed(roman.upper()):
            value = roman_values.get(char, 0)

            if value < prev_value:
                total -= value
            else:
                total += value

            prev_value = value

        return str(total)

    def deduplicate_filenames(
        self,
        chapters: List[Dict],
        extension: str = '.pdf'
    ) -> List[Dict]:
        """
        去重文件名

        参数：
            chapters: 章节列表
            extension: 文件扩展名

        返回：
            更新后的章节列表
        """
        seen = {}

        for chapter in chapters:
            base_name = chapter.get('filename', 'untitled')
            count = 1

            # 生成唯一的文件名
            while (base_name + extension) in seen:
                count += 1
                # 在文件名末尾添加序号
                if '.' in base_name:
                    name, ext = base_name.rsplit('.', 1)
                    new_name = f"{name}_{count}.{ext}"
                else:
                    new_name = f"{base_name}_{count}"
                base_name = new_name

            seen[base_name + extension] = True
            chapter['filename'] = base_name + extension

        return chapters

    def ensure_pdf_extension(self, filename: str) -> str:
        """
        确保文件名有.pdf扩展名

        参数：
            filename: 文件名

        返回：
            带有.pdf扩展名的文件名
        """
        if not filename.lower().endswith('.pdf'):
            return f"{filename}.pdf"

        return filename
