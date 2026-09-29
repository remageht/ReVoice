"""
Qwen3-TTS engine для ReVoice.
Строго соответствует реальному API qwen-tts 0.1.1:
1. Загрузка: Qwen3TTSModel.from_pretrained(path, device_map="cuda:0"|"auto", dtype=torch.bfloat16, attn_implementation="eager", max_memory={"0":"3000MB","cpu":"12GB"} при auto). Никаких torch_dtype/device kwargs.
2. Синтез: generate_voice_clone(text, language, ref_audio, ref_text) либо voice_clone_prompt=create_voice_clone_prompt(ref_audio, ref_text). Возвращает (wavs, sr) — сохраняем wavs[0]. Никакого .generate(text=, speaker_audio=).
3. Языки: маппинг ISO 639-1 -> полное название ({"ru": "Russian", ...}), сверка с get_supported_languages().
4. Meta-tensor патч: оборачивание GenerationMixin._maybe_initialize_input_ids_for_generation и synced_gpus=False.
"""
from __future__ import annotations
import os
import sys
import gc
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
import numpy as np

from . import EngineInfo, register_tts

logger = logging.getLogger(__name__)

# Маппинг ISO кодов языков в названия, ожидаемые Qwen3-TTS
LANGUAGE_MAP: Dict[str, str] = {
    "ru": "Russian",
    "en": "English",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
}

_REVERSE_LANG_MAP: Dict[str, str] = {v.lower(): k for k, v in LANGUAGE_MAP.items()}


# ---------------------------------------------------------------------------
# Патч meta-тензоров при device_map=auto (Правило 4)
# ---------------------------------------------------------------------------

_PATCH_APPLIED = False

def _apply_meta_tensor_patch():
    """
    Патч transformers GenerationMixin._maybe_initialize_input_ids_for_generation.
    При оффлоаде на CPU/Disk некоторые тензоры создаются на meta-устройстве.
    Пересоздаём их на том же устройстве, что и inputs_embeds.
    """
    global _PATCH_APPLIED
    if _PATCH_APPLIED:
        return

    try:
        from transformers.generation import utils as _gu
        import torch

        _orig_init = getattr(_gu.GenerationMixin, "_maybe_initialize_input_ids_for_generation", None)
        if _orig_init is not None:
            def _safe_init(self, inputs=None, bos_token_id=None, model_kwargs=None):
                r = _orig_init(self, inputs, bos_token_id, model_kwargs)
                if isinstance(r, torch.Tensor) and r.device.type == "meta":
                    dev = torch.device("cuda:0")
                    ie = (model_kwargs or {}).get("inputs_embeds")
                    if isinstance(ie, torch.Tensor) and ie.device.type != "meta":
                        dev = ie.device
                    r = torch.ones_like(r, device=dev)
                return r

            _gu.GenerationMixin._maybe_initialize_input_ids_for_generation = _safe_init
            _PATCH_APPLIED = True
            logger.info("Meta-tensor monkey patch applied to transformers.GenerationMixin")
    except Exception as e:
        logger.warning("Could not apply meta-tensor patch: %s", e)


class QwenTTSEngine:
    """
    Qwen3-TTS zero-shot voice cloning engine.
    Поддерживает варианты 0.6B и 1.7B с защитой по памяти под 4 ГБ VRAM.
    """

    engine_id = "qwen"
    info = EngineInfo(
        engine_id="qwen",
        display_name="Qwen3-TTS",
        hf_repo_id="Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        license="Apache-2.0",
        size_mb=3800,
        languages=list(LANGUAGE_MAP.keys()),
        supports_cloning=True,
        supports_instruct=False,
        requires_gpu=True,
        model_variants=["0.6B", "1.7B"],
    )

    def __init__(self):
        self._model = None
        self._variant = None
        self._model_path = None
        self._sample_rate = 24000

    def is_loaded(self) -> bool:
        return self._model is not None

    async def load(
        self,
        variant: str = "0.6B",
        device: str = "cuda",
        model_path: Optional[str | Path] = None,
    ) -> None:
        """Загрузить модель Qwen3-TTS."""
        if self._model is not None:
            await self.unload()

        await asyncio.to_thread(self._load_sync, variant, device, model_path)

    def _load_sync(
        self,
        variant: str,
        device: str,
        model_path: Optional[str | Path] = None,
    ) -> None:
        """Синхронная загрузка с точными параметрами Qwen3TTSModel.from_pretrained."""
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError as e:
            raise ImportError(
                "qwen-tts или torch не установлены в окружении. "
                "Установите через: uv pip install qwen-tts==0.1.1 transformers==4.57.3"
            ) from e

        # Применяем патч для meta-тензоров
        _apply_meta_tensor_patch()

        # Определяем путь к весам и вариант
        if model_path is not None:
            load_path = str(model_path)
            if variant == "0.6B" and ("17b" in load_path.lower() or "1.7" in load_path):
                variant = "1.7B"
        else:
            from ..services.models_manager import get_model_path
            model_id = f"qwen-tts-{variant.lower()}"
            target_path = get_model_path(model_id)
            if not target_path.exists():
                raise FileNotFoundError(
                    f"Папка модели не найдена: {target_path}. "
                    f"Скачайте веса через экран «Модели» или укажите путь."
                )
            load_path = str(target_path)

        logger.info("Loading Qwen3-TTS [%s] from %s...", variant, load_path)

        has_cuda = torch.cuda.is_available() and device.startswith("cuda")

        # 1. Параметры from_pretrained строго по спецификации:
        # device_map="cuda:0"|"auto", dtype=torch.bfloat16, attn_implementation="eager"
        # max_memory={"0":"3000MB","cpu":"12GB"} при auto.
        # НИКАКИХ torch_dtype/device kwargs.
        load_kwargs: Dict[str, Any] = {
            "dtype": torch.bfloat16 if has_cuda else torch.float32,
            "attn_implementation": "eager",
        }

        if has_cuda:
            if variant == "1.7B":
                # Для 1.7B на 4GB VRAM используем auto оффлоад с лимитом памяти
                load_kwargs["device_map"] = "auto"
                load_kwargs["max_memory"] = {"0": "3000MB", "cpu": "12GB"}
            else:
                load_kwargs["device_map"] = "cuda:0"
        else:
            load_kwargs["device_map"] = "cpu"

        try:
            self._model = Qwen3TTSModel.from_pretrained(load_path, **load_kwargs)
            self._variant = variant
            self._model_path = load_path

            # Пробуем пропатчить внутренний talker для synced_gpus=False
            if hasattr(self._model, "talker") and hasattr(self._model.talker, "generate"):
                orig_talker_gen = self._model.talker.generate
                def _patched_talker_gen(*args, **kwargs):
                    kwargs["synced_gpus"] = False
                    return orig_talker_gen(*args, **kwargs)
                self._model.talker.generate = _patched_talker_gen

            logger.info("Qwen3-TTS [%s] successfully loaded!", variant)

        except Exception as e:
            logger.exception("Failed to load Qwen3-TTS from %s", load_path)
            self._model = None
            raise

    async def unload(self) -> None:
        """Выгрузить модель и полностью освободить VRAM."""
        if self._model is not None:
            del self._model
            self._model = None
            self._variant = None
            self._model_path = None

            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
            except Exception:
                pass

            gc.collect()
            logger.info("Qwen3-TTS unloaded from memory")

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
        Синтез речи с клонированием голоса через реальный API qwen-tts.
        """
        if not self.is_loaded():
            raise RuntimeError("Qwen3-TTS не загружен в память. Вызовите load().")

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
        """
        Синхронный вызов generate_voice_clone или create_voice_clone_prompt.
        Возвращает (audio_np, sample_rate).
        """
        import torch

        if seed is not None:
            torch.manual_seed(seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(seed)

        # 3. Преобразуем язык через маппинг
        lang_full = LANGUAGE_MAP.get(language.lower(), "Russian")

        # 2. Вызываем либо generate_voice_clone, либо create_voice_clone_prompt
        wavs = None
        sr = self._sample_rate

        try:
            if hasattr(self._model, "generate_voice_clone"):
                res = self._model.generate_voice_clone(
                    text=text,
                    language=lang_full,
                    ref_audio=(ref_audio, ref_sr),
                    ref_text=ref_text,
                    max_new_tokens=600,
                    synced_gpus=False,
                )
                if isinstance(res, tuple):
                    wavs, sr = res
                else:
                    wavs = res
            elif hasattr(self._model, "create_voice_clone_prompt"):
                prompt = self._model.create_voice_clone_prompt(
                    ref_audio=(ref_audio, ref_sr),
                    ref_text=ref_text,
                )
                res = self._model.generate_voice_clone(
                    text=text,
                    language=lang_full,
                    voice_clone_prompt=prompt,
                    max_new_tokens=600,
                    synced_gpus=False,
                )
                if isinstance(res, tuple):
                    wavs, sr = res
                else:
                    wavs = res
            else:
                raise AttributeError(
                    "Qwen3TTSModel не имеет методов generate_voice_clone или create_voice_clone_prompt"
                )
        except torch.cuda.OutOfMemoryError as e:
            raise RuntimeError(
                "Нехватка видеопамяти (VRAM OOM) при синтезе Qwen. "
                "Закройте другие GPU-приложения или переключитесь на модель 0.6B."
            ) from e
        except Exception as e:
            err_str = str(e).lower()
            if "out of memory" in err_str:
                raise RuntimeError(
                    "Нехватка видеопамяти (VRAM OOM) при синтезе Qwen. "
                    "Закройте другие GPU-приложения или переключитесь на модель 0.6B."
                ) from e
            if "meta" in err_str and "device" in err_str:
                raise RuntimeError(
                    "Ошибка meta-тензоров при оффлоаде. Перезагрузите модель через экран «Модели»."
                ) from e
            raise

        # Извлекаем wavs[0]
        if isinstance(wavs, (list, tuple)) and len(wavs) > 0:
            first_wav = wavs[0]
        else:
            first_wav = wavs

        # Конвертация в numpy float32
        if isinstance(first_wav, torch.Tensor):
            audio_np = first_wav.detach().cpu().float().numpy()
        else:
            audio_np = np.asarray(first_wav, dtype=np.float32)

        # Удаляем лишние размерности (например, (1, N) -> (N,))
        if audio_np.ndim > 1:
            audio_np = audio_np.squeeze()

        return audio_np, int(sr)

    def languages(self) -> List[str]:
        """Список поддерживаемых языков (ISO 639-1)."""
        if self._model is not None and hasattr(self._model, "get_supported_languages"):
            try:
                raw_langs = self._model.get_supported_languages()
                result = []
                for l in raw_langs:
                    code = _REVERSE_LANG_MAP.get(str(l).lower(), str(l).lower())
                    result.append(code)
                if result:
                    return result
            except Exception:
                pass
        return list(LANGUAGE_MAP.keys())


# Регистрируем движок в реестре
_qwen_engine = QwenTTSEngine()
register_tts(_qwen_engine)
