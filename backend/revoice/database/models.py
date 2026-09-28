"""
SQLAlchemy ORM models for ReVoice.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional, List
import json

from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, Text, ForeignKey, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class VoiceProfile(Base):
    __tablename__ = "voice_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="ru")
    default_engine: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    effects_chain: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    avatar_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    samples: Mapped[List["VoiceSample"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )
    generations: Mapped[List["Generation"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", lazy="selectin"
    )


class VoiceSample(Base):
    __tablename__ = "voice_samples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("voice_profiles.id", ondelete="CASCADE"), nullable=False
    )
    audio_path: Mapped[str] = mapped_column(String(500), nullable=False)
    reference_text: Mapped[str] = mapped_column(Text, nullable=False)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rms_median: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sample_rate: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    peak: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    verdict: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    rms_profile_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    profile: Mapped["VoiceProfile"] = relationship(back_populates="samples")


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("voice_profiles.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="ru")
    engine: Mapped[str] = mapped_column(String(50), default="qwen")
    model_size: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    audio_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    duration_sec: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/completed/failed
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effects_chain: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    profile: Mapped["VoiceProfile"] = relationship(back_populates="generations")
