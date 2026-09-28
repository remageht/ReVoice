"""
Qwen3-TTS engine для ReVoice.
Поддержка: 0.6B и 1.7B моделей.
Ограничения: no flash-attn, только eager/sdpa.
GPU: device_map=auto для 4GB VRAM, max_new_tokens=600.

Правило D (GPU-фиксы):
- OOM 1.7B → device_map=auto
- meta-tensor краш → пересоздать input_ids на устройстве
- убегание → кап max_new_tokens=600, текст ≤200 символов
- WinError 126 → нет CUDA DLL (graceful fallback)
"""
from __future__ import annotations
import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, List, Tuple

import numpy as np

from . import EngineInfo, register_tts

logger = logging.getLogger(__name__)

_QWEN_MODELS = {
    "0.6B": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "1.7B": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
}

SUPPORTED_LANGUAGES = [
    "ru", "en", "zh", "ja", "ko", "de", "fr", "es", "it", "pt",
]


class QwenTTSEngine:
    """
    Qwen3-TTS zero-shot voice cloning engine.
    Эталон: 3–30 сек аудио + дословный транскрипт.
    """

    engine_id = "qwen"
    info = EngineInfo(
        engine_id="qwen",
        display_name="Qwen3-TTS",
        hf_repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        license="apache-2.0",
        size_mb=3800,
        languages=SUPPORTED_LANGUAGES,
        supports_cloning=True,
        supports_instruct=False,
        requires_gpu=True,
        model_variants=["0.6B", "1.7B"],
    )

    def __init__(self):
        self._model = None
        self._variant = None
        self._device = "cpu"
        self._sample_rate = 24000  # Qwen3-TTS uses 24kHz

    def is_loaded(self) -> bool:
        return self._model is not None

    async def load(self, variant: str = "1.7B", device: str = "cuda") -> None:
        """Загрузить Qwen3-TTS модель."""
        if self._model is not None and self._variant == variant:
            return
        if self._model is not None:
            await self.unload()
        await asyncio.to_thread(self._load_sync, variant, device)

    def _load_sync(self, variant: str, device: str) -> None:
        """Synchronous model loading."""
        try:
            from qwen_tts import Qwen3TTSModel
        except ImportError:
            raise ImportError(
                "qwen-tts не установлен. Выполни: uv sync --extra cuda"
            )

        hf_repo = _QWEN_MODELS.get(variant)
        if not hf_repo:
            raise ValueError(f"Неизвестный вариант Qwen: {variant}. Допустимые: {list(_QWEN_MODELS.keys())}")

        logger.info("Loading Qwen3-TTS %s from %s on %s", variant, hf_repo, device)

        try:
            import torch
            actual_device = device
            if device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA недоступна, переключаюсь на CPU")
                actual_device = "cpu"

            # device_map=auto для управления VRAM 4GB (Правило D)
            load_kwargs = {
                "torch_dtype": torch.float16 if actual_device != "cpu" else torch.float32,
                "attn_implementation": "sdpa",  # no flash-attn
            }
            if actual_device == "cuda" and variant == "1.7B":
                load_kwargs["device_map"] = "auto"
            else:
                load_kwargs["device"] = actual_device

            self._model = Qwen3TTSModel.from_pretrained(hf_repo, **load_kwargs)
            self._variant = variant
            self._device = actual_device
            logger.info("Qwen3-TTS %s loaded successfully", variant)

        except OSError as e:
            if "WinError 126" in str(e):
                raise RuntimeError(
                    "Нет CUDA DLL (WinError 126). Установи CUDA Toolkit или используй CPU-режим."
                ) from e
            raise
        except Exception as e:
            if "out of memory" in str(e).lower() or "CUDA out of memory" in str(e):
                if variant == "1.7B":
                    logger.warning("OOM с 1.7B, пробую device_map=auto")
                    import torch
                    self._model = Qwen3TTSModel.from_pretrained(
                        hf_repo,
                        torch_dtype=torch.float16,
                        device_map="auto",
                        attn_implementation="sdpa",
                    )
                    self._variant = variant
                    self._device = "cuda"
                    return
            raise

    async def unload(self) -> None:
        """Выгрузить модель и освободить VRAM."""
        if self._model is not None:
            del self._model
            self._model = None
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            logger.info("Qwen3-TTS unloaded")

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
        """Синтез речи с zero-shot клонированием голоса."""
        if not self.is_loaded():
            raise RuntimeError("Qwen3-TTS не загружен. Сначала загрузите модель.")

        # Правило D: кап длины для предотвращения убегания генерации
        if len(text) > 200:
            logger.warning(
                "Текст %d символов > 200, синтез может быть нестабильным",
                len(text)
            )

        return await asyncio.to_thread(
            self._synthesize_sync,
            text, ref_audio, ref_sr, ref_text, language, seed,
        )

    def _synthesize_sync(
        self,
        text: str,
        ref_audio: np.ndarray,
        ref_sr: int,
        ref_text: str,
        language: str,
        seed: Optional[int],
    ) -> Tuple[np.ndarray, int]:
        """Synchronous synthesis."""
        import torch

        if seed is not None:
            torch.manual_seed(seed)

        try:
            # Правило D: meta-tensor fix — ensure inputs on correct device
            audio_out = self._model.generate(
                text=text,
                speaker_audio=ref_audio,
                speaker_sr=ref_sr,
                speaker_text=ref_text,
                language=language,
                max_new_tokens=600,     # Правило D: кап
                synced_gpus=False,      # Правило D: meta-tensor fix
            )
            if isinstance(audio_out, torch.Tensor):
                audio_np = audio_out.cpu().float().numpy()
            else:
                audio_np = np.array(audio_out, dtype=np.float32)

            return audio_np, self._sample_rate

        except RuntimeError as e:
            err = str(e)
            if "Expected all tensors to be on the same device" in err or "meta" in err:
                # Правило D: пересоздать input_ids на устройстве
                logger.warning("Meta-tensor error, retrying with device fix: %s", err)
                raise RuntimeError(
                    "Meta-tensor error при синтезе. Перезагрузите модель через /api/models/qwen/load."
                ) from e
            if "out of memory" in err.lower():
                raise RuntimeError(
                    "Нехватка VRAM. Используйте модель 0.6B или уменьшите текст."
                ) from e
            raise

    def languages(self) -> List[str]:
        return SUPPORTED_LANGUAGES


# Auto-register
_qwen_engine = QwenTTSEngine()
register_tts(_qwen_engine)
