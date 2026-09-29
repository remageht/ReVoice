/// Python sidecar management.
///
/// Production mode: after bootstrap, spawns venv/Scripts/python.exe -m uvicorn revoice.main:app
/// Dev mode: assumes backend is already running on port 7851
use anyhow::{Context, Result};
use std::path::PathBuf;
use tauri::{AppHandle, Manager, Emitter};

const BACKEND_PORT: u16 = 7851;

pub struct SidecarState {
    pub is_running: bool,
    pub pid: Option<u32>,
}

impl SidecarState {
    pub fn new() -> Self {
        Self {
            is_running: false,
            pid: None,
        }
    }
}

pub async fn start_sidecar(handle: &AppHandle) -> Result<()> {
    tracing::info!("Запуск ReVoice Python бэкенда...");

    let data_dir = get_data_dir();
    let is_dev = is_dev_mode();

    if is_dev {
        tracing::warn!(
            "Dev-режим: ожидаем бэкенд на порту {}. Запустите: cd backend && uv run uvicorn revoice.main:app --port {}",
            BACKEND_PORT,
            BACKEND_PORT
        );
        if wait_for_backend(BACKEND_PORT, 5).await.is_ok() {
            handle.emit("sidecar-ready", serde_json::json!({
                "url": format!("http://127.0.0.1:{}", BACKEND_PORT)
            })).ok();
        } else {
            handle.emit("sidecar-error", serde_json::json!({
                "message": "Бэкенд не запущен. В dev-режиме запустите его вручную."
            })).ok();
        }
        return Ok(());
    }

    // Production mode
    // 1. Bootstrap if needed
    if !crate::bootstrap::is_bootstrapped(&data_dir) {
        tracing::info!("Первый запуск — инициализация окружения...");
        handle.emit("bootstrap-start", serde_json::json!({
            "message": "Первый запуск: подготавливаем окружение..."
        })).ok();

        crate::bootstrap::run_bootstrap(handle, data_dir.clone())
            .await
            .context("Ошибка инициализации окружения Python")?;
    }

    // 2. Start uvicorn via venv python
    let python_exe = crate::bootstrap::venv_python_exe(&data_dir);
    if !python_exe.exists() {
        anyhow::bail!(
            "Python не найден: {:?}. Попробуйте переустановить приложение.",
            python_exe
        );
    }

    // Backend source: after bootstrap, revoice/ was extracted from backend.zip into runtime/revoice/
    let backend_dir = data_dir.join("runtime").join("revoice");

    if !backend_dir.join("main.py").exists() {
        anyhow::bail!(
            "Бэкенд не найден: {:?}. Переустановите приложение и дождитесь завершения первоначальной настройки.",
            backend_dir
        );
    }

    tracing::info!("Запускаем uvicorn: python={:?} cwd={:?}", python_exe, backend_dir);

    let child = std::process::Command::new(&python_exe)
        .args([
            "-m", "uvicorn",
            "revoice.main:app",
            "--host", "127.0.0.1",
            "--port", &BACKEND_PORT.to_string(),
            "--log-level", "warning",
        ])
        .current_dir(&backend_dir)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .context("Не удалось запустить Python-бэкенд")?;

    let pid = child.id();
    tracing::info!("Бэкенд запущен (PID {}), ожидаем готовности...", pid);

    // Update state
    if let Some(state) = handle.try_state::<crate::AppState>() {
        if let Ok(mut sc) = state.sidecar.lock() {
            sc.is_running = true;
            sc.pid = Some(pid);
        }
    }

    // Wait for backend to be ready (up to 90 seconds — uvicorn cold start)
    match wait_for_backend(BACKEND_PORT, 90).await {
        Ok(()) => {
            tracing::info!("Бэкенд готов на порту {}", BACKEND_PORT);
            handle.emit("sidecar-ready", serde_json::json!({
                "url": format!("http://127.0.0.1:{}", BACKEND_PORT)
            })).ok();
        }
        Err(e) => {
            tracing::error!("Бэкенд не запустился за 90 сек: {}", e);
            handle.emit("sidecar-error", serde_json::json!({
                "message": format!("Бэкенд не запустился: {}", e)
            })).ok();
        }
    }

    // Keep child alive (don't drop — this kills the process)
    // We store it so it lives as long as the app
    std::mem::forget(child);

    Ok(())
}

/// Poll the backend health endpoint until it responds or timeout.
async fn wait_for_backend(port: u16, timeout_secs: u64) -> Result<()> {
    let url = format!("http://127.0.0.1:{}/api/health", port);
    let client = reqwest::Client::new();
    let deadline =
        std::time::Instant::now() + std::time::Duration::from_secs(timeout_secs);

    loop {
        if std::time::Instant::now() > deadline {
            anyhow::bail!("Бэкенд не ответил за {} секунд", timeout_secs);
        }

        match client
            .get(&url)
            .timeout(std::time::Duration::from_secs(2))
            .send()
            .await
        {
            Ok(resp) if resp.status().is_success() => return Ok(()),
            _ => {
                tokio::time::sleep(std::time::Duration::from_millis(500)).await;
            }
        }
    }
}

/// Get the application data directory (%APPDATA%\Revoice on Windows)
fn get_data_dir() -> PathBuf {
    if let Ok(appdata) = std::env::var("APPDATA") {
        PathBuf::from(appdata).join("Revoice")
    } else if let Some(home) = dirs::home_dir() {
        home.join(".revoice")
    } else {
        PathBuf::from("C:\\Users\\Public\\Revoice")
    }
}

/// Detect dev mode: no bootstrap marker AND REVOICE_DEV env is set,
/// OR running from cargo (no bundle resources)
fn is_dev_mode() -> bool {
    if std::env::var("REVOICE_DEV").is_ok() {
        return true;
    }
    // Heuristic: if exe is in target/debug or target/release, it's dev
    if let Ok(exe) = std::env::current_exe() {
        let exe_str = exe.to_string_lossy().to_lowercase();
        if exe_str.contains("target\\debug") || exe_str.contains("target/debug") {
            return true;
        }
    }
    false
}
