"""
Stub TTS/STT движки — работают без GPU/моделей.
Используются для тестирования API без загрузки весов.
"""
from __future__ import annotations
import logging
import struct
import math
from pathlib import Path
from typing import Optional, List, Tuple
import numpy as np

from . import EngineInfo, TTSEngine, STTEngine, register_tts, register_stt

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 22050


class StubTTSEngine:
    """Заглушка — генерирует тишину нужной длины."""

    engine_id = "stub"
    info = EngineInfo(
        engine_id="stub",
        display_name="Stub (тест)",
        hf_repo_id="",
        license="mit",
        size_mb=0,
        languages=["ru", "en"],
        supports_cloning=True,
    )

    def __init__(self):
        self._loaded = False

    async def load(self, variant: str = "default", device: str = "cpu") -> None:
        self._loaded = True
        logger.info("StubTTSEngine loaded")

    async def unload(self) -> None:
        self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded

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
        # Generate a short sine wave as placeholder
        duration = max(0.5, len(text) / 12)  # ~12 chars/sec
        t = np.linspace(0, duration, int(_SAMPLE_RATE * duration), dtype=np.float32)
        audio = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        logger.info("StubTTS: synthesized %d chars → %.2fs", len(text), duration)
        return audio, _SAMPLE_RATE

    def languages(self) -> List[str]:
        return ["ru", "en"]


class StubSTTEngine:
    """Заглушка STT — возвращает фиктивный транскрипт."""

    engine_id = "stub-stt"

    def __init__(self):
        self._loaded = False

    async def load(self, variant: str = "small") -> None:
        self._loaded = True

    async def unload(self) -> None:
        self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded

    async def transcribe(
        self,
        audio_path: Path,
        language: Optional[str] = None,
    ) -> str:
        return "[stub transcription]"


# Auto-register stubs
register_tts(StubTTSEngine())
register_stt(StubSTTEngine())
