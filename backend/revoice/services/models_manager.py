"""
Менеджер моделей ReVoice:
- НИКАКИХ встроенных весов в бандле/репозитории
- Каталог моделей (TTS / STT / LLM) с перечнем обязательных файлов и контрольными суммами
- Скачивание с докачкой (resume) и отслеживанием прогресса
- Проверка пользовательских путей («Указать путь») с детальным списком недостающих файлов
- Миграция папки моделей с переносом существующих файлов
- Ограничение VRAM: строго 1 модель в памяти единовременно, выгрузка перед загрузкой
"""
from __future__ import annotations
import os
import sys
import gc
import json
import shutil
import hashlib
import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from ..config import settings
from ..backends import _TTS_REGISTRY, _STT_REGISTRY

logger = logging.getLogger(__name__)


@dataclass
class ModelDefinition:
    id: str
    name: str
    type: str                     # "TTS" | "STT" | "LLM"
    engine_id: str                # "qwen" | "fish" | "faster-whisper"
    variant: str                  # "0.6B", "1.7B", "small", etc.
    hf_repo_id: str
    size_mb: int
    license: str
    description: str
    required_files: List[str]     # Files that must exist for model to be valid
    expected_sha256: Optional[Dict[str, str]] = None  # filename -> sha256 prefix/hash


# Каталог поддерживаемых моделей
MODEL_CATALOGUE: Dict[str, ModelDefinition] = {
    "stub": ModelDefinition(
        id="stub",
        name="Stub TTS (Тестовый генератор)",
        type="TTS",
        engine_id="stub",
        variant="default",
        hf_repo_id="",
        size_mb=0,
        license="MIT",
        description="Встроенный тестовый генератор (не требует скачивания весов).",
        required_files=[],
    ),
    "qwen-tts-0.6b": ModelDefinition(
        id="qwen-tts-0.6b",
        name="Qwen3-TTS 0.6B (Базовая, быстрая)",
        type="TTS",
        engine_id="qwen",
        variant="0.6B",
        hf_repo_id="Qwen/Qwen3-TTS-12Hz-0.6B-Base",
        size_mb=1200,
        license="Apache-2.0",
        description="Компактная модель клонирования голоса. Минимальное потребление VRAM (~1.5 ГБ).",
        required_files=["config.json", "model.safetensors"],
    ),
    "qwen-tts-1.7b": ModelDefinition(
        id="qwen-tts-1.7b",
        name="Qwen3-TTS 1.7B (Высокое качество)",
        type="TTS",
        engine_id="qwen",
        variant="1.7B",
        hf_repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        size_mb=3800,
        license="Apache-2.0",
        description="Флагманская модель zero-shot клонирования. Максимальная точность тембра.",
        required_files=["config.json", "model.safetensors"],
    ),
    "fish-speech-1.5": ModelDefinition(
        id="fish-speech-1.5",
        name="Fish Speech 1.5",
        type="TTS",
        engine_id="fish",
        variant="1.5",
        hf_repo_id="fishaudio/fish-speech-1.5",
        size_mb=2500,
        license="CC-BY-NC-SA-4.0",
        description="Альтернативный движок zero-shot синтеза речи.",
        required_files=["config.json"],
    ),
    "whisper-small": ModelDefinition(
        id="whisper-small",
        name="Faster-Whisper Small (Авто-транскрипция)",
        type="STT",
        engine_id="faster-whisper",
        variant="small",
        hf_repo_id="Systran/faster-whisper-small",
        size_mb=480,
        license="MIT",
        description="Автоматическое распознавание речи для разметки эталонных сэмплов.",
        required_files=["config.json", "model.bin", "vocabulary.json"],
    ),
    "whisper-base": ModelDefinition(
        id="whisper-base",
        name="Faster-Whisper Base (Легковесная STT)",
        type="STT",
        engine_id="faster-whisper",
        variant="base",
        hf_repo_id="Systran/faster-whisper-base",
        size_mb=145,
        license="MIT",
        description="Быстрая авто-транскрипция для слабых систем.",
        required_files=["config.json", "model.bin", "vocabulary.json"],
    ),
}

# Пользовательские пути для моделей: model_id -> Path
_CUSTOM_PATHS: Dict[str, Path] = {}

# Состояние активных загрузок: model_id -> dict
_DOWNLOAD_PROGRESS: Dict[str, dict] = {}


def get_models_dir() -> Path:
    """Возвращает актуальную директорию моделей (с учётом REVOICE_MODELS_DIR)."""
    env_dir = os.environ.get("REVOICE_MODELS_DIR")
    if env_dir:
        return Path(env_dir)
    return settings.models_dir


def set_models_dir(new_path: Path) -> None:
    """Установить новую директорию моделей."""
    settings.models_dir = new_path
    new_path.mkdir(parents=True, exist_ok=True)
    logger.info("Models directory updated to: %s", new_path)


def get_model_path(model_id: str) -> Path:
    """Возвращает локальный путь к модели (пользовательский или стандартный)."""
    if model_id in _CUSTOM_PATHS:
        return _CUSTOM_PATHS[model_id]
    return get_models_dir() / model_id


def set_custom_path(model_id: str, path: Path) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Привязать пользовательскую папку к модели.
    Возвращает (успех, ошибка_если_есть, предупреждение_если_есть).
    """
    validation = validate_model_directory(model_id, path)
    if not validation["is_valid"]:
        return False, validation["error"], None
    
    _CUSTOM_PATHS[model_id] = path.resolve()
    logger.info("Custom path set for %s: %s", model_id, path)
    return True, None, validation.get("warning")


def validate_model_directory(model_id: str, path: Path) -> dict:
    """
    Валидация папки модели («Указать путь»):
    - Наличие config.json + весов + токенизатора
    - Несовпадение — русская ошибка с перечислением недостающих файлов
    - Сверка хеша при наличии эталона
    """
    if model_id not in MODEL_CATALOGUE:
        return {"is_valid": False, "error": f"Неизвестная модель: {model_id}"}

    defn = MODEL_CATALOGUE[model_id]

    if not path.exists():
        return {"is_valid": False, "error": f"Указанный путь не существует: {path}"}
    if not path.is_dir():
        return {"is_valid": False, "error": f"Указанный путь должен быть папкой: {path}"}

    # Ищем файлы рекурсивно в папке (учитывая структуру snapshots HF)
    existing_files = {f.name for f in path.rglob("*") if f.is_file()}

    missing = []
    for req in defn.required_files:
        # Для весов допускаем safetensors или bin
        if req == "model.safetensors":
            if not any(f.endswith(".safetensors") or f.endswith(".bin") for f in existing_files):
                missing.append("model.safetensors (или *.bin)")
        elif req not in existing_files:
            missing.append(req)

    if missing:
        error_msg = (
            f"В папке не найдены обязательные файлы для «{defn.name}»:\n"
            + ", ".join(missing)
            + ".\nУбедитесь, что указана папка снапшота с весами и конфигурацией."
        )
        return {"is_valid": False, "error": error_msg}

    # Проверка хеша если задан
    warning = None
    if defn.expected_sha256:
        for fname, expected_hash in defn.expected_sha256.items():
            matching_files = list(path.rglob(fname))
            if matching_files:
                file_hash = _compute_sha256(matching_files[0])
                if not file_hash.startswith(expected_hash):
                    warning = (
                        f"Контрольная сумма файла {fname} не совпадает с эталонной "
                        f"(получено: {file_hash[:12]}..., ожидалось: {expected_hash[:12]}...). "
                        f"Файл может быть повреждён."
                    )

    return {"is_valid": True, "warning": warning}


def _compute_sha256(file_path: Path, max_bytes: int = 10 * 1024 * 1024) -> str:
    """Вычисляет sha256 первых max_bytes файла для быстрой проверки."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        chunk = f.read(max_bytes)
        hasher.update(chunk)
    return hasher.hexdigest()


def check_model_status(model_id: str) -> dict:
    """Проверить статус модели на диске и в VRAM."""
    defn = MODEL_CATALOGUE.get(model_id)
    if not defn:
        return {"status": "unknown"}

    path = get_model_path(model_id)
    is_custom = model_id in _CUSTOM_PATHS

    # Проверка загруженности в VRAM
    is_loaded = False
    if defn.type == "TTS":
        engine = _TTS_REGISTRY.get(defn.engine_id)
        if engine and engine.is_loaded():
            # Проверяем совпадение варианта
            if getattr(engine, "_variant", None) == defn.variant:
                is_loaded = True
    elif defn.type == "STT":
        engine = _STT_REGISTRY.get(defn.engine_id)
        if engine and engine.is_loaded():
            is_loaded = True

    # Проверка наличия на диске
    val = validate_model_directory(model_id, path)
    if val["is_valid"]:
        disk_status = "downloaded"
    elif path.exists() and any(path.iterdir()):
        disk_status = "partial"
    else:
        disk_status = "not_downloaded"

    download_info = _DOWNLOAD_PROGRESS.get(model_id, {})

    return {
        "id": defn.id,
        "name": defn.name,
        "type": defn.type,
        "engine_id": defn.engine_id,
        "variant": defn.variant,
        "size_mb": defn.size_mb,
        "license": defn.license,
        "description": defn.description,
        "disk_status": disk_status,
        "is_loaded": is_loaded,
        "is_custom_path": is_custom,
        "local_path": str(path),
        "download": download_info,
        "validation_warning": val.get("warning"),
    }


def list_all_models() -> List[dict]:
    """Список всех моделей с текущим статусом."""
    return [check_model_status(mid) for mid in MODEL_CATALOGUE]


# ---------------------------------------------------------------------------
# Резюмируемый загрузчик (HuggingFace snapshot_download с resume)
# ---------------------------------------------------------------------------

async def start_model_download(model_id: str) -> dict:
    """
    Запустить фоновое скачивание модели с поддержкой докачки (resume).
    """
    if model_id not in MODEL_CATALOGUE:
        raise ValueError(f"Неизвестная модель: {model_id}")

    target_dir = get_models_dir() / model_id
    target_dir.mkdir(parents=True, exist_ok=True)

    if model_id in _DOWNLOAD_PROGRESS and _DOWNLOAD_PROGRESS[model_id].get("status") == "downloading":
        return {"status": "already_downloading", "model_id": model_id}

    _DOWNLOAD_PROGRESS[model_id] = {
        "status": "downloading",
        "progress_percent": 0.0,
        "error": None,
    }

    asyncio.create_task(_download_worker(model_id, target_dir))
    return {"status": "started", "model_id": model_id, "target_dir": str(target_dir)}


async def _download_worker(model_id: str, target_dir: Path) -> None:
    """Фоновый воркер загрузки весов."""
    defn = MODEL_CATALOGUE[model_id]
    logger.info("Starting download for %s (%s) -> %s", model_id, defn.hf_repo_id, target_dir)

    try:
        from huggingface_hub import snapshot_download

        def _do_download():
            return snapshot_download(
                repo_id=defn.hf_repo_id,
                local_dir=str(target_dir),
                resume_download=True,      # Докачка: повторный запуск не начинает заново!
                local_dir_use_symlinks=False,
            )

        # Выполняем в отдельном пуле потоков
        await asyncio.to_thread(_do_download)

        _DOWNLOAD_PROGRESS[model_id] = {
            "status": "completed",
            "progress_percent": 100.0,
            "error": None,
        }
        logger.info("Download completed for %s", model_id)

    except Exception as e:
        logger.exception("Download failed for %s", model_id)
        _DOWNLOAD_PROGRESS[model_id] = {
            "status": "failed",
            "progress_percent": 0.0,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# VRAM / GPU управление: строго одна модель на 4 ГБ VRAM
# ---------------------------------------------------------------------------

async def unload_all_models() -> None:
    """
    Выгрузить ВСЕ модели из памяти и освободить VRAM.
    Очищает PyTorch CUDA кэш и запускает сборщик мусора.
    """
    for engine in _TTS_REGISTRY.values():
        if engine.is_loaded():
            await engine.unload()

    for engine in _STT_REGISTRY.values():
        if engine.is_loaded():
            await engine.unload()

    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass

    gc.collect()
    logger.info("All models unloaded. VRAM freed.")


async def load_single_model(model_id: str, device: str = "cuda") -> dict:
    """
    Загрузить модель в память.
    Автоматически выгружает любую другую модель перед загрузкой (правило 4 ГБ VRAM).
    """
    defn = MODEL_CATALOGUE.get(model_id)
    if not defn:
        raise ValueError(f"Неизвестная модель: {model_id}")

    # 1. Проверяем наличие файлов
    path = get_model_path(model_id)
    val = validate_model_directory(model_id, path)
    if not val["is_valid"]:
        raise FileNotFoundError(val["error"])

    # 2. Выгружаем все остальные модели
    await unload_all_models()

    # 3. Загружаем нужный движок
    if defn.type == "TTS":
        engine = _TTS_REGISTRY.get(defn.engine_id)
        if not engine:
            raise RuntimeError(f"Движок {defn.engine_id} не зарегистрирован")
        await engine.load(variant=defn.variant, device=device)
    elif defn.type == "STT":
        engine = _STT_REGISTRY.get(defn.engine_id)
        if not engine:
            raise RuntimeError(f"STT движок {defn.engine_id} не зарегистрирован")
        await engine.load(variant=defn.variant)

    logger.info("Model %s loaded into memory", model_id)
    return {"status": "loaded", "model_id": model_id}


# ---------------------------------------------------------------------------
# Миграция папки моделей с переносом существующих файлов
# ---------------------------------------------------------------------------

async def migrate_models_directory(
    new_dir: Path,
    move_files: bool = True,
) -> dict:
    """
    Перенести папку моделей в новое место:
    - Создает новую директорию
    - При move_files=True переносит существующие скачанные модели
    - Обновляет глобальную настройку
    """
    old_dir = get_models_dir()
    new_dir = new_dir.resolve()

    if old_dir == new_dir:
        return {"status": "unchanged", "path": str(new_dir), "migrated_count": 0}

    new_dir.mkdir(parents=True, exist_ok=True)
    migrated_count = 0

    if move_files and old_dir.exists():
        for item in old_dir.iterdir():
            target = new_dir / item.name
            if not target.exists():
                if item.is_dir():
                    shutil.copytree(str(item), str(target))
                else:
                    shutil.copy2(str(item), str(target))
                migrated_count += 1
                logger.info("Migrated model: %s -> %s", item.name, target)

    set_models_dir(new_dir)
    return {
        "status": "migrated",
        "old_path": str(old_dir),
        "new_path": str(new_dir),
        "migrated_count": migrated_count,
    }
