// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::process::Stdio;
use tauri::{Window, command, generate_context, generate_handler, Builder, Runtime};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;

// ==================== 数据结构 ====================

// 章节数据结构
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Chapter {
    pub title: String,
    pub start_page: i32,
    pub end_page: i32,
    pub filename: String,
    #[serde(default)]
    pub level: i32,
    #[serde(default)]
    pub confidence: f64,
    #[serde(default)]
    pub reason: String,
}

// Chat消息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    #[serde(rename = "type")]
    pub msg_type: String,
    pub content: String,
    #[serde(default)]
    pub metadata: serde_json::Value,
}

// Chat响应
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatResponse {
    pub response: String,
    pub extracted_rule: Option<serde_json::Value>,
    #[serde(default)]
    pub needs_clarification: bool,
    #[serde(default)]
    pub clarification_questions: Vec<String>,
}

// LLM配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LLMConfig {
    pub api_key: String,
    #[serde(default = "default_preset")]
    pub preset: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub base_url: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
}

fn default_preset() -> String {
    "kimi".to_string()
}

// 分析请求
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalyzeRequest {
    pub file_path: String,
    pub user_requirement: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub user_naming_rule: Option<String>,
    pub llm_config: LLMConfig,
    #[serde(default = "default_chunk_size")]
    pub chunk_size: i32,
    #[serde(default = "default_overlap_size")]
    pub overlap_size: i32,
}

fn default_chunk_size() -> i32 {
    30
}

fn default_overlap_size() -> i32 {
    10
}

// 分析结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AnalyzeResult {
    pub chapters: Vec<Chapter>,
    pub strategy: String,
    pub valid: bool,
    #[serde(default)]
    pub issues: Vec<String>,
    #[serde(default)]
    pub warnings: Vec<String>,
}

// 拆分请求
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SplitRequest {
    pub file_path: String,
    pub output_dir: String,
    pub chapters: Vec<Chapter>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub filename_template: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub selected_chapters: Option<Vec<Chapter>>,
}

// 拆分结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SplitResult {
    pub files: Vec<SplitFile>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SplitFile {
    pub filename: String,
    pub path: String,
    pub page_count: i32,
    pub file_size: i64,
    pub success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

// ==================== 辅助函数 ====================

// 获取Python引擎目录
fn get_python_engine_dir() -> std::path::PathBuf {
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
    } else {
        // 在发布模式下，Python引擎应该在资源目录中
        exe_dir.join("python_engine")
    }
}

// 获取主处理器脚本路径
fn get_main_processor_path() -> std::path::PathBuf {
    get_python_engine_dir().join("cli.py")
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

// ==================== 命令函数 ====================

// 测试LLM连接
#[command]
async fn test_llm_connection<R: Runtime>(
    window: Window<R>,
    llm_config: LLMConfig,
) -> Result<serde_json::Value, String> {
    let processor_path = get_main_processor_path();
    let python_path = get_python_path();

    if !processor_path.exists() {
        return Err(format!("找不到主处理器: {:?}", processor_path));
    }

    // 序列化配置
    let config_json = serde_json::to_string(&llm_config)
        .map_err(|e| format!("序列化配置失败: {}", e))?;

    let mut child = Command::new(&python_path)
        .arg(&processor_path)
        .arg("--action")
        .arg("test_connection")
        .arg("--llm-config")
        .arg(&config_json)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("启动Python进程失败: {}", e))?;

    let stdout = child.stdout.take().ok_or("无法获取stdout")?;
    let stderr = child.stderr.take().ok_or("无法获取stderr")?;

    let reader = BufReader::new(stdout);
    let mut lines = reader.lines();

    let mut result: Option<serde_json::Value> = None;
    let mut error_output = String::new();

    while let Ok(Some(line)) = lines.next_line().await {
        if let Ok(json) = serde_json::from_str::<serde_json::Value>(&line) {
            result = Some(json);
        }
    }

    let mut stderr_lines = BufReader::new(stderr).lines();
    while let Ok(Some(line)) = stderr_lines.next_line().await {
        error_output.push_str(&line);
        error_output.push('\n');
    }

    let status = child.wait().await.map_err(|e| format!("等待进程失败: {}", e))?;

    if !status.success() {
        return Err(error_output.trim().to_string());
    }

    result.ok_or_else(|| "未收到响应".to_string())
}

// 处理Chat消息
#[command]
async fn process_chat_message<R: Runtime>(
    window: Window<R>,
    message: ChatMessage,
    llm_config: LLMConfig,
) -> Result<ChatResponse, String> {
    let processor_path = get_main_processor_path();
    let python_path = get_python_path();

    if !processor_path.exists() {
        return Err(format!("找不到主处理器: {:?}", processor_path));
    }

    // 序列化消息和配置
    let message_json = serde_json::to_string(&message)
        .map_err(|e| format!("序列化消息失败: {}", e))?;
    let config_json = serde_json::to_string(&llm_config)
        .map_err(|e| format!("序列化配置失败: {}", e))?;

    let mut child = Command::new(&python_path)
        .arg(&processor_path)
        .arg("--action")
        .arg("chat")
        .arg("--message")
        .arg(&message_json)
        .arg("--llm-config")
        .arg(&config_json)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("启动Python进程失败: {}", e))?;

    let stdout = child.stdout.take().ok_or("无法获取stdout")?;
    let stderr = child.stderr.take().ok_or("无法获取stderr")?;

    let reader = BufReader::new(stdout);
    let mut lines = reader.lines();

    let mut response: Option<ChatResponse> = None;
    let mut error_output = String::new();

    while let Ok(Some(line)) = lines.next_line().await {
        if let Ok(json) = serde_json::from_str::<serde_json::Value>(&line) {
            if let Some(resp) = json.get("response") {
                response = serde_json::from_value::<ChatResponse>(json)
                    .ok();
            }
        }
    }

    // 读取错误输出
    let mut stderr_lines = BufReader::new(stderr).lines();
    while let Ok(Some(line)) = stderr_lines.next_line().await {
        error_output.push_str(&line);
        error_output.push('\n');
    }

    let status = child.wait().await.map_err(|e| format!("等待进程失败: {}", e))?;

    if !status.success() {
        return Err(error_output.trim().to_string());
    }

    response.ok_or_else(|| "未收到响应".to_string())
}

// 分析PDF
#[command]
async fn analyze_pdf<R: Runtime>(
    window: Window<R>,
    request: AnalyzeRequest,
) -> Result<AnalyzeResult, String> {
    let processor_path = get_main_processor_path();
    let python_path = get_python_path();

    if !processor_path.exists() {
        return Err(format!("找不到主处理器: {:?}", processor_path));
    }

    // 检查PDF文件是否存在
    if !std::path::Path::new(&request.file_path).exists() {
        return Err(format!("PDF文件不存在: {}", request.file_path));
    }

    // 序列化请求
    let request_json = serde_json::to_string(&request)
        .map_err(|e| format!("序列化请求失败: {}", e))?;

    let mut child = Command::new(&python_path)
        .arg(&processor_path)
        .arg("--action")
        .arg("analyze")
        .arg("--request")
        .arg(&request_json)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("启动Python进程失败: {}", e))?;

    let stdout = child.stdout.take().ok_or("无法获取stdout")?;
    let stderr = child.stderr.take().ok_or("无法获取stderr")?;
    let mut stderr_lines = BufReader::new(stderr).lines();

    let reader = BufReader::new(stdout);
    let mut lines = reader.lines();

    let mut result: Option<AnalyzeResult> = None;
    let mut last_progress = 0.0;
    let mut error_output = String::new();

    while let Ok(Some(line)) = lines.next_line().await {
        if let Ok(json) = serde_json::from_str::<serde_json::Value>(&line) {
            match json.get("type").and_then(|t| t.as_str()) {
                Some("progress") => {
                    let progress = json.get("progress").and_then(|p| p.as_f64()).unwrap_or(0.0);
                    let message = json.get("message").and_then(|m| m.as_str()).unwrap_or("");
                    let stage = json.get("stage").and_then(|s| s.as_str()).unwrap_or("analyzing");

                    if progress - last_progress >= 1.0 || progress >= 99.0 {
                        last_progress = progress;
                        let _ = window.emit("analyze-progress", serde_json::json!({
                            "progress": progress,
                            "message": message,
                            "stage": stage,
                        }));
                    }
                }
                Some("analysis_complete") | Some("split_complete") | Some("complete") => {
                    let _ = window.emit("analyze-debug", serde_json::json!({
                        "message": "收到完成事件",
                        "data": json.clone()
                    }));
                    if let Some(data) = json.get("chapters").or_else(|| json.get("data")) {
                        let _ = window.emit("analyze-debug", serde_json::json!({
                            "message": "尝试解析 chapters",
                            "data": data.clone()
                        }));

                        // 先打印原始数据用于调试
                        eprintln!("[DEBUG] chapters 原始数据: {}", data);

                        // 尝试解析
                        match serde_json::from_value::<Vec<Chapter>>(data.clone()) {
                            Ok(chapters) => {
                                let _ = window.emit("analyze-debug", serde_json::json!({
                                    "message": format!("成功解析 {} 个章节", chapters.len()),
                                    "count": chapters.len(),
                                    "first_chapter": if !chapters.is_empty() {
                                        Some(&chapters[0])
                                    } else {
                                        None
                                    }
                                }));
                                result = Some(AnalyzeResult {
                                    chapters,
                                    strategy: json.get("strategy")
                                        .and_then(|s| s.as_str())
                                        .unwrap_or("llm")
                                        .to_string(),
                                    valid: json.get("valid")
                                        .and_then(|v| v.as_bool())
                                        .unwrap_or(true),
                                    issues: json.get("issues")
                                        .and_then(|i| i.as_array())
                                        .map(|a| a.to_vec())
                                        .into_iter()
                                        .filter_map(|v| v.as_str().map(|s| s.to_string()))
                                        .collect())
                                        .unwrap_or_default(),
                                    warnings: json.get("warnings")
                                        .and_then(|w| w.as_array())
                                        .map(|w| w.to_vec())
                                        .into_iter()
                                        .filter_map(|v| v.as_str().map(|s| s.to_string()))
                                        .collect())
                                        .unwrap_or_default(),
                                });
                            }
                            Err(e) => {
                                eprintln!("[DEBUG] 章节解析失败: {}", e);
                                let _ = window.emit("analyze-debug", serde_json::json!({
                                    "message": format!("chapters 解析失败: {}", e),
                                    "data": data.to_string()
                                }));
                            }
                        }
                    } else {
                        let _ = window.emit("analyze-debug", serde_json::json!({
                            "message": "未找到 chapters 或 data 字段",
                            "json": json.to_string()
                        }));
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

    while let Ok(Some(line)) = stderr_lines.next_line().await {
        error_output.push_str(&line);
        error_output.push('\n');
    }

    let status = child.wait().await.map_err(|e| format!("等待进程失败: {}", e))?;

    if !status.success() {
        eprintln!("[DEBUG] 进程退出状态: {}, 错误输出: {}", status, error_output);
        return Err(error_output.trim().to_string());
    }

    eprintln!("[DEBUG] 最终 result: {:?}", result.is_some());
    result.ok_or_else(|| "未收到分析结果".to_string())
}

// 拆分PDF
#[command]
async fn split_pdf<R: Runtime>(
    window: Window<R>,
    request: SplitRequest,
) -> Result<SplitResult, String> {
    let processor_path = get_main_processor_path();
    let python_path = get_python_path();

    if !processor_path.exists() {
        return Err(format!("找不到主处理器: {:?}", processor_path));
    }

    // 序列化请求
    let request_json = serde_json::to_string(&request)
        .map_err(|e| format!("序列化请求失败: {}", e))?;

    let mut child = Command::new(&python_path)
        .arg(&processor_path)
        .arg("--action")
        .arg("split")
        .arg("--request")
        .arg(&request_json)
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
                Some("split_complete") | Some("complete") => {
                    if let Some(data) = json.get("results").or_else(|| json.get("files")) {
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

    while let Ok(Some(line)) = stderr_lines.next_line().await {
        error_output.push_str(&line);
        error_output.push('\n');
    }

    let status = child.wait().await.map_err(|e| format!("等待进程失败: {}", e))?;

    if !status.success() {
        return Err(error_output.trim().to_string());
    }

    Ok(SplitResult { files })
}

fn main() {
    Builder::default()
        .invoke_handler(generate_handler![
            test_llm_connection,
            process_chat_message,
            analyze_pdf,
            split_pdf
        ])
        .run(generate_context!())
        .expect("运行Tauri应用时出错");
}
