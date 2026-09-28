/// Python sidecar management.
/// The Python backend runs as a bundled PyInstaller executable.
/// On dev: spawns `uvicorn revoice.main:app` via tauri shell.
use anyhow::{Context, Result};
use std::sync::Arc;
use tauri::AppHandle;
use tauri_plugin_shell::ShellExt;

const BACKEND_PORT: u16 = 7851;
const SIDECAR_NAME: &str = "revoice-server";

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
    tracing::info!("Starting ReVoice Python sidecar...");

    let shell = handle.shell();

    // Try to find the sidecar binary (bundled)
    // Falls back to dev mode: python -m uvicorn
    let sidecar_result = shell.sidecar(SIDECAR_NAME);

    match sidecar_result {
        Ok(sidecar_cmd) => {
            tracing::info!("Starting bundled sidecar: {}", SIDECAR_NAME);
            let (_rx, child) = sidecar_cmd
                .spawn()
                .context("Failed to spawn Python sidecar")?;

            // Update state
            if let Some(state) = handle.try_state::<crate::AppState>() {
                if let Ok(mut sc) = state.sidecar.lock() {
                    sc.is_running = true;
                    // child.pid() would be nice but tauri returns Child not std::Child
                }
            }

            tracing::info!("Sidecar started, waiting for backend to become ready...");
            wait_for_backend(BACKEND_PORT, 60).await?;
            tracing::info!("Backend is ready on port {}", BACKEND_PORT);

            // Emit event to frontend
            handle.emit("sidecar-ready", serde_json::json!({
                "url": format!("http://127.0.0.1:{}", BACKEND_PORT)
            })).ok();
        }
        Err(_) => {
            // Dev mode: assume backend is already running or will be started manually
            tracing::warn!(
                "Sidecar binary '{}' not found — running in dev mode. \
                 Start backend manually: cd backend && uv run uvicorn revoice.main:app --port {}",
                SIDECAR_NAME,
                BACKEND_PORT
            );

            // In dev mode still wait briefly for backend
            if wait_for_backend(BACKEND_PORT, 5).await.is_ok() {
                handle.emit("sidecar-ready", serde_json::json!({
                    "url": format!("http://127.0.0.1:{}", BACKEND_PORT)
                })).ok();
            } else {
                handle.emit("sidecar-error", serde_json::json!({
                    "message": "Backend not available. Start it manually."
                })).ok();
            }
        }
    }

    Ok(())
}

/// Poll the backend health endpoint until it responds or timeout.
async fn wait_for_backend(port: u16, timeout_secs: u64) -> Result<()> {
    let url = format!("http://127.0.0.1:{}/api/health", port);
    let client = reqwest::Client::new();
    let deadline = std::time::Instant::now()
        + std::time::Duration::from_secs(timeout_secs);

    loop {
        if std::time::Instant::now() > deadline {
            anyhow::bail!("Backend did not start within {} seconds", timeout_secs);
        }

        match client.get(&url).timeout(std::time::Duration::from_secs(2)).send().await {
            Ok(resp) if resp.status().is_success() => return Ok(()),
            _ => {
                tokio::time::sleep(std::time::Duration::from_millis(500)).await;
            }
        }
    }
}
