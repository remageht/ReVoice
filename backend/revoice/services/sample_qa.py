"""
QA-валидация аудио-сэмплов голоса.

Правила (Rule C из спеки):
- длительность ≥ 3 сек и ≤ 30 сек
- медианный RMS ≥ 0.02 (не тишина)
- reference_text непустой
- частота дискретизации ≥ 16000 Гц
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MIN_DURATION_SEC = 3.0
MAX_DURATION_SEC = 30.0
MIN_RMS = 0.02
MIN_SAMPLE_RATE = 16000


@dataclass
class QAResult:
    is_valid: bool
    rejection_reason: Optional[str]
    duration_sec: Optional[float]
    rms_median: Optional[float]
    sample_rate: Optional[int]


async def validate_sample(
    audio_path: Path,
    reference_text: str,
) -> QAResult:
    """
    Проверить аудио-сэмпл на пригодность для клонирования голоса.
    Возвращает QAResult. Сервер не падает при невалидном сэмпле.
    """
    # Check reference text
    if not reference_text or not reference_text.strip():
        return QAResult(
            is_valid=False,
            rejection_reason="Транскрипт сэмпла пустой. Укажите дословный текст записи.",
            duration_sec=None,
            rms_median=None,
            sample_rate=None,
        )

    # Load audio
    try:
        import soundfile as sf
        data, sr = sf.read(str(audio_path), dtype="float32", always_2d=False)
    except Exception as e:
        return QAResult(
            is_valid=False,
            rejection_reason=f"Не удалось прочитать аудио: {e}",
            duration_sec=None,
            rms_median=None,
            sample_rate=None,
        )

    # Convert stereo to mono
    if data.ndim > 1:
        data = data.mean(axis=1)

    duration = len(data) / sr
    # Compute RMS in 20ms frames
    frame_size = max(1, int(sr * 0.02))
    frames = [data[i:i+frame_size] for i in range(0, len(data) - frame_size, frame_size)]
    if frames:
        rms_values = [float(np.sqrt(np.mean(f**2))) for f in frames]
        rms_median = float(np.median(rms_values))
    else:
        rms_median = 0.0

    # Checks
    if sr < MIN_SAMPLE_RATE:
        return QAResult(
            is_valid=False,
            rejection_reason=f"Слишком низкая частота дискретизации: {sr} Гц (минимум {MIN_SAMPLE_RATE} Гц).",
            duration_sec=round(duration, 2),
            rms_median=round(rms_median, 4),
            sample_rate=sr,
        )

    if duration < MIN_DURATION_SEC:
        return QAResult(
            is_valid=False,
            rejection_reason=f"Сэмпл слишком короткий: {duration:.1f} сек (минимум {MIN_DURATION_SEC} сек).",
            duration_sec=round(duration, 2),
            rms_median=round(rms_median, 4),
            sample_rate=sr,
        )

    if duration > MAX_DURATION_SEC:
        return QAResult(
            is_valid=False,
            rejection_reason=f"Сэмпл слишком длинный: {duration:.1f} сек (максимум {MAX_DURATION_SEC} сек).",
            duration_sec=round(duration, 2),
            rms_median=round(rms_median, 4),
            sample_rate=sr,
        )

    if rms_median < MIN_RMS:
        return QAResult(
            is_valid=False,
            rejection_reason=f"Сэмпл слишком тихий (RMS={rms_median:.4f}). Говорите громче или используйте другой микрофон.",
            duration_sec=round(duration, 2),
            rms_median=round(rms_median, 4),
            sample_rate=sr,
        )

    logger.info(
        "Sample QA passed: dur=%.2fs rms=%.4f sr=%d",
        duration, rms_median, sr,
    )
    return QAResult(
        is_valid=True,
        rejection_reason=None,
        duration_sec=round(duration, 2),
        rms_median=round(rms_median, 4),
        sample_rate=sr,
    )
