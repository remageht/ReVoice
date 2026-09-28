import pytest
import tempfile
from pathlib import Path
from httpx import AsyncClient, ASGITransport

from revoice.main import app
from revoice.services.models_manager import (
    MODEL_CATALOGUE,
    validate_model_directory,
    set_custom_path,
    get_models_dir,
    migrate_models_directory,
    check_model_status,
)


def test_validate_missing_files(tmp_path: Path):
    """Validation must fail and list missing files if required files are absent."""
    # Create empty dir
    val = validate_model_directory("qwen-tts-0.6b", tmp_path)
    assert val["is_valid"] is False
    assert "config.json" in val["error"]
    assert "model.safetensors" in val["error"]


def test_validate_valid_files(tmp_path: Path):
    """Validation must succeed when all required files are present."""
    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "model.safetensors").write_bytes(b"\x00" * 1024)

    val = validate_model_directory("qwen-tts-0.6b", tmp_path)
    assert val["is_valid"] is True
    assert val.get("error") is None


def test_custom_path_linking(tmp_path: Path):
    """Setting custom path must persist and update model status."""
    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "model.safetensors").write_bytes(b"\x00" * 1024)

    ok, err, warn = set_custom_path("qwen-tts-0.6b", tmp_path)
    assert ok is True
    assert err is None

    status = check_model_status("qwen-tts-0.6b")
    assert status["is_custom_path"] is True
    assert status["disk_status"] == "downloaded"
    assert status["local_path"] == str(tmp_path.resolve())


@pytest.mark.asyncio
async def test_models_api_endpoints(tmp_path: Path):
    """API endpoints for models list, dir, custom path, unload."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. List models
        r = await client.get("/api/models")
        assert r.status_code == 200
        models = r.json()
        assert len(models) >= 4
        types = {m["type"] for m in models}
        assert "TTS" in types
        assert "STT" in types

        # 2. Get dir
        r_dir = await client.get("/api/models/dir")
        assert r_dir.status_code == 200
        assert "models_dir" in r_dir.json()

        # 3. Invalid custom path -> 422 with clear error
        r_bad = await client.post("/api/models/qwen-tts-1.7b/set-path", json={
            "path": str(tmp_path)
        })
        assert r_bad.status_code == 422
        assert "config.json" in r_bad.json()["detail"]

        # 4. Valid custom path
        (tmp_path / "config.json").write_text("{}")
        (tmp_path / "model.safetensors").write_bytes(b"\x00" * 1024)
        r_good = await client.post("/api/models/qwen-tts-1.7b/set-path", json={
            "path": str(tmp_path)
        })
        assert r_good.status_code == 200
        assert r_good.json()["status"] == "linked"

        # 5. Unload all
        r_un = await client.post("/api/models/unload-all")
        assert r_un.status_code == 200
