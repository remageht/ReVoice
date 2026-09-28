"""
TTS synthesis service.
Обрабатывает нарезку по предложениям, кроссфейд и склейку.
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from pathlib import Path
from typing import List, Tuple, Optional

import numpy as np

from ..backends import get_tts
from .chunker import split_text_ru
from .effects import apply_effects_chain, normalize_audio

logger = logging.getLogger(__name__)


async def synthesize_text(
    *,
    text: str,
    samples: List[Tuple[str, str]],  # [(audio_path, ref_text), ...]
    engine_id: str,
    language: str = "ru",
    seed: Optional[int] = None,
    max_chunk_chars: int = 200,
    crossfade_ms: int = 50,
    normalize: bool = True,
    output_dir: Path,
    gen_id: str,
    effects_chain: Optional[List[dict]] = None,
) -> Tuple[Path, float]:
    """
    Синтез текста с клонированием голоса.
    Нарезает на предложения, генерирует каждое, склеивает с кроссфейдом.
    """
    engine = get_tts(engine_id)
    if not engine.is_loaded():
        await engine.load(device="cuda")

    # Load reference audio (use first valid sample)
    ref_audio_path, ref_text = samples[0]
    ref_audio, ref_sr = _load_audio(ref_audio_path)

    # Split text into chunks
    chunks = split_text_ru(text, max_chars=max_chunk_chars)
    logger.info("Synthesis: %d chunks from %d chars", len(chunks), len(text))

    # Synthesize each chunk
    audio_parts: List[np.ndarray] = []
    sample_rate = 22050

    for i, chunk in enumerate(chunks):
        if not chunk.strip():
            continue
        logger.debug("Synthesizing chunk %d/%d: %s", i+1, len(chunks), chunk[:40])
        audio, sr = await engine.synthesize(
            chunk,
            ref_audio=ref_audio,
            ref_sr=ref_sr,
            ref_text=ref_text,
            language=language,
            seed=seed,
        )
        sample_rate = sr
        audio_parts.append(audio.astype(np.float32))

    if not audio_parts:
        raise ValueError("Синтез не вернул аудио")

    # Crossfade join
    result = _crossfade_join(audio_parts, crossfade_ms=crossfade_ms, sample_rate=sample_rate)

    # Normalize
    if normalize:
        result = normalize_audio(result, target_db=-3.0)

    # Apply effects
    if effects_chain:
        result = apply_effects_chain(result, sample_rate, effects_chain)

    # Save output
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{gen_id}.wav"
    _save_wav(result, sample_rate, out_path)

    duration = len(result) / sample_rate
    logger.info("Synthesis complete: %.2f sec → %s", duration, out_path)
    return out_path, round(duration, 2)


def _load_audio(path: str) -> Tuple[np.ndarray, int]:
    import soundfile as sf
    data, sr = sf.read(path, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    return data, sr


def _save_wav(audio: np.ndarray, sample_rate: int, path: Path) -> None:
    import soundfile as sf
    sf.write(str(path), audio, sample_rate, subtype="PCM_16")


def _crossfade_join(
    parts: List[np.ndarray],
    crossfade_ms: int,
    sample_rate: int,
) -> np.ndarray:
    """Склеить аудио-фрагменты с кроссфейдом."""
    if len(parts) == 1:
        return parts[0]

    cf_samples = int(crossfade_ms * sample_rate / 1000)

    if cf_samples == 0:
        return np.concatenate(parts)

    result = parts[0].copy()
    for part in parts[1:]:
        if len(result) < cf_samples or len(part) < cf_samples:
            result = np.concatenate([result, part])
            continue

        fade_out = np.linspace(1.0, 0.0, cf_samples, dtype=np.float32)
        fade_in = np.linspace(0.0, 1.0, cf_samples, dtype=np.float32)

        # Blend the overlap region
        overlap = result[-cf_samples:] * fade_out + part[:cf_samples] * fade_in
        result = np.concatenate([result[:-cf_samples], overlap, part[cf_samples:]])

    return result
