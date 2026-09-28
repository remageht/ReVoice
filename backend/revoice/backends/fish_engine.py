"""
Fish Speech 1.5 engine для ReVoice.
Строго соответствует реальному API fish-speech v1.5.x:
1. Импорты:
   - from fish_speech.models.text2semantic.inference import launch_thread_safe_queue
   - from fish_speech.models.vqgan.inference import load_model as load_decoder_model
   - from fish_speech.inference_engine import TTSInferenceEngine
   - from fish_speech.utils.schema import ServeTTSRequest, ServeReferenceAudio
   - from fish_speech.text import clean_text, split_text
2. Загрузка:
   - llama_queue = launch_thread_safe_queue(checkpoint_dir, device="cuda", precision=torch.bfloat16, compile=False)
     (compile=True запрещён на Windows из-за отсутствия Triton)
   - decoder = load_decoder_model("firefly_gan_vq", checkpoint_path, device="cuda")
   - engine = TTSInferenceEngine(llama_queue, decoder, precision=torch.bfloat16, compile=False)
3. Синтез:
   - req = ServeTTSRequest(
         text=chunk,
         references=[ServeReferenceAudio(audio=ref_wav_bytes, text=ref_text_or_empty)],
         chunk_length=200,
         max_new_tokens=min(2048, max(256, len(text)*4)),
         temperature=0.7, top_p=0.7, repetition_penalty=1.2, seed=1, streaming=True
     )
   - for segment in engine.inference(req): segment.audio (float32, 44100 Гц!)
4. Особенности Fish:
   - НЕТ параметра языка (авто-детект) — маппинг ru/en не передаётся
   - Частота дискретизации 44.1 кГц (в отличие от Qwen 24 кГц)
   - Чанки нарезаются заранее через split_text(clean_text(text), 200)
5. VRAM ~3.9 ГБ:
   - Выгрузка всех остальных движков перед стартом (правило одной модели)
   - Понятная русская ошибка при OOM
"""
from __future__ import annotations
import io
import os
import sys
import gc
import asyncio
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Any
import numpy as np
import soundfile as sf

from . import EngineInfo, register_tts

logger = logging.getLogger(__name__)

# Добавляем возможные пути к репозиторию fish-speech
for _p in ["C:/dev/fish-speech", "C:\\dev\\fish-speech"]:
    if os.path.exists(_p) and _p not in sys.path:
        sys.path.insert(0, _p)


def _apply_torchaudio_compat() -> None:
    """
    Патч torchaudio.load: на Windows без FFmpeg C-библиотек torchaudio падает на torchcodec.
    Подменяем на soundfile, возвращающий (tensor, sr).
    """
    try:
        import torch
        import torchaudio

        def _compat_audio_load(filepath, backend=None, **kwargs):
            data, sr = sf.read(filepath, dtype="float32", always_2d=True)
            data = data.T  # (channels, samples)
            return torch.from_numpy(data.copy()), sr

        torchaudio.load = _compat_audio_load
        if not hasattr(torchaudio, "list_audio_backends"):
            torchaudio.list_audio_backends = lambda: ["soundfile"]
    except Exception as e:
        logger.debug("torchaudio compat patch notice: %s", e)


class FishTTSEngine:
    """
    Движок синтеза речи Fish Speech 1.5.
    Работает с очередью DualARTransformer и VQGAN декодером (Firefly).
    """

    engine_id = "fish"
    info = EngineInfo(
        engine_id="fish",
        display_name="Fish Speech 1.5",
        hf_repo_id="fishaudio/fish-speech-1.5",
        license="CC-BY-NC-SA-4.0",
        size_mb=2500,
        languages=["auto", "ru", "en", "zh", "ja", "ko", "de", "fr", "es"],
        supports_cloning=True,
        supports_instruct=False,
        requires_gpu=True,
        model_variants=["1.5"],
    )

    def __init__(self):
        self._engine = None
        self._decoder = None
        self._llama_queue = None
        self._model_path: Optional[str] = None
        self._sample_rate: int = 44100

    def is_loaded(self) -> bool:
        return self._engine is not None

    async def load(
        self,
        variant: str = "1.5",
        device: str = "cuda",
        model_path: Optional[str | Path] = None,
    ) -> None:
        """
        Загрузка моделей Fish Speech 1.5.
        Перед загрузкой выгружаются все остальные движки для соблюдения правила VRAM.
        """
        # Правило одной модели: выгружаем остальные движки
        from ..backends import _TTS_REGISTRY
        for eid, eng in _TTS_REGISTRY.items():
            if eid != self.engine_id and eng.is_loaded():
                logger.info("Unloading engine '%s' before loading Fish Speech", eid)
                await eng.unload()

        if self._engine is not None:
            await self.unload()

        await asyncio.to_thread(self._load_sync, variant, device, model_path)

    def _load_sync(
        self,
        variant: str,
        device: str,
        model_path: Optional[str | Path] = None,
    ) -> None:
        """Синхронная загрузка очереди Llama и VQGAN декодера."""
        _apply_torchaudio_compat()

        try:
            import torch
            from fish_speech.models.text2semantic.inference import launch_thread_safe_queue
            from fish_speech.models.vqgan.inference import load_model as load_decoder_model
            from fish_speech.inference_engine import TTSInferenceEngine
        except ImportError as e:
            raise ImportError(
                "Пакет fish-speech не найден. Убедитесь, что репозиторий находится в C:\\dev\\fish-speech "
                "или установлен в окружении: " + str(e)
            ) from e

        # Определяем директорию с весами
        if model_path is not None:
            chk_dir = Path(model_path)
        else:
            env_path = os.environ.get("REVOICE_TEST_FISH")
            if env_path and Path(env_path).exists():
                chk_dir = Path(env_path)
            else:
                from ..services.models_manager import get_model_path
                target = get_model_path("fish-speech-1.5")
                if target.exists():
                    chk_dir = target
                else:
                    chk_dir = Path("C:/dev/checkpoints/fish-speech-1.5")

        if not chk_dir.exists():
            raise FileNotFoundError(
                f"Директория с чекпоинтами Fish Speech 1.5 не найдена: {chk_dir}. "
                "Укажите путь или скачайте веса через экран «Модели»."
            )

        # Поиск файла декодера Firefly VQ
        decoder_pth = chk_dir / "firefly-gan-vq-fsq-8x1024-21hz-generator.pth"
        if not decoder_pth.exists():
            # Поиск любого подходящего генератора в папке
            pth_candidates = list(chk_dir.glob("*firefly*.pth")) or list(chk_dir.glob("*.pth"))
            if pth_candidates:
                decoder_pth = pth_candidates[0]
            else:
                # Проверяем fallback путь
                fallback_pth = Path("C:/dev/checkpoints/fish-speech-1.5/firefly-gan-vq-fsq-8x1024-21hz-generator.pth")
                if fallback_pth.exists():
                    decoder_pth = fallback_pth
                else:
                    raise FileNotFoundError(
                        f"Файл декодера Firefly VQ не найден в {chk_dir} "
                        "(ожидался firefly-gan-vq-fsq-8x1024-21hz-generator.pth)."
                    )

        target_device = device
        if target_device.startswith("cuda") and not torch.cuda.is_available():
            logger.warning("CUDA недоступна, запуск Fish Speech на CPU")
            target_device = "cpu"

        precision = torch.bfloat16 if target_device.startswith("cuda") else torch.float32

        logger.info(
            "Loading Fish Speech 1.5 from %s (decoder: %s) on %s...",
            chk_dir, decoder_pth.name, target_device,
        )

        try:
            # 1. Загрузка VQGAN декодера
            self._decoder = load_decoder_model("firefly_gan_vq", str(decoder_pth), device=target_device)

            # 2. Запуск потокобезопасной очереди LLAMA (compile=False строго на Windows)
            self._llama_queue = launch_thread_safe_queue(
                str(chk_dir),
                device=target_device,
                precision=precision,
                compile=False,
            )

            # 3. Создание движка инференса
            self._engine = TTSInferenceEngine(
                llama_queue=self._llama_queue,
                decoder_model=self._decoder,
                precision=precision,
                compile=False,
            )
            self._model_path = str(chk_dir)
            logger.info("Fish Speech 1.5 successfully loaded!")

        except torch.cuda.OutOfMemoryError as e:
            self._cleanup_sync()
            raise RuntimeError(
                "Нехватка видеопамяти (VRAM OOM) при загрузке Fish Speech 1.5. "
                "Закройте другие GPU-приложения или переключитесь на модель Qwen 0.6B."
            ) from e
        except Exception as e:
            if "out of memory" in str(e).lower():
                self._cleanup_sync()
                raise RuntimeError(
                    "Нехватка видеопамяти (VRAM OOM) при загрузке Fish Speech 1.5. "
                    "Закройте другие GPU-приложения или переключитесь на модель Qwen 0.6B."
                ) from e
            self._cleanup_sync()
            logger.exception("Failed to load Fish Speech 1.5 from %s", chk_dir)
            raise

    async def unload(self) -> None:
        """Полная выгрузка Fish Speech и освобождение VRAM."""
        await asyncio.to_thread(self._cleanup_sync)
        logger.info("Fish Speech 1.5 unloaded from memory")

    def _cleanup_sync(self) -> None:
        """Синхронная остановка рабочего потока и очистка памяти."""
        if self._llama_queue is not None:
            try:
                # Отправляем маркер завершения рабочему потоку
                self._llama_queue.put(None)
            except Exception:
                pass
            self._llama_queue = None

        self._decoder = None
        self._engine = None
        self._model_path = None

        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except Exception:
            pass

        gc.collect()

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
        Синтез речи с клонированием голоса через Fish Speech 1.5.
        Fish автоматически детектирует язык, поэтому параметр языка не передаётся в модель.
        Выходной звук имеет частоту дискретизации 44100 Гц.
        """
        if not self.is_loaded():
            raise RuntimeError("Fish Speech 1.5 не загружен в память. Вызовите load().")

        return await asyncio.to_thread(
            self._synthesize_sync,
            text, ref_audio, ref_sr, ref_text, seed,
        )

    def _synthesize_sync(
        self,
        text: str,
        ref_audio: np.ndarray,
        ref_sr: int,
        ref_text: str,
        seed: Optional[int],
    ) -> Tuple[np.ndarray, int]:
        """Синхронный синтез чанков текста."""
        import torch
        from fish_speech.utils.schema import ServeTTSRequest, ServeReferenceAudio

        # Импорт текстовых утилит
        try:
            from fish_speech.text import clean_text, split_text
        except ImportError:
            try:
                from fish_speech.text.clean import clean_text
            except ImportError:
                clean_text = lambda t: t.strip()

            from ..services.chunker import split_text_ru
            split_text = lambda t, c=200: split_text_ru(t, max_chars=c)

        # Кодируем эталонное аудио в байты WAV
        buf = io.BytesIO()
        sf.write(buf, ref_audio, ref_sr, format="WAV")
        ref_wav_bytes = buf.getvalue()

        # Очистка и нарезка текста на чанки по 200 символов
        cleaned = clean_text(text)
        chunks = split_text(cleaned, 200)
        if not chunks:
            chunks = [cleaned] if cleaned else [text]

        final_segments: List[np.ndarray] = []
        out_sr = self._sample_rate

        try:
            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    continue

                chunk_len = len(chunk)
                max_tokens = min(2048, max(256, int(chunk_len * 4)))

                req = ServeTTSRequest(
                    text=chunk,
                    references=[
                        ServeReferenceAudio(audio=ref_wav_bytes, text=ref_text or "")
                    ],
                    chunk_length=200,
                    max_new_tokens=max_tokens,
                    temperature=0.7,
                    top_p=0.7,
                    repetition_penalty=1.2,
                    seed=seed if seed is not None else 1,
                    streaming=True,
                )

                chunk_out = None
                for result in self._engine.inference(req):
                    if result.code == "error":
                        raise RuntimeError(f"Ошибка инференса Fish Speech: {result.error}")
                    if result.code == "segment":
                        sr, seg = result.audio
                        out_sr = sr
                        if chunk_out is None:
                            chunk_out = [seg]
                        else:
                            chunk_out.append(seg)
                    elif result.code == "final":
                        sr, full_seg = result.audio
                        out_sr = sr
                        # Если сегменты не собирались потоково, берём полный
                        if not chunk_out:
                            chunk_out = [full_seg]

                if chunk_out:
                    merged_chunk = np.concatenate(chunk_out, axis=0)
                    final_segments.append(merged_chunk.astype(np.float32))

            if not final_segments:
                raise RuntimeError("Fish Speech не вернул аудио-сегментов")

            # Склейка с микропаузой 50 мс
            gap = np.zeros(int(0.05 * out_sr), dtype=np.float32)
            joined_parts = []
            for seg in final_segments:
                joined_parts.append(seg)
                joined_parts.append(gap)
            # Убираем последний gap
            joined_audio = np.concatenate(joined_parts[:-1], axis=0)

            return joined_audio, int(out_sr)

        except torch.cuda.OutOfMemoryError as e:
            raise RuntimeError(
                "Нехватка видеопамяти (VRAM OOM) при синтезе Fish Speech 1.5. "
                "Попробуйте уменьшить размер текста или переключиться на модель Qwen 0.6B."
            ) from e
        except Exception as e:
            if "out of memory" in str(e).lower():
                raise RuntimeError(
                    "Нехватка видеопамяти (VRAM OOM) при синтезе Fish Speech 1.5. "
                    "Попробуйте уменьшить размер текста или переключиться на модель Qwen 0.6B."
                ) from e
            raise

    def languages(self) -> List[str]:
        return list(self.info.languages)


# Автоматическая регистрация движка
_fish_engine = FishTTSEngine()
register_tts(_fish_engine)
