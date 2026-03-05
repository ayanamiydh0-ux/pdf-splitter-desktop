import React, { useState, useCallback, useEffect, useRef } from "react";
import { invoke } from "@tauri-apps/api/tauri";
import { open } from "@tauri-apps/api/dialog";
import { listen } from "@tauri-apps/api/event";
import "./App.css";

// LLM预设配置
const LLM_PRESETS = {
  openai: {
    name: "OpenAI",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4"
  },
  kimi: {
    name: "Kimi (Moonshot)",
    base_url: "https://api.moonshot.cn/v1",
    model: "moonshot-v1-8k"
  },
  glm: {
    name: "GLM-4 (智谱)",
    base_url: "https://open.bigmodel.cn/api/paas/v4",
    model: "glm-4"
  },
  "glm-coding": {
    name: "GLM Coding Max (智谱)",
    base_url: "https://open.bigmodel.cn/api/paas/v4",
    model: "glm-4-flash"
  },
  deepseek: {
    name: "DeepSeek",
    base_url: "https://api.deepseek.com",
    model: "deepseek-chat"
  },
  ollama: {
    name: "Ollama (本地)",
    base_url: "http://localhost:11434/v1",
    model: "llama3"
  }
};

function App() {
  // ============ 状态管理 ============

  // 文件相关
  const [filePath, setFilePath] = useState(null);
  const [fileName, setFileName] = useState("");
  const [chapters, setChapters] = useState([]);
  const [selectedChapters, setSelectedChapters] = useState(new Set());
  const [splitResults, setSplitResults] = useState([]);

  // 进度和状态
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSplitting, setIsSplitting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("请选择PDF文件或描述拆分需求");
  const [elapsedTime, setElapsedTime] = useState(0);
  const [tokenConsumed, setTokenConsumed] = useState(0);

  // 输出相关
  const [outputDir, setOutputDir] = useState(null);

  // Chat相关
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [showChat, setShowChat] = useState(true);
  const [extractedRule, setExtractedRule] = useState(null);

  // LLM配置
  const [llmConfig, setLlmConfig] = useState({
    api_key: "",
    preset: "kimi",
    base_url: "",
    model: ""
  });
  const [showSettings, setShowSettings] = useState(false);
  const [llmConnected, setLlmConnected] = useState(false);
  const [llmTesting, setLlmTesting] = useState(false);

  // 分块配置
  const [chunkSize, setChunkSize] = useState(30);
  const [overlapSize, setOverlapSize] = useState(10);

  // 分析结果
  const [analysisStrategy, setAnalysisStrategy] = useState("");
  const [analysisValid, setAnalysisValid] = useState(true);
  const [analysisIssues, setAnalysisIssues] = useState([]);
  const [analysisWarnings, setAnalysisWarnings] = useState([]);

  // 进度详情
  const [pagesAnalyzed, setPagesAnalyzed] = useState(0);
  const [totalPages, setTotalPages] = useState(0);

  // Refs
  const progressRef = useRef(null);

  // ============ Chat功能 ============

  const handleSendMessage = async () => {
    if (!chatInput.trim()) return;

    const userMessage = {
      type: "text",
      content: chatInput,
      metadata: {}
    };

    // 添加用户消息
    setChatMessages(prev => [...prev, { role: "user", content: chatInput }]);
    setChatInput("");
    setStatus("正在理解你的需求...");

    try {
      const response = await invoke("process_chat_message", {
        message: userMessage,
        llmConfig: llmConfig
      });

      // 添加助手回复
      setChatMessages(prev => [...prev, {
        role: "assistant",
        content: response.response
      }]);

      // 保存提取的规则
      if (response.extracted_rule) {
        setExtractedRule(response.extracted_rule);
      }

      // 如果需要澄清，提示用户
      if (response.needs_clarification && response.clarification_questions.length > 0) {
        setStatus(`需要更多信息：${response.clarification_questions.join("; ")}`);
      } else {
        setStatus("需求理解完成！请选择PDF文件开始分析");
      }

    } catch (err) {
      console.error("Chat失败:", err);
      setStatus("处理失败: " + (err?.message || err?.toString()));
    }
  };

  const clearChat = () => {
    setChatMessages([]);
    setExtractedRule(null);
  };

  // ============ 文件选择 ============

  const handleSelectFile = async () => {
    try {
      const selected = await open({
        multiple: false,
        filters: [{ name: "PDF文件", extensions: ["pdf"] }]
      });

      if (selected) {
        setFilePath(selected);
        setFileName(selected.split("/").pop() || selected.split("\\").pop());
        setChapters([]);
        setSelectedChapters(new Set());
        setSplitResults([]);
        setPagesAnalyzed(0);
        setTotalPages(0);
        setStatus("已选择文件，点击\"开始分析\"或通过Chat描述需求");
      }
    } catch (err) {
      console.error("选择文件失败:", err);
      setStatus("选择文件失败: " + err.message);
    }
  };

  // ============ PDF分析 ============

  const handleAnalyze = async () => {
    if (!filePath) return;

    setIsAnalyzing(true);
    setProgress(0);
    setStatus("正在分析PDF...");
    setElapsedTime(0);
    setTokenConsumed(0);

    // 开始计时
    const startTime = Date.now();
    const timer = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    try {
      // 监听进度事件
      const unlisten = await listen("analyze-progress", (event) => {
        const payload = event.payload;
        setProgress(payload.progress || 0);

        if (payload.message) {
          setStatus(payload.message);
        }

        if (payload.pages_analyzed !== undefined) {
          setPagesAnalyzed(payload.pages_analyzed);
        }

        if (payload.total_pages !== undefined) {
          setTotalPages(payload.total_pages);
        }
      });

      // 监听调试事件
      const unlistenDebug = await listen("analyze-debug", (event) => {
        console.log("[RUST DEBUG]", event.payload);
      });

      // 构建分析请求
      const request = {
        file_path: filePath,
        user_requirement: extractedRule ? JSON.stringify(extractedRule) : "按章节拆分",
        user_naming_rule: null,
        llm_config: llmConfig,
        chunk_size: chunkSize,
        overlap_size: overlapSize
      };

      const result = await invoke("analyze_pdf", { request });

      unlisten();
      unlistenDebug();
      clearInterval(timer);

      // 调试：打印完整结果
      console.log("[DEBUG] 分析结果:", result);

      if (result && result.chapters && result.chapters.length > 0) {
        console.log("[DEBUG] 章节数量:", result.chapters.length);
        console.log("[DEBUG] 章节示例:", result.chapters[0]);

        setChapters(result.chapters);
        setAnalysisStrategy(result.strategy);
        setAnalysisValid(result.valid);
        setAnalysisIssues(result.issues || []);
        setAnalysisWarnings(result.warnings || []);
        setSelectedChapters(new Set(result.chapters.map((_, i) => i)));

        const warningText = result.warnings && result.warnings.length > 0
          ? ` 警告: ${result.warnings[0]}`
          : "";

        setStatus(`分析完成！使用${result.strategy === "bookmark" ? "书签" : "LLM"}识别到 ${result.chapters.length} 个章节${warningText}`);
      } else {
        console.error("[DEBUG] 结果格式异常:", result);
        setStatus(`未识别到章节结构。result=${JSON.stringify(result)}`);
      }
    } catch (err) {
      console.error("分析失败:", err);
      const errorMessage = err?.message || err?.toString() || "未知错误";
      setStatus("分析失败: " + errorMessage);
    } finally {
      setIsAnalyzing(false);
      clearInterval(timer);
    }
  };

  // ============ PDF分割 ============

  const handleSplit = async () => {
    if (!filePath || selectedChapters.size === 0) return;

    // 选择输出目录
    let dir = outputDir;
    if (!dir) {
      try {
        dir = await open({
          directory: true,
          multiple: false
        });
      } catch (err) {
        // 用户取消了
        return;
      }
    }

    if (!dir) return;

    setIsSplitting(true);
    setProgress(0);
    setStatus("正在拆分PDF...");
    setSplitResults([]);

    const startTime = Date.now();
    const timer = setInterval(() => {
      setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    try {
      const selectedChapterList = chapters.filter((_, i) => selectedChapters.has(i));

      // 监听进度事件
      const unlisten = await listen("split-progress", (event) => {
        const payload = event.payload;
        setProgress(payload.progress || 0);
        if (payload.message) {
          setStatus(payload.message);
        }
      });

      const request = {
        file_path: filePath,
        output_dir: dir,
        chapters: selectedChapterList,
        filename_template: null,
        selected_chapters: null
      };

      const result = await invoke("split_pdf", { request });

      unlisten();
      clearInterval(timer);

      if (result && result.files) {
        setSplitResults(result.files);
        setStatus(`拆分完成！共生成 ${result.files.length} 个文件`);
      } else {
        setStatus("拆分失败");
      }
    } catch (err) {
      console.error("拆分失败:", err);
      setStatus("拆分失败: " + (err?.message || err?.toString()));
    } finally {
      setIsSplitting(false);
      clearInterval(timer);
    }
  };

  // ============ LLM配置 ============

  const handleTestLLM = async () => {
    if (!llmConfig.api_key) {
      alert("请输入API Key");
      return;
    }

    setLlmTesting(true);
    setStatus("正在测试LLM连接...");

    try {
      const result = await invoke("test_llm_connection", {
        llmConfig: llmConfig
      });

      if (result.success) {
        setLlmConnected(true);
        setStatus("LLM连接测试成功！" + (result.message || ""));
      } else {
        setLlmConnected(false);
        setStatus("LLM连接测试失败: " + (result.message || "未知错误"));
      }
    } catch (err) {
      console.error("LLM测试失败:", err);
      setLlmConnected(false);
      setStatus("LLM连接测试失败: " + (err?.message || err?.toString()));
    } finally {
      setLlmTesting(false);
    }
  };

  const handlePresetChange = (preset) => {
    const presetConfig = LLM_PRESETS[preset];
    if (presetConfig) {
      setLlmConfig(prev => ({
        ...prev,
        preset: preset,
        base_url: prev.base_url || presetConfig.base_url,
        model: prev.model || presetConfig.model
      }));
    }
  };

  // ============ 章节选择 ============

  const toggleChapter = (index) => {
    setSelectedChapters(prev => {
      const newSet = new Set(prev);
      if (newSet.has(index)) {
        newSet.delete(index);
      } else {
        newSet.add(index);
      }
      return newSet;
    });
  };

  const toggleAll = () => {
    if (selectedChapters.size === chapters.length) {
      setSelectedChapters(new Set());
    } else {
      setSelectedChapters(new Set(chapters.map((_, i) => i)));
    }
  };

  // ============ 格式化辅助函数 ============

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  // ============ 渲染 ============

  return (
    <div className="app">
      {/* 顶部导航 */}
      <header className="header">
        <div className="header-left">
          <h1>📖 PDF 智能拆分器</h1>
          <p>Chat交互 + AI分析，智能拆分PDF文档</p>
        </div>
        <button
          className="btn btn-icon"
          onClick={() => setShowSettings(!showSettings)}
          title="设置"
        >
          ⚙️ 设置
        </button>
      </header>

      <main className="main">
        <div className="main-grid">
          <div className="main-grid-content">
            {/* 左侧：文件和结果 */}
            <div className="left-panel">
            {/* 文件选择区域 */}
            <section className="section">
              <div
                className={`file-drop-zone ${filePath ? 'has-file' : ''}`}
                onClick={handleSelectFile}
              >
                {fileName ? (
                  <div className="file-info">
                    <span className="file-icon">📄</span>
                    <span className="file-name">{fileName}</span>
                    <span className="change-file">点击更换文件</span>
                  </div>
                ) : (
                  <div className="drop-hint">
                    <span className="drop-icon">📁</span>
                    <p>点击选择 PDF 文件</p>
                  </div>
                )}
              </div>

              {filePath && !isAnalyzing && chapters.length === 0 && (
                <button
                  className="btn btn-primary btn-full"
                  onClick={handleAnalyze}
                >
                  🔍 开始分析
                </button>
              )}
            </section>

            {/* 进度条 */}
            {(isAnalyzing || isSplitting) && (
              <section className="section progress-section">
                <div className="progress-container">
                  <div className="progress-bar">
                    <div
                      className="progress-fill"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <div className="progress-stats">
                    <span className="stat">
                      📄 {pagesAnalyzed}/{totalPages} 页
                    </span>
                    <span className="stat">
                      ⏱️ {formatTime(elapsedTime)}
                    </span>
                    {tokenConsumed > 0 && (
                      <span className="stat">
                        💰 {tokenConsumed} tokens
                      </span>
                    )}
                  </div>
                </div>
                <p className="status-text">{status}</p>
              </section>
            )}

            {/* 章节列表 */}
            {chapters.length > 0 && (
              <section className="section">
                <div className="section-header">
                  <h2>📚 识别到的章节</h2>
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={selectedChapters.size === chapters.length}
                      onChange={toggleAll}
                    />
                    全选 ({selectedChapters.size}/{chapters.length})
                  </label>
                </div>

                {/* 分析信息 */}
                <div className="analysis-info">
                  <span className="strategy-badge">
                    {analysisStrategy === "bookmark" ? "🔖 书签" : "🤖 LLM"}
                  </span>
                  {analysisIssues.length > 0 && (
                    <span className="issue-badge">
                      ⚠️ {analysisIssues.length} 个问题
                    </span>
                  )}
                </div>

                <div className="chapter-list">
                  {chapters.map((chapter, index) => (
                    <div
                      key={index}
                      className={`chapter-item ${selectedChapters.has(index) ? 'selected' : ''}`}
                      onClick={() => toggleChapter(index)}
                    >
                      <input
                        type="checkbox"
                        checked={selectedChapters.has(index)}
                        onChange={() => {}}
                      />
                      <div className="chapter-info">
                        <span className="chapter-title" title={chapter.title}>
                          {chapter.title}
                        </span>
                        <span className="chapter-pages">
                          第 {chapter.start_page}-{chapter.end_page} 页
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* 拆分按钮 */}
            {chapters.length > 0 && (
              <section className="section">
                <button
                  className="btn btn-primary btn-large btn-full"
                  onClick={handleSplit}
                  disabled={isSplitting || selectedChapters.size === 0}
                >
                  {isSplitting ? "⏳ 拆分中..." : `⚡ 拆分 ${selectedChapters.size} 个章节`}
                </button>
              </section>
            )}

            {/* 拆分结果 */}
            {splitResults.length > 0 && (
              <section className="section">
                <h2>✅ 拆分完成</h2>
                <div className="results-list">
                  {splitResults.map((file, index) => (
                    <div key={index} className="result-item">
                      <span className="result-icon">📄</span>
                      <span className="result-name">{file.filename}</span>
                      <span className="result-size">{formatFileSize(file.file_size)}</span>
                      <span className="result-pages">{file.page_count} 页</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {/* 状态栏 */}
            {!isAnalyzing && !isSplitting && status && (
              <section className="section">
                <p className="status-text">{status}</p>
              </section>
            )}
          </div>

          {/* 右侧：Chat窗口 */}
          {showChat && (
            <div className="right-panel chat-panel">
              <div className="chat-header">
                <h3>💬 智能助手</h3>
                <div className="chat-actions">
                  <button
                    className="btn btn-icon"
                    onClick={clearChat}
                    title="清空对话"
                  >
                    🗑️
                  </button>
                  <button
                    className="btn btn-icon"
                    onClick={() => setShowChat(false)}
                    title="关闭"
                  >
                    ✖️
                  </button>
                </div>
              </div>

              <div className="chat-messages">
                {chatMessages.length === 0 ? (
                  <div className="chat-welcome">
                    <p>👋 你好！我是PDF拆分助手。</p>
                    <p>你可以：</p>
                    <ul>
                      <li>描述你的拆分需求</li>
                      <li>上传相关文档或图片</li>
                      <li>询问如何使用</li>
                    </ul>
                    <p className="chat-hint">示例："请按SESSION拆分这个会议录"</p>
                  </div>
                ) : (
                  chatMessages.map((msg, index) => (
                    <div
                      key={index}
                      className={`chat-message ${msg.role}`}
                    >
                      <div className="message-avatar">
                        {msg.role === "user" ? "👤" : "🤖"}
                      </div>
                      <div className="message-content">
                        {msg.content}
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div className="chat-input-area">
                <textarea
                  className="chat-input"
                  placeholder="描述你的拆分需求..."
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage();
                    }
                  }}
                  disabled={isAnalyzing || isSplitting}
                />
                <button
                  className="btn btn-primary"
                  onClick={handleSendMessage}
                  disabled={!chatInput.trim() || isAnalyzing || isSplitting}
                >
                  发送
                </button>
              </div>
            </div>
          )}

          {!showChat && (
            <button
              className="btn btn-icon chat-toggle"
              onClick={() => setShowChat(true)}
              title="打开Chat"
            >
              💬
            </button>
          )}
          </div>
        </div>
      </main>

      {/* 设置面板 */}
      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal settings-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>⚙️ 设置</h2>
              <button
                className="btn btn-icon"
                onClick={() => setShowSettings(false)}
              >
                ✖️
              </button>
            </div>

            <div className="modal-body">
              {/* LLM配置 */}
              <div className="settings-section">
                <h3>🤖 大模型配置</h3>

                <div className="form-group">
                  <label>快速选择：</label>
                  <div className="preset-buttons">
                    {Object.entries(LLM_PRESETS).map(([key, preset]) => (
                      <button
                        key={key}
                        className={`btn ${llmConfig.preset === key ? 'btn-primary' : 'btn-secondary'}`}
                        onClick={() => handlePresetChange(key)}
                      >
                        {preset.name}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="form-group">
                  <label>API Key：</label>
                  <input
                    type="password"
                    className="input-field"
                    placeholder="输入API Key"
                    value={llmConfig.api_key}
                    onChange={(e) => setLlmConfig({ ...llmConfig, api_key: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Base URL：</label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder={LLM_PRESETS[llmConfig.preset]?.base_url || ""}
                    value={llmConfig.base_url}
                    onChange={(e) => setLlmConfig({ ...llmConfig, base_url: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>模型：</label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder={LLM_PRESETS[llmConfig.preset]?.model || ""}
                    value={llmConfig.model}
                    onChange={(e) => setLlmConfig({ ...llmConfig, model: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <button
                    className="btn btn-secondary"
                    onClick={handleTestLLM}
                    disabled={llmTesting || !llmConfig.api_key}
                  >
                    {llmTesting ? "测试中..." : "🔗 测试连接"}
                  </button>
                  {llmConnected && <span className="status-success">✅ 已连接</span>}
                </div>
              </div>

              {/* 分块配置 */}
              <div className="settings-section">
                <h3>📊 分块配置</h3>

                <div className="form-group">
                  <label>每块大小（页）：</label>
                  <input
                    type="number"
                    className="input-field"
                    min="10"
                    max="500"
                    value={chunkSize}
                    onChange={(e) => setChunkSize(parseInt(e.target.value))}
                  />
                </div>

                <div className="form-group">
                  <label>重叠区域（页）：</label>
                  <input
                    type="number"
                    className="input-field"
                    min="5"
                    max="100"
                    value={overlapSize}
                    onChange={(e) => setOverlapSize(parseInt(e.target.value))}
                  />
                  <p className="form-hint">
                    重叠区域用于确保跨块章节不被错误拆分
                  </p>
                </div>
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn btn-primary" onClick={() => setShowSettings(false)}>
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      <footer className="footer">
        <p>PDF 智能拆分器 v2.0 | AI驱动，本地处理</p>
      </footer>
    </div>
  );
}

export default App;
