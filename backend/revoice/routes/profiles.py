"""
Voice profiles CRUD.
GET    /api/profiles        — список профилей
POST   /api/profiles        — создать профиль
GET    /api/profiles/{id}   — получить профиль
PATCH  /api/profiles/{id}   — обновить профиль
DELETE /api/profiles/{id}   — удалить профиль
POST   /api/profiles/{id}/samples — добавить сэмпл
DELETE /api/profiles/{id}/samples/{sid} — удалить сэмпл
"""
from __future__ import annotations
import logging
import shutil
import uuid
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database.session import get_db
from ..database.models import VoiceProfile, VoiceSample
from ..config import settings
from ..services.sample_qa import validate_sample

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/profiles", tags=["profiles"])


# ---------- Pydantic schemas ----------

class SampleOut(BaseModel):
    id: str
    audio_path: str
    reference_text: str
    duration_sec: Optional[float]
    rms_median: Optional[float]
    is_valid: bool
    rejection_reason: Optional[str]

    class Config:
        from_attributes = True


class ProfileOut(BaseModel):
    id: str
    name: str
    description: Optional[str]
    language: str
    default_engine: Optional[str]
    effects_chain: Optional[str]
    sample_count: int = 0
    generation_count: int = 0
    created_at: str
    updated_at: str
    samples: List[SampleOut] = []

    class Config:
        from_attributes = True


class ProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    language: str = Field(default="ru", pattern="^[a-z]{2}(-[A-Z]{2})?$")
    default_engine: Optional[str] = None


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    language: Optional[str] = None
    default_engine: Optional[str] = None
    effects_chain: Optional[str] = None  # JSON string


# ---------- Helpers ----------

def _profile_or_404(profile: Optional[VoiceProfile]) -> VoiceProfile:
    if profile is None:
        raise HTTPException(status_code=404, detail="Профиль не найден")
    return profile


async def _get_profile(profile_id: str, db: AsyncSession) -> VoiceProfile:
    stmt = select(VoiceProfile).where(VoiceProfile.id == profile_id)
    result = await db.execute(stmt)
    return _profile_or_404(result.scalar_one_or_none())


def _to_out(p: VoiceProfile) -> ProfileOut:
    samples = [
        SampleOut(
            id=s.id,
            audio_path=s.audio_path,
            reference_text=s.reference_text,
            duration_sec=s.duration_sec,
            rms_median=s.rms_median,
            is_valid=s.is_valid,
            rejection_reason=s.rejection_reason,
        )
        for s in (p.samples or [])
    ]
    return ProfileOut(
        id=p.id,
        name=p.name,
        description=p.description,
        language=p.language,
        default_engine=p.default_engine,
        effects_chain=p.effects_chain,
        sample_count=len(p.samples or []),
        generation_count=len(p.generations or []),
        created_at=p.created_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
        samples=samples,
    )


# ---------- Routes ----------

@router.get("", response_model=List[ProfileOut])
async def list_profiles(db: AsyncSession = Depends(get_db)) -> List[ProfileOut]:
    """Список всех голосовых профилей."""
    stmt = select(VoiceProfile).order_by(VoiceProfile.created_at.desc())
    result = await db.execute(stmt)
    profiles = result.scalars().all()
    return [_to_out(p) for p in profiles]


@router.post("", response_model=ProfileOut, status_code=201)
async def create_profile(
    body: ProfileCreate,
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    """Создать новый голосовой профиль."""
    profile = VoiceProfile(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        language=body.language,
        default_engine=body.default_engine,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    logger.info("Created profile %s: %s", profile.id, profile.name)
    return _to_out(profile)


@router.get("/{profile_id}", response_model=ProfileOut)
async def get_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    """Получить профиль по ID."""
    profile = await _get_profile(profile_id, db)
    return _to_out(profile)


@router.patch("/{profile_id}", response_model=ProfileOut)
async def update_profile(
    profile_id: str,
    body: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    """Обновить профиль."""
    profile = await _get_profile(profile_id, db)
    if body.name is not None:
        profile.name = body.name
    if body.description is not None:
        profile.description = body.description
    if body.language is not None:
        profile.language = body.language
    if body.default_engine is not None:
        profile.default_engine = body.default_engine
    if body.effects_chain is not None:
        profile.effects_chain = body.effects_chain
    await db.commit()
    await db.refresh(profile)
    return _to_out(profile)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Удалить профиль и все его сэмплы."""
    profile = await _get_profile(profile_id, db)
    # Remove voice directory
    voice_dir = settings.voices_dir / profile_id
    if voice_dir.exists():
        shutil.rmtree(voice_dir, ignore_errors=True)
    await db.delete(profile)
    await db.commit()
    logger.info("Deleted profile %s", profile_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{profile_id}/samples", response_model=SampleOut, status_code=201)
async def add_sample(
    profile_id: str,
    reference_text: str = Form(..., min_length=1, max_length=1000),
    audio: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> SampleOut:
    """
    Добавить аудио-сэмпл к профилю.
    Проводит автоматическую QA-проверку (RMS, длительность, транскрипт).
    """
    profile = await _get_profile(profile_id, db)

    # Save audio file
    sample_id = str(uuid.uuid4())
    voice_dir = settings.voices_dir / profile_id
    voice_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(audio.filename or "sample.wav").suffix or ".wav"
    audio_path = voice_dir / f"{sample_id}{ext}"

    content = await audio.read()
    audio_path.write_bytes(content)

    # QA validation
    qa = await validate_sample(audio_path, reference_text)

    sample = VoiceSample(
        id=sample_id,
        profile_id=profile_id,
        audio_path=str(audio_path),
        reference_text=reference_text,
        duration_sec=qa.duration_sec,
        rms_median=qa.rms_median,
        sample_rate=qa.sample_rate,
        is_valid=qa.is_valid,
        rejection_reason=qa.rejection_reason,
    )
    db.add(sample)
    await db.commit()
    await db.refresh(sample)

    if not qa.is_valid:
        logger.warning("Sample %s rejected: %s", sample_id, qa.rejection_reason)

    return SampleOut(
        id=sample.id,
        audio_path=sample.audio_path,
        reference_text=sample.reference_text,
        duration_sec=sample.duration_sec,
        rms_median=sample.rms_median,
        is_valid=sample.is_valid,
        rejection_reason=sample.rejection_reason,
    )


@router.delete("/{profile_id}/samples/{sample_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_sample(
    profile_id: str,
    sample_id: str,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Удалить сэмпл."""
    stmt = select(VoiceSample).where(
        VoiceSample.id == sample_id,
        VoiceSample.profile_id == profile_id,
    )
    result = await db.execute(stmt)
    sample = result.scalar_one_or_none()
    if sample is None:
        raise HTTPException(status_code=404, detail="Сэмпл не найден")

    # Remove file
    p = Path(sample.audio_path)
    if p.exists():
        p.unlink()

    await db.delete(sample)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
