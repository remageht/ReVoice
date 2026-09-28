"""
Models and weights management routes.
- НИКАКИХ встроенных весов: всё докачивается или подключается пользователем
- Валидация папок моделей (config.json + веса + токенизатор)
- Резюмируемая загрузка
- Переопределение папки моделей с миграцией
- VRAM менеджмент: строго 1 модель в памяти на 4 ГБ VRAM
"""
from __future__ import annotations
import os
import sys
import subprocess
import logging
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.models_manager import (
    list_all_models,
    check_model_status,
    start_model_download,
    set_custom_path,
    validate_model_directory,
    load_single_model,
    unload_all_models,
    get_models_dir,
    migrate_models_directory,
    get_model_path,
)
from ..backends import _TTS_REGISTRY, get_tts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/models", tags=["models"])


class SetPathRequest(BaseModel):
    path: str = Field(..., min_length=1)


class LoadModelRequest(BaseModel):
    device: str = "cuda"


class MigrateDirRequest(BaseModel):
    new_dir: str = Field(..., min_length=1)
    move_files: bool = True


@router.get("", response_model=List[dict])
async def list_models() -> List[dict]:
    """Список всех доступных моделей с их дисковым и VRAM статусом."""
    return list_all_models()


@router.get("/dir", response_model=dict)
async def get_directory() -> dict:
    """Получить текущую папку моделей."""
    return {
        "models_dir": str(get_models_dir()),
        "is_env_overridden": bool(os.environ.get("REVOICE_MODELS_DIR")),
    }


@router.post("/dir/migrate", response_model=dict)
async def migrate_directory(req: MigrateDirRequest) -> dict:
    """Перенести папку моделей в новое место с миграцией файлов."""
    new_path = Path(req.new_dir)
    result = await migrate_models_directory(new_path, move_files=req.move_files)
    return result


@router.get("/{model_id}", response_model=dict)
async def get_model(model_id: str) -> dict:
    """Получить статус конкретной модели."""
    status = check_model_status(model_id)
    if status.get("status") == "unknown":
        raise HTTPException(status_code=404, detail="Модель не найдена в каталоге")
    return status


@router.post("/{model_id}/download", response_model=dict)
async def download_model(model_id: str) -> dict:
    """Запустить резюмируемое скачивание модели."""
    try:
        return await start_model_download(model_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to start download")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{model_id}/set-path", response_model=dict)
async def link_custom_path(model_id: str, req: SetPathRequest) -> dict:
    """
    «Указать путь» к скачанной модели.
    Проверяет наличие обязательных файлов, возвращает ошибку при несовпадении.
    """
    custom_path = Path(req.path)
    success, error, warning = set_custom_path(model_id, custom_path)
    if not success:
        raise HTTPException(status_code=422, detail=error)
    return {
        "status": "linked",
        "model_id": model_id,
        "path": str(custom_path),
        "warning": warning,
    }


@router.post("/{model_id}/load", response_model=dict)
async def load_model(model_id: str, req: LoadModelRequest = LoadModelRequest()) -> dict:
    """
    Загрузить модель в VRAM.
    Автоматически выгружает любую другую модель перед загрузкой (правило 4 ГБ VRAM).
    """
    try:
        return await load_single_model(model_id, device=req.device)
    except FileNotFoundError as e:
        raise HTTPException(status_code=422, detail=f"Модель не готова: {e}")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Failed to load model %s", model_id)
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки: {e}")


@router.post("/{model_id}/unload", response_model=dict)
async def unload_model(model_id: str) -> dict:
    """Выгрузить модель из VRAM и освободить память."""
    await unload_all_models()
    return {"status": "unloaded", "model_id": model_id}


@router.post("/unload-all", response_model=dict)
async def unload_all() -> dict:
    """Выгрузить ВСЕ модели из памяти и освободить VRAM."""
    await unload_all_models()
    return {"status": "all_unloaded"}


@router.post("/{model_id}/open-folder", response_model=dict)
async def open_folder(model_id: str) -> dict:
    """Открыть папку модели в системном проводнике."""
    p = get_model_path(model_id)
    if not p.exists():
        p = get_models_dir()
    p.mkdir(parents=True, exist_ok=True)

    try:
        if sys.platform == "win32":
            os.startfile(str(p))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)])
        else:
            subprocess.run(["xdg-open", str(p)])
        return {"status": "opened", "path": str(p)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Не удалось открыть папку: {e}")
