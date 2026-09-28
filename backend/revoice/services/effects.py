"""
Audio effects pipeline.
Каждый эффект: apply(wav, sr, **params) -> wav
Правило B: длительность ±1%, пик ≤ 0.99.
"""
from __future__ import annotations
import logging
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Effects registry
# ---------------------------------------------------------------------------

_EFFECTS: dict[str, callable] = {}


def register_effect(name: str):
    """Decorator to register an audio effect."""
    def decorator(fn):
        _EFFECTS[name] = fn
        return fn
    return decorator


def apply_effects_chain(
    audio: np.ndarray,
    sample_rate: int,
    chain: List[dict],
) -> np.ndarray:
    """
    Применить цепочку эффектов к аудио.
    chain — список {"name": str, **params}
    """
    result = audio.astype(np.float32)
    for effect_cfg in chain:
        name = effect_cfg.get("name")
        if not name:
            continue
        params = {k: v for k, v in effect_cfg.items() if k != "name"}
        if name not in _EFFECTS:
            logger.warning("Unknown effect: %s", name)
            continue
        try:
            result = _EFFECTS[name](result, sample_rate, **params)
            # Safety clip
            result = np.clip(result, -0.99, 0.99)
        except Exception as e:
            logger.error("Effect %s failed: %s", name, e)
    return result


# ---------------------------------------------------------------------------
# Built-in effects
# ---------------------------------------------------------------------------

@register_effect("normalize")
def effect_normalize(audio: np.ndarray, sr: int, target_db: float = -3.0) -> np.ndarray:
    """Нормализация до target_db."""
    return normalize_audio(audio, target_db=target_db)


@register_effect("pitch_shift")
def effect_pitch_shift(audio: np.ndarray, sr: int, semitones: float = 0.0) -> np.ndarray:
    """Сдвиг высоты тона (±полутона)."""
    if semitones == 0.0:
        return audio
    try:
        from pedalboard import Pedalboard, PitchShift
        board = Pedalboard([PitchShift(semitones=semitones)])
        # pedalboard expects (channels, samples)
        return board(audio[np.newaxis, :], sr)[0]
    except ImportError:
        logger.warning("pedalboard not installed, pitch_shift skipped")
        return audio


@register_effect("reverb")
def effect_reverb(
    audio: np.ndarray,
    sr: int,
    room_size: float = 0.15,
    damping: float = 0.5,
    wet_level: float = 0.1,
    dry_level: float = 0.9,
) -> np.ndarray:
    """Реверберация через pedalboard."""
    try:
        from pedalboard import Pedalboard, Reverb
        board = Pedalboard([Reverb(
            room_size=room_size,
            damping=damping,
            wet_level=wet_level,
            dry_level=dry_level,
        )])
        return board(audio[np.newaxis, :], sr)[0]
    except ImportError:
        logger.warning("pedalboard not installed, reverb skipped")
        return audio


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def normalize_audio(audio: np.ndarray, target_db: float = -3.0) -> np.ndarray:
    """Нормализовать аудио до target_db (RMS-based)."""
    audio = audio.astype(np.float32)
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms < 1e-8:
        return audio
    target_linear = 10 ** (target_db / 20)
    gain = target_linear / rms
    result = audio * gain
    # Hard clip to prevent clipping above 0.99
    peak = float(np.max(np.abs(result)))
    if peak > 0.99:
        result = result * (0.99 / peak)
    return result


def list_effects() -> List[dict]:
    """Список доступных эффектов."""
    return [{"name": k} for k in _EFFECTS.keys()]
