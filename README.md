# PDF 章节拆分器（桌面版）

一个基于 Tauri + React + Python 的桌面应用，用于智能识别 PDF 章节结构并拆分文档。

## 特性

- 📤 拖拽或选择 PDF 文件
- 🔍 自动识别章节结构
- ✂️ 按章节拆分文档
- 💾 选择本地保存位置
- 📊 实时进度显示
- 🖥️ 本地处理，保护隐私

## 项目结构

```
pdf-splitter-desktop/
├── src/                    # React 前端代码
│   ├── App.jsx
│   ├── App.css
│   └── main.jsx
├── src-tauri/             # Tauri/Rust 后端
│   ├── src/
│   │   └── main.rs
│   ├── icons/
│   ├── Cargo.toml
│   ├── build.rs
│   └── tauri.conf.json
├── python_engine/         # Python 处理引擎
│   ├── pdf_engine.py      # 核心处理逻辑
│   └── requirements.txt
├── index.html
├── package.json
└── vite.config.js
```

## 开发环境要求

- Node.js 18+
- Rust 1.70+
- Python 3.8+

## 快速开始

### 1. 安装前端依赖

```bash
cd pdf-splitter-desktop
npm install
```

### 2. 安装 Python 依赖

```bash
cd python_engine
pip install -r requirements.txt
cd ..
```

### 3. 安装 Tauri CLI（如果未安装）

```bash
cargo install tauri-cli
```

### 4. 运行开发版本

```bash
npm run tauri dev
```

### 5. 构建发布版本

```bash
npm run tauri build
```

## 使用说明

1. 点击主界面选择 PDF 文件
2. 点击"开始分析章节"识别文档结构
3. 勾选要拆分的章节（支持全选/取消全选）
4. 选择输出目录
5. 点击"拆分"按钮生成文件

## 技术栈

- **前端**: React 18 + Vite
- **后端**: Tauri (Rust)
- **PDF处理**: Python + PyPDF2
- **通信**: Tauri IPC + Event

## 大文件支持

- 使用流式处理，避免一次性加载大文件到内存
- 支持 GB 级 PDF 文件（取决于系统内存）
- 进度实时显示，可随时了解处理状态

## 章节识别规则

支持自动识别以下格式的章节：
- Chapter 1 / CHAPTER I
- 1. / 1.1 / 1.1.1
- Section 1
- I. / II. / III.
- 第1章 / 第一章
- Abstract / Introduction / Conclusion
- 学术论文格式 (1 Title)

## 注意事项

1. 首次运行需要 Python 环境，建议提前安装 PyPDF2
2. 对于扫描版 PDF（图片型），无法识别文字内容
3. 章节识别基于文本分析，复杂排版可能影响准确率

## License

MIT
