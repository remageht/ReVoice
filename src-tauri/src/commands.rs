/// Tauri commands exposed to the frontend.
use anyhow::Result;
use tauri::{AppHandle, State};

use crate::AppState;


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

/// Universal backend request proxy implementation.
pub async fn backend_request_impl(
    method: &str,
    path: &str,
    body: Option<serde_json::Value>,
    base_url: &str,
) -> Result<serde_json::Value, String> {
    use base64::Engine;

    let clean_path = if let Some(stripped) = path.strip_prefix('/') {
        stripped
    } else {
        path
    };
    let url = format!("{}/{}", base_url, clean_path);
    log::info!("backend_request [Rust proxy]: {} {} (has_body: {})", method, clean_path, body.is_some());
    let client = reqwest::Client::new();
    let timeout = std::time::Duration::from_secs(120);

    let method_upper = method.to_uppercase();
    let mut req = match method_upper.as_str() {
        "GET" => client.get(&url),
        "POST" => client.post(&url),
        "PATCH" => client.patch(&url),
        "PUT" => client.put(&url),
        "DELETE" => client.delete(&url),
        _ => return Err(format!("Неподдерживаемый HTTP метод: {}", method)),
    };

    req = req.timeout(timeout);

    if let Some(b) = &body {
        if b.get("_multipart").and_then(|v| v.as_bool()).unwrap_or(false) {
            let ref_text = b.get("reference_text").and_then(|v| v.as_str()).unwrap_or("");
            let file_name = b.get("file_name").and_then(|v| v.as_str()).unwrap_or("sample.wav");
            let b64 = b.get("file_base64").and_then(|v| v.as_str()).unwrap_or("");
            let audio_bytes = base64::engine::general_purpose::STANDARD
                .decode(b64)
                .map_err(|e| format!("Base64 decode error: {}", e))?;

            let part = reqwest::multipart::Part::bytes(audio_bytes)
                .file_name(file_name.to_string())
                .mime_str("audio/wav")
                .unwrap_or_else(|_| reqwest::multipart::Part::bytes(vec![]));

            let form = reqwest::multipart::Form::new()
                .text("reference_text", ref_text.to_string())
                .part("audio", part);

            req = req.multipart(form);
        } else {
            req = req.json(b);
        }
    }

    let response = req
        .send()
        .await
        .map_err(|e| format!("Ошибка подключения к бэкенду: {}", e))?;

    let status = response.status();
    let bytes = response
        .bytes()
        .await
        .map_err(|e| format!("Ошибка чтения ответа бэкенда: {}", e))?;

    let json_val: serde_json::Value = if bytes.is_empty() {
        serde_json::Value::Null
    } else {
        serde_json::from_slice(&bytes).unwrap_or_else(|_| {
            serde_json::Value::String(String::from_utf8_lossy(&bytes).to_string())
        })
    };

    if !status.is_success() {
        let err_msg = if let Some(detail) = json_val.get("detail").and_then(|d| d.as_str()) {
            detail.to_string()
        } else if json_val.is_string() {
            json_val.as_str().unwrap().to_string()
        } else {
            format!("HTTP {}: {}", status, json_val)
        };
        return Err(err_msg);
    }

    Ok(json_val)
}

/// Universal backend request proxy for frontend when webview loopback fails.
#[tauri::command]
pub async fn backend_request(
    method: String,
    path: String,
    body: Option<serde_json::Value>,
    state: State<'_, AppState>,
) -> Result<serde_json::Value, String> {
    let base_url = state.backend_url.lock().unwrap().clone();
    backend_request_impl(&method, &path, body, &base_url).await
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

#[cfg(test)]
mod tests {
    use super::*;
    use base64::Engine;

    const BASE_URL: &str = "http://127.0.0.1:7851";

    #[tokio::test]
    async fn test_backend_request_health() {
        let res = backend_request_impl("GET", "/api/health", None, BASE_URL).await;
        assert!(res.is_ok(), "health check failed: {:?}", res);
        let val = res.unwrap();
        assert_eq!(val["status"], "ok");
    }

    #[tokio::test]
    async fn test_backend_request_crud_and_multipart() {
        // 1. Create profile
        let create_body = serde_json::json!({
            "name": "Егор Rust Proxy Test",
            "language": "ru"
        });
        let res = backend_request_impl("POST", "/api/profiles", Some(create_body), BASE_URL).await;
        assert!(res.is_ok(), "create profile failed: {:?}", res);
        let profile = res.unwrap();
        let profile_id = profile["id"].as_str().expect("profile id").to_string();

        // 2. Add sample with multipart proxy
        let sample_wav = std::path::Path::new(r"C:\dev\voices\egorka_adult.wav");
        if sample_wav.exists() {
            let wav_bytes = std::fs::read(sample_wav).expect("read wav");
            let b64 = base64::engine::general_purpose::STANDARD.encode(&wav_bytes);
            let multipart_body = serde_json::json!({
                "_multipart": true,
                "reference_text": "Привет! Это тестовый эталон голоса для проверки синтеза речи.",
                "file_name": "egorka_adult.wav",
                "file_base64": b64
            });
            let sample_res = backend_request_impl(
                "POST",
                &format!("/api/profiles/{}/samples", profile_id),
                Some(multipart_body),
                BASE_URL,
            ).await;
            assert!(sample_res.is_ok(), "multipart upload failed: {:?}", sample_res);
            let sample = sample_res.unwrap();
            assert_eq!(sample["is_valid"], true);
        }

        // 3. Delete profile
        let del_res = backend_request_impl(
            "DELETE",
            &format!("/api/profiles/{}", profile_id),
            None,
            BASE_URL,
        ).await;
        assert!(del_res.is_ok(), "delete profile failed: {:?}", del_res);
    }
}

