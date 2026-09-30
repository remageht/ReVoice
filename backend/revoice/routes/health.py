"""
Health-check endpoint.
GET /api/health — возвращает статус движка, GPU, версию.
"""
from __future__ import annotations
import sys
import platform
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..backends import list_tts_engines
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["health"])

_start_time = datetime.now(timezone.utc)


class GpuInfo(BaseModel):
    available: bool
    name: Optional[str] = None
    vram_total_mb: Optional[int] = None
    vram_free_mb: Optional[int] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_sec: float
    platform: str
    python_version: str
    gpu: GpuInfo
    loaded_engines: list[str]
    data_dir: str


def _gpu_info() -> GpuInfo:
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            free, total = torch.cuda.mem_get_info(0)
            return GpuInfo(
                available=True,
                name=props.name,
                vram_total_mb=total // 1024 // 1024,
                vram_free_mb=free // 1024 // 1024,
            )
    except Exception:
        pass
    return GpuInfo(available=False)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Статус сервера ReVoice."""
    from ..backends import _TTS_REGISTRY
    uptime = (datetime.now(timezone.utc) - _start_time).total_seconds()
    loaded = [eid for eid, e in _TTS_REGISTRY.items() if e.is_loaded()]
    return HealthResponse(
        status="ok",
        version="0.1.3",
        uptime_sec=round(uptime, 1),
        platform=platform.platform(),
        python_version=sys.version.split()[0],
        gpu=_gpu_info(),
        loaded_engines=loaded,
        data_dir=str(settings.data_dir),
    )
