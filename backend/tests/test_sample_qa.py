"""
Тесты QA-валидации сэмплов.
"""
import pytest
import numpy as np
import soundfile as sf
from pathlib import Path
import tempfile

from revoice.services.sample_qa import validate_sample


async def _make_wav(duration: float, sr: int = 22050, rms: float = 0.1) -> Path:
    t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
    audio = (rms * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(f.name, audio, sr)
    return Path(f.name)


@pytest.mark.asyncio
async def test_valid_sample():
    path = await _make_wav(5.0)
    result = await validate_sample(path, "Привет, мир. Тестовый текст.")
    assert result.is_valid, result.rejection_reason
    assert result.duration_sec >= 3.0


@pytest.mark.asyncio
async def test_too_short():
    path = await _make_wav(1.5)
    result = await validate_sample(path, "Привет")
    assert not result.is_valid
    assert "короткий" in result.rejection_reason.lower() or "short" in result.rejection_reason.lower()


@pytest.mark.asyncio
async def test_empty_text():
    path = await _make_wav(5.0)
    result = await validate_sample(path, "")
    assert not result.is_valid
    assert "транскрипт" in result.rejection_reason.lower() or "пустой" in result.rejection_reason.lower()


@pytest.mark.asyncio
async def test_too_quiet():
    path = await _make_wav(5.0, rms=0.001)  # Almost silent
    result = await validate_sample(path, "Тихий сэмпл")
    assert not result.is_valid
    assert "тихий" in result.rejection_reason.lower() or "rms" in result.rejection_reason.lower()
