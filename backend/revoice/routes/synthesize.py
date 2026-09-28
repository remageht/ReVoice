"""
Synthesize route.
POST /api/synthesize — синтез речи с клонированием голоса.
GET  /api/synthesize/{gen_id}/progress — SSE прогресс.
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from pathlib import Path
from typing import Optional, List, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database.session import get_db
from ..database.models import Generation, VoiceProfile, VoiceSample
from ..config import settings
from ..services.tts import synthesize_text
from ..backends import get_tts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["synthesize"])


class SynthRequest(BaseModel):
    profile_id: str
    text: str = Field(..., min_length=1, max_length=50000)
    engine: str = Field(default="stub")
    model_variant: str = Field(default="default")
    language: str = Field(default="ru")
    seed: Optional[int] = None
    max_chunk_chars: int = Field(default=200, ge=50, le=1000)
    crossfade_ms: int = Field(default=50, ge=0, le=500)
    normalize: bool = True
    effects_chain: Optional[List[dict]] = None


class SynthResponse(BaseModel):
    generation_id: str
    status: str
    audio_path: Optional[str] = None
    duration_sec: Optional[float] = None
    engine: str


@router.post("/synthesize", response_model=SynthResponse, status_code=201)
async def synthesize(
    req: SynthRequest,
    db: AsyncSession = Depends(get_db),
) -> SynthResponse:
    """Синтез речи с клонированием голоса."""
    # Validate profile
    stmt = select(VoiceProfile).where(VoiceProfile.id == req.profile_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Профиль не найден")

    # Get valid samples
    stmt2 = select(VoiceSample).where(
        VoiceSample.profile_id == req.profile_id,
        VoiceSample.is_valid == True,
    )
    result2 = await db.execute(stmt2)
    samples = result2.scalars().all()

    if not samples:
        raise HTTPException(
            status_code=422,
            detail="Нет валидных сэмплов голоса. Добавьте хотя бы один сэмпл (3–30 сек).",
        )

    gen_id = str(uuid.uuid4())

    # Create pending generation record
    gen = Generation(
        id=gen_id,
        profile_id=req.profile_id,
        text=req.text,
        language=req.language,
        engine=req.engine,
        model_size=req.model_variant,
        seed=req.seed,
        status="pending",
    )
    db.add(gen)
    await db.commit()

    # Run synthesis
    try:
        audio_path, duration = await synthesize_text(
            text=req.text,
            samples=[(s.audio_path, s.reference_text) for s in samples],
            engine_id=req.engine,
            language=req.language,
            seed=req.seed,
            max_chunk_chars=req.max_chunk_chars,
            crossfade_ms=req.crossfade_ms,
            normalize=req.normalize,
            output_dir=settings.generations_dir,
            gen_id=gen_id,
        )
        gen.audio_path = str(audio_path)
        gen.duration_sec = duration
        gen.status = "completed"
    except Exception as e:
        logger.exception("Synthesis failed for gen %s", gen_id)
        gen.status = "failed"
        gen.error = str(e)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Синтез не удался: {e}")

    await db.commit()

    return SynthResponse(
        generation_id=gen_id,
        status="completed",
        audio_path=str(audio_path),
        duration_sec=duration,
        engine=req.engine,
    )


@router.get("/history", response_model=List[dict])
async def get_history(
    profile_id: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    """История генераций."""
    stmt = select(Generation).order_by(Generation.created_at.desc()).limit(limit)
    if profile_id:
        stmt = stmt.where(Generation.profile_id == profile_id)
    result = await db.execute(stmt)
    gens = result.scalars().all()
    return [
        {
            "id": g.id,
            "profile_id": g.profile_id,
            "text": g.text[:100],
            "engine": g.engine,
            "language": g.language,
            "status": g.status,
            "duration_sec": g.duration_sec,
            "audio_path": g.audio_path,
            "created_at": g.created_at.isoformat(),
        }
        for g in gens
    ]
