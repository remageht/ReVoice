"""
Тесты аудио-эффектов.
Правило B: длительность ±1%, пик ≤ 0.99.
"""
import pytest
import numpy as np
from revoice.services.effects import (
    normalize_audio,
    apply_effects_chain,
    effect_pitch_shift,
)


def make_audio(duration_sec: float = 5.0, sr: int = 22050) -> tuple:
    t = np.linspace(0, duration_sec, int(sr * duration_sec), dtype=np.float32)
    audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    return audio, sr


def test_normalize_peak():
    audio, sr = make_audio()
    result = normalize_audio(audio, target_db=-3.0)
    peak = float(np.max(np.abs(result)))
    assert peak <= 0.99, f"Peak {peak} exceeds 0.99"


def test_normalize_duration():
    audio, sr = make_audio(5.0)
    result = normalize_audio(audio, target_db=-3.0)
    # Duration must be within ±1%
    assert abs(len(result) - len(audio)) / len(audio) < 0.01


def test_effects_chain_normalize():
    audio, sr = make_audio(5.0)
    result = apply_effects_chain(audio, sr, [{"name": "normalize", "target_db": -3.0}])
    peak = float(np.max(np.abs(result)))
    assert peak <= 0.99


def test_effects_chain_unknown_ignored():
    audio, sr = make_audio()
    # Should not crash on unknown effect
    result = apply_effects_chain(audio, sr, [{"name": "nonexistent_effect_xyz"}])
    assert result is not None
    assert len(result) == len(audio)


def test_normalize_silent_audio():
    """Silent audio should not crash normalize."""
    audio = np.zeros(22050, dtype=np.float32)
    result = normalize_audio(audio)
    assert result is not None
    assert not np.any(np.isnan(result))
