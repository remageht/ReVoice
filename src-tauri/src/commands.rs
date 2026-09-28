/// Tauri commands exposed to the frontend.
use anyhow::Result;
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, State};

use crate::AppState;

#[derive(Serialize)]
pub struct HealthResponse {
    pub status: String,
    pub version: String,
}

/// Open a native file dialog for audio import.
#[tauri::command]
pub async fn open_file_dialog(
    title: String,
    filters: Vec<(String, Vec<String>)>,
) -> Result<Option<String>, String> {
    let mut dialog = rfd::AsyncFileDialog::new().set_title(&title);
    for (name, exts) in &filters {
        let ext_refs: Vec<&str> = exts.iter().map(|e| e.as_str()).collect();
        dialog = dialog.add_filter(name, &ext_refs);
    }
    let file = dialog.pick_file().await;
    Ok(file.map(|f| f.path().to_string_lossy().to_string()))
}

/// Open a native save dialog.
#[tauri::command]
pub async fn save_file_dialog(
    title: String,
    default_name: String,
    filters: Vec<(String, Vec<String>)>,
) -> Result<Option<String>, String> {
    let mut dialog = rfd::AsyncFileDialog::new()
        .set_title(&title)
        .set_file_name(&default_name);
    for (name, exts) in &filters {
        let ext_refs: Vec<&str> = exts.iter().map(|e| e.as_str()).collect();
        dialog = dialog.add_filter(name, &ext_refs);
    }
    let file = dialog.save_file().await;
    Ok(file.map(|f| f.path().to_string_lossy().to_string()))
}

/// Get the application data directory.
#[tauri::command]
pub fn get_data_dir() -> String {
    dirs::data_dir()
        .map(|d| d.join("Revoice").to_string_lossy().to_string())
        .unwrap_or_else(|| "~/Revoice".to_string())
}

/// Get the backend URL.
#[tauri::command]
pub fn get_backend_url(state: State<AppState>) -> String {
    state.backend_url.lock().unwrap().clone()
}

/// Ping the backend health endpoint.
#[tauri::command]
pub async fn health_check(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    let url = format!("{}/api/health", state.backend_url.lock().unwrap());
    let client = reqwest::Client::new();
    match client
        .get(&url)
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
    {
        Ok(r) => r.json::<serde_json::Value>().await.map_err(|e| e.to_string()),
        Err(e) => Err(format!("Backend недоступен: {}", e)),
    }
}

/// Restart the Python sidecar.
#[tauri::command]
pub async fn restart_sidecar(app: AppHandle) -> Result<(), String> {
    crate::sidecar::start_sidecar(&app)
        .await
        .map_err(|e| e.to_string())
}

/// Synthesize text from clipboard using the active profile.
/// Called by the global hotkey handler.
#[tauri::command]
pub async fn synthesize_clipboard(
    text: String,
    profile_id: String,
    engine: String,
    state: State<'_, AppState>,
) -> Result<serde_json::Value, String> {
    let base_url = state.backend_url.lock().unwrap().clone();
    let url = format!("{}/api/synthesize", base_url);
    let client = reqwest::Client::new();

    let body = serde_json::json!({
        "profile_id": profile_id,
        "text": text,
        "engine": engine,
        "language": "ru",
    });

    match client
        .post(&url)
        .json(&body)
        .timeout(std::time::Duration::from_secs(120))
        .send()
        .await
    {
        Ok(r) => r.json::<serde_json::Value>().await.map_err(|e| e.to_string()),
        Err(e) => Err(format!("Синтез не удался: {}", e)),
    }
}
