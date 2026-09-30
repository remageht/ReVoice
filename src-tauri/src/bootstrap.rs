/// Bootstrap module — automatic Python runtime setup on first launch.
///
/// Flow:
/// 1. Check if runtime already exists at %APPDATA%\Revoice\runtime\python\python.exe
/// 2. If not: download embeddable Python 3.10 zip (~10 MB)
/// 3. Extract to %APPDATA%\Revoice\runtime\python\
/// 4. Download uv.exe (~10 MB)
/// 5. Use uv to create venv and install revoice backend
/// 6. Copy backend source from app bundle resources
/// 7. Emit bootstrap-progress events at every step

use anyhow::{Context, Result};
use std::path::{Path, PathBuf};
use tauri::{AppHandle, Emitter, Manager};

// Python 3.10 embeddable package for Windows x64
// (3.10 — проверенная связка: torch cu126 cp310 + qwen-tts 0.1.1, как прод-venv)
const PYTHON_URL: &str =
    "https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip";

// uv for Windows x64
const UV_URL: &str =
    "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip";

// torch CUDA wheel (PyPI отдаёт CPU; download.pytorch.org даёт 403 в ряде сетей).
// R2-зеркало + Mozilla UA не требуются здесь: качаем reqwest с дефолтным UA,
// при проблемах — тот же URL через curl -A "Mozilla/5.0".
// ВАЖНО: cp310 строго под embeddable 3.10 выше.
const TORCH_WHEEL_URL: &str = "https://download-r2.pytorch.org/whl/cu126/torch-2.14.0%2Bcu126-cp310-cp310-win_amd64.whl";
const TORCH_WHEEL_NAME: &str = "torch-2.14.0+cu126-cp310-cp310-win_amd64.whl";

/// Check if the Python runtime is already bootstrapped.
pub fn is_bootstrapped(data_dir: &Path) -> bool {
    let python_exe = runtime_python_exe(data_dir);
    python_exe.exists()
}

/// Return path to runtime python.exe
pub fn runtime_python_exe(data_dir: &Path) -> PathBuf {
    data_dir.join("runtime").join("python").join("python.exe")
}

/// Return path to venv python.exe (inside the uv-managed venv)
pub fn venv_python_exe(data_dir: &Path) -> PathBuf {
    data_dir
        .join("runtime")
        .join("venv")
        .join("Scripts")
        .join("python.exe")
}

/// Return path to uv.exe
fn uv_exe(data_dir: &Path) -> PathBuf {
    data_dir.join("runtime").join("uv.exe")
}

/// Emit a progress event to the frontend.
fn emit_progress(handle: &AppHandle, step: &str, pct: u8, message: &str) {
    handle
        .emit(
            "bootstrap-progress",
            serde_json::json!({
                "step": step,
                "pct": pct,
                "message": message,
            }),
        )
        .ok();
}

/// Run the full bootstrap process.
/// Returns Ok(()) when Python venv is ready and backend is installed.
pub async fn run_bootstrap(handle: &AppHandle, data_dir: PathBuf) -> Result<()> {
    let runtime_dir = data_dir.join("runtime");
    std::fs::create_dir_all(&runtime_dir)
        .context("Не удалось создать директорию runtime")?;

    let python_dir = runtime_dir.join("python");
    let uv_path = uv_exe(&data_dir);
    let venv_dir = runtime_dir.join("venv");

    // --- Step 1: Download embeddable Python ---
    emit_progress(handle, "python_download", 5, "Скачиваем Python 3.10...");

    if !python_dir.exists() {
        let zip_path = runtime_dir.join("python_embed.zip");
        download_with_progress(handle, PYTHON_URL, &zip_path, 5, 25, "Скачиваем Python 3.10")
            .await
            .context("Ошибка скачивания Python")?;

        emit_progress(handle, "python_extract", 30, "Распаковываем Python...");
        std::fs::create_dir_all(&python_dir)?;
        extract_zip(&zip_path, &python_dir).context("Ошибка распаковки Python")?;
        let _ = std::fs::remove_file(&zip_path);

        // Enable site-packages in embeddable Python
        fix_pth_file(&python_dir)?;
    } else {
        emit_progress(handle, "python_ok", 30, "Python уже установлен");
    }

    // --- Step 2: Download uv ---
    emit_progress(handle, "uv_download", 33, "Скачиваем менеджер пакетов uv...");

    if !uv_path.exists() {
        let uv_zip_path = runtime_dir.join("uv.zip");
        download_with_progress(handle, UV_URL, &uv_zip_path, 33, 50, "Скачиваем uv")
            .await
            .context("Ошибка скачивания uv")?;

        emit_progress(handle, "uv_extract", 52, "Распаковываем uv...");
        extract_zip_single(&uv_zip_path, &uv_path, "uv.exe")
            .context("Ошибка распаковки uv.exe")?;
        let _ = std::fs::remove_file(&uv_zip_path);
    } else {
        emit_progress(handle, "uv_ok", 52, "uv уже установлен");
    }

    // --- Step 3: Create venv ---
    emit_progress(handle, "venv_create", 55, "Создаём виртуальное окружение...");

    if !venv_dir.exists() {
        let status = std::process::Command::new(&uv_path)
            .args(["venv", venv_dir.to_str().unwrap(), "--python", "3.10"])
            .env("UV_PYTHON", runtime_python_exe(&data_dir).to_str().unwrap())
            .status()
            .context("Не удалось запустить uv venv")?;

        if !status.success() {
            anyhow::bail!("uv venv завершился с ошибкой: {:?}", status.code());
        }
    } else {
        emit_progress(handle, "venv_ok", 55, "Виртуальное окружение уже существует");
    }

    // --- Step 4: Extract backend source from bundled zip ---
    emit_progress(handle, "backend_copy", 60, "Распаковываем бэкенд...");

    let backend_dest = runtime_dir.join("revoice");
    if !backend_dest.exists() {
        // backend.zip is bundled with the app in resource_dir
        let resource_dir = handle
            .path()
            .resource_dir()
            .context("Не удалось получить resource_dir")?;

        let backend_zip = resource_dir.join("backend.zip");
        if backend_zip.exists() {
            std::fs::create_dir_all(&backend_dest)?;
            extract_zip(&backend_zip, &backend_dest)
                .context("Ошибка распаковки backend.zip")?;
            log::info!("Backend extracted to: {:?}", backend_dest);
        } else {
            log::warn!("backend.zip not found at {:?} — будет попытка работы без него", backend_zip);
        }
    } else {
        emit_progress(handle, "backend_ok", 60, "Бэкенд уже распакован");
    }


    // --- Step 5: Install dependencies ---
    emit_progress(handle, "deps_install", 65, "Устанавливаем зависимости (это займёт несколько минут)...");

    let requirements_path = runtime_dir.join("requirements.txt");
    write_requirements(&requirements_path)?;

    let venv_pip = venv_dir.join("Scripts").join("pip.exe");
    let pip_cmd = if venv_pip.exists() { venv_pip } else {
        // Fallback: use uv pip install
        uv_path.clone()
    };

    // Use uv pip install for speed
    let pip_args: Vec<String> = if pip_cmd == uv_path {
        vec![
            "pip".to_string(),
            "install".to_string(),
            "-r".to_string(),
            requirements_path.to_str().unwrap().to_string(),
            "--python".to_string(),
            venv_python_exe(&data_dir).to_str().unwrap().to_string(),
        ]
    } else {
        vec![
            "install".to_string(),
            "-r".to_string(),
            requirements_path.to_str().unwrap().to_string(),
        ]
    };

    let status = std::process::Command::new(&pip_cmd)
        .args(&pip_args)
        .status()
        .context("Не удалось запустить установку зависимостей")?;

    if !status.success() {
        anyhow::bail!("Установка зависимостей завершилась с ошибкой: {:?}", status.code());
    }

    // --- Step 5b: torch (CUDA wheel или CPU) ---
    // PyPI отдаёт CPU-torch, а faster-whisper тянет его зависимостью.
    // NVIDIA есть → CUDA-колесо поверх с заменой (Qwen на GPU).
    // NVIDIA нет (AMD/Intel) → остаётся CPU-torch с PyPI, всё работает на CPU (медленно).
    // REVOICE_FORCE_CPU=1 принудительно включает CPU-режим (для тестов).
    let use_cuda = has_nvidia_gpu();
    if use_cuda {
        emit_progress(handle, "torch_check", 86, "Проверяем torch CUDA...");
    } else {
        emit_progress(handle, "torch_cpu", 86, "NVIDIA не найден — режим CPU (без CUDA-колеса)...");
        log::info!("No NVIDIA GPU (or REVOICE_FORCE_CPU=1): CPU torch will be used");
    }
    if use_cuda && !torch_cu126_ok(&data_dir) {
        emit_progress(handle, "torch_download", 86, "Качаем torch CUDA (~2.6 ГБ, долго)...");
        let wheel_path = runtime_dir.join(TORCH_WHEEL_NAME);
        download_with_progress(handle, TORCH_WHEEL_URL, &wheel_path, 86, 94, "Качаем torch CUDA")
            .await
            .context("Ошибка скачивания torch CUDA wheels")?;

        emit_progress(handle, "torch_install", 94, "Ставим torch CUDA поверх CPU-сборки...");
        let status = std::process::Command::new(&uv_path)
            .args([
                "pip", "install",
                "--python", venv_python_exe(&data_dir).to_str().unwrap(),
                wheel_path.to_str().unwrap(),
            ])
            .status()
            .context("Не удалось запустить установку torch")?;
        if !status.success() {
            anyhow::bail!("Установка torch CUDA завершилась с ошибкой: {:?}", status.code());
        }
        let _ = std::fs::remove_file(&wheel_path);
        if !torch_cu126_ok(&data_dir) {
            anyhow::bail!("torch CUDA не завёлся после установки (нужен torch 2.14.0+cu126)");
        }
    } else {
        emit_progress(handle, "torch_ok", 94, "torch CUDA уже на месте");
    }

    // --- Step 5c: torchaudio без зависимостей ---
    // Полная установка torchaudio снесла бы CUDA-torch (пин torch==X). Нужен только импорт.
    if !py_import_ok(&data_dir, "torchaudio") {
        emit_progress(handle, "torchaudio_install", 95, "Ставим torchaudio (без зависимостей)...");
        let status = std::process::Command::new(&uv_path)
            .args([
                "pip", "install", "--no-deps",
                "--python", venv_python_exe(&data_dir).to_str().unwrap(),
                "torchaudio",
            ])
            .status()
            .context("Не удалось запустить установку torchaudio")?;
        if !status.success() {
            anyhow::bail!("Установка torchaudio завершилась с ошибкой: {:?}", status.code());
        }
    }

    // --- Step 5d: финальная проверка ML-стека ---
    // GPU-машина: строгая проверка (cu126 + cuda True).
    // CPU-машина (AMD/Intel): достаточно импорта torch + qwen_tts (любой сборки).
    emit_progress(handle, "ml_check", 97, "Проверяем ML-стек...");
    let out = std::process::Command::new(venv_python_exe(&data_dir))
        .args(["-c", "import torch, qwen_tts, transformers; print(torch.__version__, torch.cuda.is_available(), transformers.__version__)"])
        .output()
        .context("Не удалось запустить проверку ML-стека")?;
    let txt = String::from_utf8_lossy(&out.stdout).to_string();
    log::info!("ML check: {}", txt.trim());
    let ml_ok = if use_cuda {
        txt.contains("2.14.0+cu126") && txt.contains("True")
    } else {
        out.status.success() && py_import_ok(&data_dir, "qwen_tts")
    };
    if !ml_ok {
        anyhow::bail!("ML-стек не готов: {}", txt.trim());
    }

    emit_progress(handle, "done", 100, "Окружение готово!");
    log::info!("Bootstrap complete. Runtime at: {:?}", runtime_dir);
    Ok(())
}

/// Проверка: в venv стоит torch 2.14.0+cu126 (а не CPU-сборка от faster-whisper).
fn torch_cu126_ok(data_dir: &Path) -> bool {
    let out = std::process::Command::new(venv_python_exe(data_dir))
        .args(["-c", "import torch; print(torch.__version__)"])
        .output();
    match out {
        Ok(o) if o.status.success() => {
            String::from_utf8_lossy(&o.stdout).contains("2.14.0+cu126")
        }
        _ => false,
    }
}

/// Есть ли NVIDIA GPU (nvidia-smi отвечает).
/// REVOICE_FORCE_CPU=1 принудительно возвращает false (тест CPU-режима).
fn has_nvidia_gpu() -> bool {
    if std::env::var("REVOICE_FORCE_CPU").is_ok() {
        return false;
    }
    std::process::Command::new("nvidia-smi")
        .arg("-L")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

/// Проверка импорта модуля в venv (для опциональных пакетов).
fn py_import_ok(data_dir: &Path, module: &str) -> bool {
    let code = format!("import {module}");
    std::process::Command::new(venv_python_exe(data_dir))
        .args(["-c", &code])
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

/// Write requirements.txt for backend.
// torch ставится ОТДЕЛЬНО колесом CUDA (см. шаг 5b): PyPI отдаёт CPU-сборку,
// а faster-whisper тянет её зависимостью — CUDA-колесо ставится последним с заменой.
fn write_requirements(path: &Path) -> Result<()> {
    let requirements = r#"fastapi==0.115.12
uvicorn[standard]==0.34.3
sqlalchemy==2.0.41
pydantic==2.11.7
pydantic-settings==2.9.1
aiosqlite==0.21.0
python-multipart==0.0.20
httpx==0.28.1
librosa==0.11.0
soundfile==0.14.0
numpy==1.26.4
scipy==1.15.3
einops==0.8.2
onnxruntime==1.23.2
sox==1.5.0
qwen-tts==0.1.1
transformers==4.57.3
accelerate==1.12.0
tokenizers==0.22.0
huggingface-hub==0.34.4
regex
safetensors
tqdm
faster-whisper==1.1.1
pedalboard==0.9.17
psutil==7.0.0
sse-starlette==2.2.1
imageio-ffmpeg>=0.5
mutagen>=1.47.0
"#;
    std::fs::write(path, requirements).context("Не удалось записать requirements.txt")?;
    Ok(())
}

/// Download file with progress events + RESUME.
/// Если файл уже частично скачан (обрыв), продолжает Range-запросом с конца,
/// а не начинает заново. Критично для гигабайтных колёс на медленном CDN.
async fn download_with_progress(
    handle: &AppHandle,
    url: &str,
    dest: &Path,
    pct_start: u8,
    pct_end: u8,
    label: &str,
) -> Result<()> {
    use tokio::io::AsyncWriteExt;

    log::info!("Downloading {} → {:?}", url, dest);

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(300))
        .user_agent("ReVoice/0.1.0")
        .build()?;

    // HEAD: узнаём полный размер для resume-проверки
    let total: u64 = client
        .head(url)
        .send()
        .await
        .ok()
        .and_then(|r| r.content_length())
        .unwrap_or(0);

    let have: u64 = std::fs::metadata(dest).map(|m| m.len()).unwrap_or(0);
    if total > 0 && have >= total && have > 0 {
        log::info!("{} уже скачан целиком ({} МБ), пропускаем", label, have / 1_048_576);
        return Ok(());
    }
    if have > 0 {
        log::info!("{}: резюм с {} МБ", label, have / 1_048_576);
    }

    let mut req = client.get(url);
    if have > 0 {
        req = req.header("Range", format!("bytes={}-", have));
    }
    let resp = req.send().await.context("HTTP request failed")?;
    // Сервер может проигнорировать Range (200 вместо 206) — тогда качаем заново
    let resumed = resp.status() == reqwest::StatusCode::PARTIAL_CONTENT;
    if !resumed && have > 0 {
        log::warn!("{}: сервер не поддержал resume, качаем заново", label);
    }

    let total = if total > 0 { total } else { resp.content_length().unwrap_or(0) };
    let mut downloaded: u64 = if resumed { have } else { 0 };

    let mut file = if resumed {
        tokio::fs::OpenOptions::new()
            .append(true)
            .open(dest)
            .await
            .context("Cannot open destination file for append")?
    } else {
        tokio::fs::File::create(dest)
            .await
            .context("Cannot create destination file")?
    };

    let mut stream = resp.bytes_stream();
    use futures_util::StreamExt;

    while let Some(chunk) = stream.next().await {
        let chunk = chunk.context("Stream error")?;
        file.write_all(&chunk).await.context("Write error")?;
        downloaded += chunk.len() as u64;

        if total > 0 {
            let frac = downloaded as f64 / total as f64;
            let pct = pct_start as f64 + frac * (pct_end - pct_start) as f64;
            let mb = downloaded as f64 / 1_048_576.0;
            let total_mb = total as f64 / 1_048_576.0;
            handle
                .emit(
                    "bootstrap-progress",
                    serde_json::json!({
                        "step": "download",
                        "pct": pct as u8,
                        "message": format!("{}: {:.1}/{:.1} МБ", label, mb, total_mb),
                    }),
                )
                .ok();
        }
    }

    file.flush().await?;
    // Финальная проверка размера
    let final_size = std::fs::metadata(dest).map(|m| m.len()).unwrap_or(0);
    if total > 0 && final_size != total {
        anyhow::bail!(
            "{}: размер не сошёлся (есть {} из {}), будет повтор при следующем запуске",
            label, final_size, total
        );
    }
    Ok(())
}

/// Extract all files from a ZIP archive to a directory.
fn extract_zip(zip_path: &Path, dest_dir: &Path) -> Result<()> {
    let file = std::fs::File::open(zip_path)?;
    let mut archive = zip::ZipArchive::new(file)?;

    for i in 0..archive.len() {
        let mut entry = archive.by_index(i)?;
        let outpath = dest_dir.join(entry.name());

        if entry.name().ends_with('/') {
            std::fs::create_dir_all(&outpath)?;
        } else {
            if let Some(parent) = outpath.parent() {
                std::fs::create_dir_all(parent)?;
            }
            let mut out_file = std::fs::File::create(&outpath)?;
            std::io::copy(&mut entry, &mut out_file)?;
        }
    }
    Ok(())
}

/// Extract a single named file from ZIP to dest_path.
fn extract_zip_single(zip_path: &Path, dest_path: &Path, filename: &str) -> Result<()> {
    let file = std::fs::File::open(zip_path)?;
    let mut archive = zip::ZipArchive::new(file)?;

    // Find the file (may be nested)
    for i in 0..archive.len() {
        let mut entry = archive.by_index(i)?;
        let name = entry.name().to_string();
        if name.ends_with(filename) && !name.ends_with('/') {
            if let Some(parent) = dest_path.parent() {
                std::fs::create_dir_all(parent)?;
            }
            let mut out_file = std::fs::File::create(dest_path)?;
            std::io::copy(&mut entry, &mut out_file)?;
            return Ok(());
        }
    }
    anyhow::bail!("File '{}' not found in ZIP archive", filename);
}

/// Fix embeddable Python's ._pth file to enable site-packages and pip.
fn fix_pth_file(python_dir: &Path) -> Result<()> {
    // Find python311._pth
    for entry in std::fs::read_dir(python_dir)? {
        let entry = entry?;
        let name = entry.file_name();
        let name_str = name.to_string_lossy();
        if name_str.ends_with("._pth") {
            let path = entry.path();
            let content = std::fs::read_to_string(&path)?;
            // Uncomment import site line
            let fixed = content.replace("#import site", "import site");
            std::fs::write(&path, fixed)?;
            log::info!("Fixed ._pth file: {:?}", path);
            return Ok(());
        }
    }
    log::warn!("._pth file not found in {:?}", python_dir);
    Ok(())
}
