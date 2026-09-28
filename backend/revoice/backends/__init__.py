"""
Engine registry — протокол и реестр движков TTS/STT.

Каждый движок регистрируется через декоратор @register_engine.
Протокол определяет контракт: load / unload / synthesize / languages.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Protocol, Optional, Tuple, List, runtime_checkable
from pathlib import Path
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class EngineInfo:
    """Описание движка TTS для UI и API."""
    engine_id: str       # «qwen», «fish», «faster-whisper»
    display_name: str    # Отображаемое имя
    hf_repo_id: str      # HuggingFace repo ID
    license: str         # «apache-2.0» / «mit» / «cc-by-nc-4.0»
    size_mb: int         # Примерный размер в МБ
    languages: List[str] = field(default_factory=list)
    supports_cloning: bool = True
    supports_instruct: bool = False
    requires_gpu: bool = False
    model_variants: List[str] = field(default_factory=lambda: ["default"])


@runtime_checkable
class TTSEngine(Protocol):
    """Протокол TTS-движка."""

    engine_id: str
    info: EngineInfo

    async def load(self, variant: str = "default", device: str = "cuda") -> None:
        """Загрузить модель в память."""
        ...

    async def unload(self) -> None:
        """Выгрузить модель, освободить VRAM."""
        ...

    def is_loaded(self) -> bool:
        """True если модель загружена."""
        ...

    async def synthesize(
        self,
        text: str,
        *,
        ref_audio: np.ndarray,
        ref_sr: int,
        ref_text: str,
        language: str = "ru",
        seed: Optional[int] = None,
    ) -> Tuple[np.ndarray, int]:
        """
        Синтез речи с клонированием голоса.

        Returns:
            (audio_array, sample_rate)
        """
        ...

    def languages(self) -> List[str]:
        """Список поддерживаемых языков (ISO 639-1)."""
        ...


@runtime_checkable
class STTEngine(Protocol):
    """Протокол STT-движка."""

    engine_id: str

    async def load(self, variant: str = "small") -> None: ...
    async def unload(self) -> None: ...
    def is_loaded(self) -> bool: ...

    async def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
    ) -> str:
        """Транскрибировать аудио в текст."""
        ...


# ---------------------------------------------------------------------------
# Engine registry
# ---------------------------------------------------------------------------

_TTS_REGISTRY: dict[str, "TTSEngine"] = {}
_STT_REGISTRY: dict[str, "STTEngine"] = {}


def register_tts(engine: "TTSEngine") -> None:
    """Зарегистрировать TTS-движок."""
    _TTS_REGISTRY[engine.engine_id] = engine
    logger.debug("TTS engine registered: %s", engine.engine_id)


def register_stt(engine: "STTEngine") -> None:
    """Зарегистрировать STT-движок."""
    _STT_REGISTRY[engine.engine_id] = engine
    logger.debug("STT engine registered: %s", engine.engine_id)


def get_tts(engine_id: str) -> "TTSEngine":
    if engine_id not in _TTS_REGISTRY:
        raise KeyError(f"TTS engine not found: {engine_id!r}. Available: {list(_TTS_REGISTRY.keys())}")
    return _TTS_REGISTRY[engine_id]


def get_stt(engine_id: str = "faster-whisper") -> "STTEngine":
    if engine_id not in _STT_REGISTRY:
        raise KeyError(f"STT engine not found: {engine_id!r}")
    return _STT_REGISTRY[engine_id]


def list_tts_engines() -> List[EngineInfo]:
    return [e.info for e in _TTS_REGISTRY.values()]
