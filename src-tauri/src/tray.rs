/// System tray setup for ReVoice.
use anyhow::Result;
use tauri::{
    App,
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::TrayIconBuilder,
    Manager,
};

pub fn setup_tray(app: &mut App) -> Result<()> {
    let show = MenuItem::with_id(app, "show", "Показать ReVoice", true, None::<&str>)?;
    let hide = MenuItem::with_id(app, "hide", "Скрыть ReVoice", true, None::<&str>)?;
    let sep = PredefinedMenuItem::separator(app)?;
    let quit = MenuItem::with_id(app, "quit", "Выйти", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[&show, &hide, &sep, &quit])?;

    let _tray = TrayIconBuilder::new()
        .menu(&menu)
        .show_menu_on_left_click(false)
        .tooltip("ReVoice — студия голоса")
        .on_menu_event(|app, event| match event.id.as_ref() {
            "show" => {
                if let Some(window) = app.get_webview_window("main") {
                    window.show().ok();
                    window.set_focus().ok();
                }
            }
            "hide" => {
                if let Some(window) = app.get_webview_window("main") {
                    window.hide().ok();
                }
            }
            "quit" => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let tauri::tray::TrayIconEvent::Click {
                button: tauri::tray::MouseButton::Left,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    if window.is_visible().unwrap_or(false) {
                        window.hide().ok();
                    } else {
                        window.show().ok();
                        window.set_focus().ok();
                    }
                }
            }
        })
        .build(app)?;

    Ok(())
}
