#!/bin/bash

# PDF 章节拆分器 - 快速启动脚本

echo "🚀 启动 PDF 章节拆分器..."

# 检查依赖
check_dependency() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ 未找到 $1，请先安装"
        return 1
    fi
    echo "✅ $1 已安装"
    return 0
}

echo ""
echo "检查依赖..."
check_dependency node || exit 1
check_dependency npm || exit 1
check_dependency python3 || exit 1

# 检查Python依赖
echo ""
echo "检查 Python 依赖..."
if python3 -c "import PyPDF2" 2>/dev/null; then
    echo "✅ PyPDF2 已安装"
else
    echo "⚠️  正在安装 PyPDF2..."
    pip3 install PyPDF2
fi

# 安装Node依赖
echo ""
echo "安装 Node 依赖..."
npm install

# 启动开发服务器
echo ""
echo "启动开发服务器..."
echo "等待 Tauri 启动中..."
echo ""

npm run tauri dev
