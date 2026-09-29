/// Global hotkey registration.
/// Ctrl+Shift+V — синтез текста из буфера обмена в активный голос.
use anyhow::Result;
use tauri::{AppHandle, Emitter};
use tauri_plugin_global_shortcut::{GlobalShortcutExt, Shortcut, ShortcutState};

const SYNTH_HOTKEY: &str = "Ctrl+Shift+V";

pub fn register_hotkeys(handle: &AppHandle) -> Result<()> {
    let shortcut: Shortcut = SYNTH_HOTKEY.parse()
        .map_err(|e| anyhow::anyhow!("Invalid shortcut {}: {}", SYNTH_HOTKEY, e))?;

    handle.global_shortcut().on_shortcut(shortcut, |app, _shortcut, event| {
        if event.state == ShortcutState::Pressed {
            log::info!("Global hotkey triggered: {}", SYNTH_HOTKEY);
            let app_handle = app.clone();
            tauri::async_runtime::spawn(async move {
                handle_synth_hotkey(&app_handle).await;
            });
        }
    })?;

    log::info!("Global hotkey registered: {}", SYNTH_HOTKEY);
    Ok(())
}

async fn handle_synth_hotkey(app: &AppHandle) {
    // Read clipboard text
    use tauri_plugin_clipboard_manager::ClipboardExt;
    let text = match app.clipboard().read_text() {
        Ok(t) if !t.trim().is_empty() => t,
        _ => {
            log::warn!("Clipboard empty or not text, skipping synthesis");
            return;
        }
    };

    log::info!("Hotkey: synthesizing {} chars from clipboard", text.len());

    // Emit to frontend to trigger synthesis
    app.emit("hotkey-synth", serde_json::json!({
        "text": text,
        "source": "clipboard_hotkey",
    })).ok();
}
