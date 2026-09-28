"""
Models/engines management.
GET /api/models — список движков с их статусом.
POST /api/models/{engine_id}/load — загрузить движок.
POST /api/models/{engine_id}/unload — выгрузить движок.
"""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..backends import list_tts_engines, get_tts, EngineInfo, _TTS_REGISTRY

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/models", tags=["models"])


class ModelStatus(BaseModel):
    engine_id: str
    display_name: str
    hf_repo_id: str
    license: str
    size_mb: int
    languages: list[str]
    supports_cloning: bool
    requires_gpu: bool
    model_variants: list[str]
    is_loaded: bool


class LoadRequest(BaseModel):
    variant: str = "default"
    device: str = "cuda"


@router.get("", response_model=list[ModelStatus])
async def list_models() -> list[ModelStatus]:
    """Список всех зарегистрированных TTS-движков."""
    result = []
    for info in list_tts_engines():
        engine = _TTS_REGISTRY.get(info.engine_id)
        result.append(ModelStatus(
            **info.__dict__,
            is_loaded=engine.is_loaded() if engine else False,
        ))
    return result


@router.post("/{engine_id}/load", response_model=dict)
async def load_model(engine_id: str, req: LoadRequest) -> dict:
    """Загрузить TTS-движок в память."""
    try:
        engine = get_tts(engine_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if engine.is_loaded():
        return {"status": "already_loaded", "engine_id": engine_id}

    try:
        await engine.load(variant=req.variant, device=req.device)
        return {"status": "loaded", "engine_id": engine_id}
    except Exception as e:
        logger.exception("Failed to load engine %s", engine_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{engine_id}/unload", response_model=dict)
async def unload_model(engine_id: str) -> dict:
    """Выгрузить TTS-движок."""
    try:
        engine = get_tts(engine_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await engine.unload()
    return {"status": "unloaded", "engine_id": engine_id}
