use std::sync::Mutex;
use tauri::Manager;

mod sidecar;
mod tray;
mod commands;
mod hotkey;

use sidecar::SidecarState;

/// Application state shared across commands.
pub struct AppState {
    pub sidecar: Mutex<SidecarState>,
    pub backend_url: Mutex<String>,
}

pub fn run() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::from_default_env()
                .add_directive("revoice=debug".parse().unwrap()),
        )
        .init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--minimized"]),
        ))
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_log::Builder::new()
            .target(tauri_plugin_log::Target::new(
                tauri_plugin_log::TargetKind::LogDir { file_name: Some("revoice".into()) },
            ))
            .build())
        .setup(|app| {
            let handle = app.handle().clone();

            // Initialize state
            app.manage(AppState {
                sidecar: Mutex::new(SidecarState::new()),
                backend_url: Mutex::new("http://127.0.0.1:7851".to_string()),
            });

            // Setup system tray
            tray::setup_tray(app)?;

            // Start Python sidecar
            let handle_clone = handle.clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = sidecar::start_sidecar(&handle_clone).await {
                    tracing::error!("Failed to start sidecar: {}", e);
                }
            });

            // Register global hotkey
            hotkey::register_hotkeys(&handle)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::open_file_dialog,
            commands::save_file_dialog,
            commands::get_data_dir,
            commands::get_backend_url,
            commands::health_check,
            commands::restart_sidecar,
            commands::synthesize_clipboard,
        ])
        .run(tauri::generate_context!())
        .expect("ReVoice failed to start");
}
