#!/usr/bin/env python3
"""
PDF 拆分工具 - Python 主处理器入口
处理来自 Rust 后端的命令
"""

import sys
import json
import argparse
from typing import Dict
import os

# 设置Python模块搜索路径，确保能找到当前目录的模块
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 导入主处理器
from main_processor import MainProcessor


def send_progress(data: Dict):
    """发送进度事件"""
    print(json.dumps(data, ensure_ascii=False))


def handle_test_connection(args):
    """测试LLM连接"""
    # 读取配置
    llm_config_json = args.llm_config
    llm_config = json.loads(llm_config_json)

    # 创建处理器
    processor = MainProcessor(
        llm_config=llm_config,
        send_callback=send_progress
    )

    # 测试连接
    result = processor.test_llm_connection()

    # 发送响应
    print(json.dumps(result, ensure_ascii=False))


def handle_chat(args):
    """处理Chat消息"""
    # 读取消息和配置
    message_json = args.message
    llm_config_json = args.llm_config

    message = json.loads(message_json)
    llm_config = json.loads(llm_config_json)

    # 创建处理器
    processor = MainProcessor(
        llm_config=llm_config,
        send_callback=send_progress
    )

    # 处理消息
    result = processor.process_chat_message(message)

    # 发送响应
    print(json.dumps(result, ensure_ascii=False))


def handle_analyze(args):
    """处理PDF分析"""
    # 读取请求
    request_json = args.request
    request = json.loads(request_json)

    file_path = request.get('file_path')
    user_requirement = request.get('user_requirement')
    user_naming_rule = request.get('user_naming_rule')
    llm_config = request.get('llm_config')
    chunk_size = request.get('chunk_size', 100)
    overlap_size = request.get('overlap_size', 20)

    # 创建处理器
    processor = MainProcessor(
        llm_config=llm_config,
        chunk_size=chunk_size,
        overlap_size=overlap_size,
        send_callback=send_progress
    )

    # 分析PDF
    result = processor.analyze_pdf(
        file_path,
        user_requirement,
        user_naming_rule
    )

    # 确保章节数据完整
    chapters = result.get('chapters', [])
    normalized_chapters = []
    for ch in chapters:
        normalized_ch = {
            'title': ch.get('title', 'Unknown'),
            'start_page': int(ch.get('start_page', 0)),
            'end_page': int(ch.get('end_page', 0)),
            'filename': ch.get('filename', 'chapter.pdf'),
            'level': int(ch.get('level', 0)),
            'confidence': float(ch.get('confidence', 0.0)),
            'reason': ch.get('reason', '')
        }
        normalized_chapters.append(normalized_ch)

    # 发送完成事件
    send_progress({
        'type': 'analysis_complete',
        'chapters': normalized_chapters,
        'strategy': result.get('strategy', 'llm'),
        'valid': result.get('valid', True),
        'issues': result.get('issues', []),
        'warnings': result.get('warnings', [])
    })


def handle_split(args):
    """处理PDF分割"""
    # 读取请求
    request_json = args.request
    request = json.loads(request_json)

    file_path = request.get('file_path')
    output_dir = request.get('output_dir')
    chapters = request.get('chapters', [])
    filename_template = request.get('filename_template')
    selected_chapters = request.get('selected_chapters')

    # 创建处理器
    processor = MainProcessor(
        llm_config={},  # 不需要LLM
        send_callback=send_progress
    )

    # 设置当前PDF路径
    processor.current_pdf_path = file_path
    processor.current_chapters = chapters

    # 如果指定了选中的章节，使用它们
    if selected_chapters:
        chapters_to_split = selected_chapters
    else:
        chapters_to_split = chapters

    # 执行分割
    results = processor.split_pdf(
        output_dir,
        chapters_to_split,
        filename_template
    )

    # 转换为SplitFile格式
    files = []
    for result in results:
        files.append({
            'filename': result.get('filename'),
            'path': result.get('path'),
            'page_count': result.get('page_count'),
            'file_size': result.get('file_size'),
            'success': result.get('success', True),
            'error': result.get('error')
        })

    # 发送完成事件
    send_progress({
        'type': 'split_complete',
        'results': files
    })


def main():
    parser = argparse.ArgumentParser(description='PDF拆分工具主处理器')

    parser.add_argument('--action', required=True, choices=['test_connection', 'chat', 'analyze', 'split'])
    parser.add_argument('--message', help='Chat消息JSON')
    parser.add_argument('--llm-config', help='LLM配置JSON')
    parser.add_argument('--request', help='请求JSON')

    args = parser.parse_args()

    try:
        if args.action == 'test_connection':
            handle_test_connection(args)
        elif args.action == 'chat':
            handle_chat(args)
        elif args.action == 'analyze':
            handle_analyze(args)
        elif args.action == 'split':
            handle_split(args)
        else:
            print(json.dumps({
                'type': 'error',
                'error': f'未知操作: {args.action}'
            }))
            sys.exit(1)

    except Exception as e:
        print(json.dumps({
            'type': 'error',
            'error': str(e)
        }))
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
