import React, { useState, useCallback } from "react";
import { invoke } from "@tauri-apps/api/tauri";
import { open, save } from "@tauri-apps/api/dialog";
import { listen } from "@tauri-apps/api/event";
import "./App.css";

function App() {
  const [filePath, setFilePath] = useState(null);
  const [fileName, setFileName] = useState("");
  const [chapters, setChapters] = useState([]);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSplitting, setIsSplitting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("请选择PDF文件");
  const [outputDir, setOutputDir] = useState(null);
  const [selectedChapters, setSelectedChapters] = useState(new Set());
  const [splitResults, setSplitResults] = useState([]);

  // 选择文件
  const handleSelectFile = async () => {
    try {
      const selected = await open({
        multiple: false,
        filters: [{ name: "PDF文件", extensions: ["pdf"] }],
      });
      
      if (selected) {
        setFilePath(selected);
        setFileName(selected.split("/").pop() || selected.split("\\").pop());
        setChapters([]);
        setSelectedChapters(new Set());
        setSplitResults([]);
        setStatus("已选择文件，点击开始分析");
      }
    } catch (err) {
      console.error("选择文件失败:", err);
      setStatus("选择文件失败: " + err.message);
    }
  };

  // 分析章节
  const handleAnalyze = async () => {
    if (!filePath) return;
    
    setIsAnalyzing(true);
    setProgress(0);
    setStatus("正在分析PDF章节结构...");
    
    try {
      // 监听进度事件
      const unlisten = await listen("analyze-progress", (event) => {
        const { progress: prog, message, chapters: foundChapters } = event.payload;
        setProgress(prog);
        if (message) setStatus(message);
        if (foundChapters) {
          setChapters(foundChapters);
          setSelectedChapters(new Set(foundChapters.map((_, i) => i)));
        }
      });

      const result = await invoke("analyze_pdf", { filePath });
      
      unlisten();
      
      if (result && result.chapters) {
        setChapters(result.chapters);
        setSelectedChapters(new Set(result.chapters.map((_, i) => i)));
        setStatus(`分析完成！共找到 ${result.chapters.length} 个章节`);
      } else {
        setStatus("未识别到章节结构");
      }
    } catch (err) {
      console.error("分析失败:", err);
      setStatus("分析失败: " + err.message);
    } finally {
      setIsAnalyzing(false);
      setProgress(0);
    }
  };

  // 选择输出目录
  const handleSelectOutputDir = async () => {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
      });
      
      if (selected) {
        setOutputDir(selected);
      }
    } catch (err) {
      console.error("选择目录失败:", err);
    }
  };

  // 拆分PDF
  const handleSplit = async () => {
    if (!filePath || selectedChapters.size === 0) return;
    
    const dir = outputDir || await save({
      defaultPath: "split_pdfs",
    });
    
    if (!dir) return;
    
    setIsSplitting(true);
    setProgress(0);
    setStatus("正在拆分PDF...");
    setSplitResults([]);
    
    try {
      const selectedChapterList = chapters.filter((_, i) => selectedChapters.has(i));
      
      // 监听进度事件
      const unlisten = await listen("split-progress", (event) => {
        const { progress: prog, message } = event.payload;
        setProgress(prog);
        if (message) setStatus(message);
      });

      const result = await invoke("split_pdf", {
        filePath,
        outputDir: dir,
        chapters: selectedChapterList,
      });
      
      unlisten();
      
      if (result && result.files) {
        setSplitResults(result.files);
        setStatus(`拆分完成！共生成 ${result.files.length} 个文件`);
      }
    } catch (err) {
      console.error("拆分失败:", err);
      setStatus("拆分失败: " + err.message);
    } finally {
      setIsSplitting(false);
      setProgress(0);
    }
  };

  // 切换章节选择
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

  // 全选/取消全选
  const toggleAll = () => {
    if (selectedChapters.size === chapters.length) {
      setSelectedChapters(new Set());
    } else {
      setSelectedChapters(new Set(chapters.map((_, i) => i)));
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1>📖 PDF 章节拆分器</h1>
        <p>智能识别章节结构，一键拆分大文件</p>
      </header>

      <main className="main">
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
                <p className="drop-sub">或拖拽文件到此处</p>
              </div>
            )}
          </div>
          
          {filePath && !isAnalyzing && chapters.length === 0 && (
            <button 
              className="btn btn-primary"
              onClick={handleAnalyze}
            >
              🔍 开始分析章节
            </button>
          )}
        </section>

        {/* 进度条 */}
        {(isAnalyzing || isSplitting) && (
          <section className="section progress-section">
            <div className="progress-bar">
              <div 
                className="progress-fill" 
                style={{ width: `${progress}%` }}
              />
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
                      {chapter.title.length > 50 
                        ? chapter.title.substring(0, 50) + "..." 
                        : chapter.title}
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

        {/* 输出设置和拆分 */}
        {chapters.length > 0 && (
          <section className="section split-section">
            <div className="output-settings">
              <div className="output-path">
                <label>输出目录：</label>
                <span className="path-text">
                  {outputDir || "未选择（将弹出保存对话框）"}
                </span>
                <button 
                  className="btn btn-secondary"
                  onClick={handleSelectOutputDir}
                >
                  📂 选择目录
                </button>
              </div>
            </div>
            
            <button 
              className="btn btn-primary btn-large"
              onClick={handleSplit}
              disabled={isSplitting || selectedChapters.size === 0}
            >
              {isSplitting ? "⏳ 拆分中..." : `⚡ 拆分选中的 ${selectedChapters.size} 个章节`}
            </button>
          </section>
        )}

        {/* 拆分结果 */}
        {splitResults.length > 0 && (
          <section className="section results-section">
            <h2>✅ 拆分完成</h2>
            <div className="results-list">
              {splitResults.map((file, index) => (
                <div key={index} className="result-item">
                  <span className="result-icon">📄</span>
                  <span className="result-name">{file.name}</span>
                  <span className="result-size">{file.size}</span>
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
      </main>

      <footer className="footer">
        <p>PDF 章节拆分器 v0.1.0 | 本地处理，保护隐私</p>
      </footer>
    </div>
  );
}

export default App;
