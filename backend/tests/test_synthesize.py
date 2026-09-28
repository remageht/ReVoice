import pytest
import numpy as np
import soundfile as sf
import tempfile
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from revoice.main import app
from revoice.config import settings


@pytest.fixture
def sample_wav(tmp_path: Path) -> Path:
    # 5 seconds of 440Hz sine wave
    sr = 22050
    t = np.linspace(0, 5.0, int(sr * 5.0), dtype=np.float32)
    audio = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    p = tmp_path / "sample.wav"
    sf.write(str(p), audio, sr)
    return p


@pytest.mark.asyncio
async def test_synthesize_flow(sample_wav: Path):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Create profile
        r = await client.post("/api/profiles", json={
            "name": "Тестовый профиль для синтеза",
            "language": "ru",
        })
        assert r.status_code == 201
        pid = r.json()["id"]

        # 2. Add valid sample
        with open(sample_wav, "rb") as f:
            r_sample = await client.post(
                f"/api/profiles/{pid}/samples",
                data={"reference_text": "Это тестовый эталон для клонирования голоса."},
                files={"audio": ("sample.wav", f, "audio/wav")},
            )
        assert r_sample.status_code == 201, r_sample.text
        assert r_sample.json()["is_valid"] is True

        # 3. Synthesize with stub engine
        r_synth = await client.post("/api/synthesize", json={
            "profile_id": pid,
            "text": "Привет! Это проверка синтеза речи студии ReVoice.",
            "engine": "stub",
            "language": "ru",
            "max_chunk_chars": 100,
            "crossfade_ms": 30,
            "normalize": True,
        })
        assert r_synth.status_code == 201, r_synth.text
        data = r_synth.json()
        assert data["status"] == "completed"
        assert data["audio_path"] is not None
        assert data["duration_sec"] > 0
        assert Path(data["audio_path"]).exists()

        # 4. Check history
        r_hist = await client.get("/api/history", params={"profile_id": pid})
        assert r_hist.status_code == 200
        items = r_hist.json()
        assert len(items) >= 1
        assert items[0]["engine"] == "stub"
