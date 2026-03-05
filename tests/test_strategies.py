#!/usr/bin/env python3
"""
ISSCCSessionStrategy 单元测试
"""

import sys
from pathlib import Path

# 添加 python_engine 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent / 'python_engine'))

from pdf_engine import ISSCCSessionStrategy


def test_new_chapter_detection():
    """测试新章节识别"""
    strategy = ISSCCSessionStrategy()

    # 应该识别为新章节
    header1 = "ISSCC 2026 / SESSION 1 / PLENARY / 1.1"
    result1 = strategy.analyze_page(header1)
    print(f"测试 1: '{header1}' → {result1}")
    assert result1 == 'NEW_CHAPTER', f"期望 NEW_CHAPTER，实际 {result1}"

    header2 = "ISSCC 2026 / SESSION 2 / DIGITAL / 3.2"
    result2 = strategy.analyze_page(header2)
    print(f"测试 2: '{header2}' → {result2}")
    assert result2 == 'NEW_CHAPTER', f"期望 NEW_CHAPTER，实际 {result2}"

    print("✓ 新章节识别测试通过\n")


def test_time_header_detection():
    """测试时间页眉识别"""
    strategy = ISSCCSessionStrategy()

    # 时间页眉应该识别为有效内容
    header = "ISSCC 2026 / February 16, 2026 / 10:45 AM"
    result = strategy.analyze_page(header)
    print(f"测试: '{header}' → {result}")
    assert result == 'VALID_CONTENT', f"期望 VALID_CONTENT，实际 {result}"

    print("✓ 时间页眉识别测试通过\n")


def test_invalid_header_detection():
    """测试无关页眉识别"""
    strategy = ISSCCSessionStrategy()

    # PROGRAM 页眉应该识别为无效
    header1 = "ISSCC 2026 / PROGRAM"
    result1 = strategy.analyze_page(header1)
    print(f"测试 1: '{header1}' → {result1}")
    assert result1 == 'INVALID', f"期望 INVALID，实际 {result1}"

    # DIGEST OF TECHNICAL PAPERS 页眉应该识别为无效
    header2 = "DIGEST OF TECHNICAL PAPERS"
    result2 = strategy.analyze_page(header2)
    print(f"测试 2: '{header2}' → {result2}")
    assert result2 == 'INVALID', f"期望 INVALID，实际 {result2}"

    # 空页眉应该识别为无效
    header3 = ""
    result3 = strategy.analyze_page(header3)
    print(f"测试 3: '(空)' → {result3}")
    assert result3 == 'INVALID', f"期望 INVALID，实际 {result3}"

    print("✓ 无关页眉识别测试通过\n")


def test_chapter_number_extraction():
    """测试章节编号提取"""
    strategy = ISSCCSessionStrategy()

    header1 = "ISSCC 2026 / SESSION 1 / PLENARY / 1.1"
    result1 = strategy.extract_chapter_number(header1)
    print(f"测试 1: '{header1}' → {result1}")
    assert result1 == "1.1", f"期望 1.1，实际 {result1}"

    header2 = "ISSCC 2026 / SESSION 2 / DIGITAL / 3.2"
    result2 = strategy.extract_chapter_number(header2)
    print(f"测试 2: '{header2}' → {result2}")
    assert result2 == "3.2", f"期望 3.2，实际 {result2}"

    print("✓ 章节编号提取测试通过\n")


def test_tracked_header_detection():
    """测试跟踪的章节编号识别"""
    strategy = ISSCCSessionStrategy()

    # 设置当前跟踪的章节编号
    strategy.current_chapter_number = "1.1"

    # 相同章节编号的页眉应该识别为有效内容
    header1 = "ISSCC 2026 / SESSION 1 / PLENARY / 1.1"
    result1 = strategy.analyze_page(header1)
    print(f"测试 1: '{header1}' (编号已跟踪: 1.1) → {result1}")
    assert result1 == 'VALID_CONTENT', f"期望 VALID_CONTENT，实际 {result1}"

    # 不同章节编号的页眉应该识别为新章节
    header2 = "ISSCC 2026 / SESSION 1 / PLENARY / 1.2"
    result2 = strategy.analyze_page(header2)
    print(f"测试 2: '{header2}' (编号已跟踪: 1.1) → {result2}")
    assert result2 == 'NEW_CHAPTER', f"期望 NEW_CHAPTER，实际 {result2}"

    print("✓ 跟踪章节编号识别测试通过\n")


def test_title_extraction():
    """测试标题提取"""
    strategy = ISSCCSessionStrategy()

    # 模拟页面文本 - 简单情况
    page_text = """ISSCC 2026 / SESSION 1 / PLENARY / 1.1
Some Paper Title Goes Here
This is the abstract of the paper..."""

    result = strategy.extract_title(page_text)
    print(f"测试 1: 提取标题 → {result}")
    assert result == "Some Paper Title Goes Here", f"期望 'Some Paper Title Goes Here'，实际 {result}"

    # 模拟页面文本 - 带版权前缀的情况
    page_text2 = """10  •  2026 IEEE International Solid-State Circuits ConferenceISSCC 2026 / SESSION 1 / PLENARY / 1.1
979-8-3315-8936-3/26/$31.00 ©2026 IEEE1.0 The Growth of AI, Unleashing Opportunities and the IC Ecosystem
The pervasive integration of artiﬁcial intelligence (AI) across every industry and aspect of"""

    result2 = strategy.extract_title(page_text2)
    print(f"测试 2: 提取标题（带版权前缀） → {result2}")
    assert result2 == "The Growth of AI, Unleashing Opportunities and the IC Ecosystem", f"期望 'The Growth of AI, Unleashing Opportunities and the IC Ecosystem'，实际 {result2}"

    print("✓ 标题提取测试通过\n")


def test_figure_page_detection():
    """测试Figure页面识别"""
    strategy = ISSCCSessionStrategy()

    # Figure页眉应该识别为有效内容
    header1 = "Figure 1.1.1: Global Semiconductor Market to Reach $1 Trillion in 2030"
    result1 = strategy.analyze_page(header1)
    print(f"测试 1: '{header1}' → {result1}")
    assert result1 == 'VALID_CONTENT', f"期望 VALID_CONTENT，实际 {result1}"

    header2 = "Figure 1.1.7: AI Compute - From Cloud to Edge"
    result2 = strategy.analyze_page(header2)
    print(f"测试 2: '{header2}' → {result2}")
    assert result2 == 'VALID_CONTENT', f"期望 VALID_CONTENT，实际 {result2}"

    print("✓ Figure页面识别测试通过\n")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("开始运行单元测试...")
    print("=" * 60)
    print()

    try:
        test_new_chapter_detection()
        test_time_header_detection()
        test_invalid_header_detection()
        test_chapter_number_extraction()
        test_tracked_header_detection()
        test_title_extraction()
        test_figure_page_detection()

        print("=" * 60)
        print("所有测试通过！✓")
        print("=" * 60)
        return True

    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        return False
    except Exception as e:
        print(f"\n✗ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
