# ReVoice

> Студия клонирования голоса и озвучки для создателей контента.
> Мемы, аудиокниги, дубляж — всё локально, без облаков.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Стек

- **UI**: Tauri 2 + React 18 + TypeScript + Tailwind CSS
- **Backend**: Python 3.11 + FastAPI (sidecar PyInstaller)
- **TTS**: Qwen3-TTS 0.6B/1.7B, Fish Speech 1.5
- **STT**: faster-whisper small
- **DB**: SQLite (`%APPDATA%/Revoice/revoice.db`)
- **Платформа №1**: Windows 11 + CUDA 12.x / RTX

## Структура монорепо

```
ReVoice/
├── app/          # React UI + Tauri frontend
├── src-tauri/    # Rust Tauri shell
├── backend/      # Python FastAPI sidecar
└── docs/
```

## Этап 1: Запуск бэкенда для разработки

```powershell
cd backend
uv sync
uv run python -m uvicorn revoice.main:app --reload --port 7851
```

Проверка: `curl http://localhost:7851/api/health`

## Лицензия

MIT — смотри [LICENSE](LICENSE).
