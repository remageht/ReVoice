"""
Effects API.
GET /api/effects — список эффектов.
"""
from __future__ import annotations
from fastapi import APIRouter
from ..services.effects import list_effects

router = APIRouter(prefix="/api/effects", tags=["effects"])


@router.get("", response_model=list[dict])
async def get_effects() -> list[dict]:
    """Список доступных аудио-эффектов."""
    return list_effects()
