use std::sync::Mutex;
use tauri::Manager;

mod sidecar;
mod tray;
mod commands;
mod hotkey;
mod bootstrap;

use sidecar::SidecarState;

/// Application state shared across commands.
pub struct AppState {
    pub sidecar: Mutex<SidecarState>,
    pub backend_url: Mutex<String>,
}

pub fn run() {
    // Логирование — только через tauri_plugin_log (ниже).
    // Свой tracing_subscriber::init() здесь ЗАПРЕЩЁН: двойная инициализация
    // глобального логгера = паника "attempted to set a logger...".
    // Все вызовы — только log::info!/warn!/error!/debug! (уходят в файл revoice.log).
    tauri::Builder::default()
        // Один инстанс навсегда: повторный запуск фокусирует существующее окно,
        // а не плодит GUI/бэкенды с дракой за порт 7851 и SQLite (причина «вечных спиннеров»).
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                window.show().ok();
                window.set_focus().ok();
            }
        }))
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
                    log::error!("Failed to start sidecar: {}", e);
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
            commands::backend_request,
            commands::restart_sidecar,
            commands::synthesize_clipboard,
        ])
        .run(tauri::generate_context!())
        .expect("ReVoice failed to start");
}
