// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::process::Stdio;
use tauri::{Manager, Window, command, generate_context, generate_handler, Builder, Runtime};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;

// 章节数据结构
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Chapter {
    pub title: String,
    pub start_page: i32,
    pub end_page: i32,
    pub level: i32,
}

// 分析结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalyzeResult {
    pub chapters: Vec<Chapter>,
}

// 拆分结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SplitResult {
    pub files: Vec<SplitFile>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SplitFile {
    pub name: String,
    pub path: String,
    pub size: String,
    pub pages: i32,
}

// 获取Python引擎路径
fn get_python_engine_path() -> std::path::PathBuf {
    let exe_path = std::env::current_exe().expect("无法获取可执行文件路径");
    let exe_dir = exe_path.parent().expect("无法获取可执行文件目录");
    
    // 在开发模式下
    if cfg!(debug_assertions) {
        exe_dir
            .parent()
            .expect("无法获取父目录")
            .parent()
            .expect("无法获取祖父目录")
            .parent()
            .expect("无法获取曾祖父目录")
            .join("python_engine")
            .join("pdf_engine.py")
    } else {
        // 在发布模式下，Python引擎应该在资源目录中
        exe_dir.join("python_engine").join("pdf_engine.py")
    }
}

// 获取Python解释器路径
fn get_python_path() -> String {
    // 优先使用内嵌的Python，否则使用系统Python
    if let Ok(python_path) = std::env::var("PDF_SPLITTER_PYTHON") {
        return python_path;
    }
    
    // 检查是否有内嵌的Python
    let exe_path = std::env::current_exe().expect("无法获取可执行文件路径");
    let exe_dir = exe_path.parent().expect("无法获取可执行文件目录");
    let bundled_python = exe_dir.join("python").join("python.exe");
    
    if bundled_python.exists() {
        return bundled_python.to_string_lossy().to_string();
    }
    
    // 使用系统Python
    "python3".to_string()
}

// 分析PDF
#[command]
async fn analyze_pdf<R: Runtime>(
    window: Window<R>,
    file_path: String,
) -> Result<AnalyzeResult, String> {
    let python_path = get_python_path();
    let engine_path = get_python_engine_path();
    
    // 检查引擎文件是否存在
    if !engine_path.exists() {
        return Err(format!("找不到Python引擎: {:?}", engine_path));
    }

    // 检查PDF文件是否存在
    if !std::path::Path::new(&file_path).exists() {
        return Err(format!("PDF文件不存在: {}", file_path));
    }

    let mut child = Command::new(&python_path)
        .arg(&engine_path)
        .arg("--action")
        .arg("analyze")
        .arg("--input")
        .arg(&file_path)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("启动Python进程失败: {} (python_path: {}, engine_path: {}, file_path: {})", e, python_path, engine_path.display(), file_path))?;

    let stdout = child.stdout.take().ok_or("无法获取stdout")?;
    let stderr = child.stderr.take().ok_or("无法获取stderr")?;
    let mut stderr_lines = BufReader::new(stderr).lines();

    let reader = BufReader::new(stdout);
    let mut lines = reader.lines();

    // 收集stderr以便在出错时使用
    let mut error_output = String::new();
    
    let mut chapters: Vec<Chapter> = Vec::new();
    let mut last_progress = 0.0;
    
    // 读取Python进程的输出
    while let Ok(Some(line)) = lines.next_line().await {
        // 尝试解析JSON
        if let Ok(json) = serde_json::from_str::<serde_json::Value>(&line) {
            match json.get("type").and_then(|t| t.as_str()) {
                Some("progress") => {
                    let progress = json.get("progress").and_then(|p| p.as_f64()).unwrap_or(0.0);
                    let message = json.get("message").and_then(|m| m.as_str()).unwrap_or("");
                    
                    // 只在进度变化超过1%时发送事件
                    if progress - last_progress >= 1.0 || progress >= 99.0 {
                        last_progress = progress;
                        let _ = window.emit("analyze-progress", serde_json::json!({
                            "progress": progress,
                            "message": message,
                        }));
                    }
                }
                Some("complete") => {
                    if let Some(data) = json.get("data").or_else(|| json.get("chapters")) {
                        if let Ok(chs) = serde_json::from_value::<Vec<Chapter>>(data.clone()) {
                            chapters = chs;
                        }
                    }
                }
                Some("error") => {
                    let error = json.get("error").and_then(|e| e.as_str()).unwrap_or("未知错误");
                    return Err(error.to_string());
                }
                _ => {}
            }
        }
    }

    // 等待进程结束
    let status = child.wait().await.map_err(|e| format!("等待进程失败: {}", e))?;

    // 读取所有stderr输出
    while let Ok(Some(line)) = stderr_lines.next_line().await {
        error_output.push_str(&line);
        error_output.push('\n');
    }

    if !status.success() {
        let error_msg = if error_output.trim().is_empty() {
            "Python进程执行失败".to_string()
        } else {
            format!("Python进程执行失败: {}", error_output.trim())
        };
        return Err(error_msg);
    }
    
    Ok(AnalyzeResult { chapters })
}

// 拆分PDF
#[command]
async fn split_pdf<R: Runtime>(
    window: Window<R>,
    file_path: String,
    output_dir: String,
    chapters: Vec<Chapter>,
) -> Result<SplitResult, String> {
    let python_path = get_python_path();
    let engine_path = get_python_engine_path();
    
    // 序列化章节数据
    let chapters_json = serde_json::to_string(&chapters)
        .map_err(|e| format!("序列化章节数据失败: {}", e))?;
    
    let mut child = Command::new(&python_path)
        .arg(&engine_path)
        .arg("--action")
        .arg("split")
        .arg("--input")
        .arg(&file_path)
        .arg("--output")
        .arg(&output_dir)
        .arg("--chapters")
        .arg(&chapters_json)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("启动Python进程失败: {}", e))?;
    
    let stdout = child.stdout.take().ok_or("无法获取stdout")?;
    let stderr = child.stderr.take().ok_or("无法获取stderr")?;
    let mut stderr_lines = BufReader::new(stderr).lines();

    let reader = BufReader::new(stdout);
    let mut lines = reader.lines();

    let mut files: Vec<SplitFile> = Vec::new();
    let mut last_progress = 0.0;
    let mut error_output = String::new();
    
    while let Ok(Some(line)) = lines.next_line().await {
        if let Ok(json) = serde_json::from_str::<serde_json::Value>(&line) {
            match json.get("type").and_then(|t| t.as_str()) {
                Some("progress") => {
                    let progress = json.get("progress").and_then(|p| p.as_f64()).unwrap_or(0.0);
                    let message = json.get("message").and_then(|m| m.as_str()).unwrap_or("");
                    
                    if progress - last_progress >= 1.0 || progress >= 99.0 {
                        last_progress = progress;
                        let _ = window.emit("split-progress", serde_json::json!({
                            "progress": progress,
                            "message": message,
                        }));
                    }
                }
                Some("complete") => {
                    if let Some(data) = json.get("files") {
                        if let Ok(f) = serde_json::from_value::<Vec<SplitFile>>(data.clone()) {
                            files = f;
                        }
                    }
                }
                Some("error") => {
                    let error = json.get("error").and_then(|e| e.as_str()).unwrap_or("未知错误");
                    return Err(error.to_string());
                }
                _ => {}
            }
        }
    }

    // 读取所有stderr输出
    while let Ok(Some(line)) = stderr_lines.next_line().await {
        error_output.push_str(&line);
        error_output.push('\n');
    }

    let status = child.wait().await.map_err(|e| format!("等待进程失败: {}", e))?;

    if !status.success() {
        let error_msg = if error_output.trim().is_empty() {
            "Python进程执行失败".to_string()
        } else {
            format!("Python进程执行失败: {}", error_output.trim())
        };
        return Err(error_msg);
    }

    Ok(SplitResult { files })
}

fn main() {
    Builder::default()
        .invoke_handler(generate_handler![analyze_pdf, split_pdf])
        .run(generate_context!())
        .expect("运行Tauri应用时出错");
}
