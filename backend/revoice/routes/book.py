"""
Book mode & Text Markup API routes for ReVoice.
"""
from __future__ import annotations
import uuid
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database.session import get_db
from ..database.models import VoiceProfile, VoiceSample
from ..services.book import parse_book_text, assemble_m4b, Chapter
from ..services.text_markup import markup_emotions
from ..services.tts import synthesize_text
from ..config import settings

router = APIRouter(prefix="/api/book", tags=["book"])


class ParseBookRequest(BaseModel):
    text: str = Field(..., min_length=1)
    title: Optional[str] = "Новая книга"
    author: Optional[str] = "Автор"


class ChapterDto(BaseModel):
    index: int
    title: str
    char_count: int
    preview: str


class ParseBookResponse(BaseModel):
    id: str
    title: str
    author: str
    chapter_count: int
    chapters: List[ChapterDto]


class MarkupRequest(BaseModel):
    text: str = Field(..., min_length=1)
    intensity: str = Field(default="moderate", pattern="^(subtle|moderate|dramatic)$")


class MarkupResponse(BaseModel):
    original: str
    marked_up: str


class BuildM4BRequest(BaseModel):
    profile_id: str
    chapters: List[dict]  # list of {title: str, text: str}
    engine: str = "qwen"
    language: str = "ru"
    book_title: str = "Моя книга"
    author: str = "ReVoice"


@router.post("/parse", response_model=ParseBookResponse)
async def parse_book(req: ParseBookRequest) -> ParseBookResponse:
    """Распарсить текст книги/Markdown на главы."""
    project = parse_book_text(req.text, default_title=req.title or "Книга")
    chapters_dto = [
        ChapterDto(
            index=c.index,
            title=c.title,
            char_count=len(c.text),
            preview=c.text[:120] + "..." if len(c.text) > 120 else c.text,
        )
        for c in project.chapters
    ]
    return ParseBookResponse(
        id=project.id,
        title=req.title or "Книга",
        author=req.author or "Автор",
        chapter_count=len(project.chapters),
        chapters=chapters_dto,
    )


@router.post("/markup", response_model=MarkupResponse)
async def markup_text(req: MarkupRequest) -> MarkupResponse:
    """Разметить текст: автопунктуация под эмоции и паузы."""
    result = markup_emotions(req.text, intensity=req.intensity)
    return MarkupResponse(
        original=req.text,
        marked_up=result,
    )


@router.post("/synthesize-book", response_model=dict)
async def synthesize_book(
    req: BuildM4BRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Синтезировать книгу по главам и собрать M4B."""
    # 1. Check profile and valid samples
    stmt = select(VoiceProfile).where(VoiceProfile.id == req.profile_id)
    result = await db.execute(stmt)
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Голосовой профиль не найден")

    stmt2 = select(VoiceSample).where(
        VoiceSample.profile_id == req.profile_id,
        VoiceSample.is_valid == True,
    )
    result2 = await db.execute(stmt2)
    samples = result2.scalars().all()
    if not samples:
        raise HTTPException(status_code=422, detail="Нет валидных сэмплов в профиле")

    sample_tuples = [(s.audio_path, s.reference_text) for s in samples]

    # 2. Synthesize each chapter
    book_dir = settings.generations_dir / f"book_{uuid.uuid4().hex[:8]}"
    book_dir.mkdir(parents=True, exist_ok=True)
    
    chapter_objs: List[Chapter] = []
    total_dur = 0.0

    for i, ch_data in enumerate(req.chapters):
        title = ch_data.get("title", f"Глава {i+1}")
        text = ch_data.get("text", "")
        if not text.strip():
            continue
        gen_id = f"ch_{i+1:02d}_{uuid.uuid4().hex[:6]}"
        ch_path, dur = await synthesize_text(
            text=text,
            samples=sample_tuples,
            engine_id=req.engine,
            language=req.language,
            output_dir=book_dir,
            gen_id=gen_id,
        )
        total_dur += dur
        chapter_objs.append(Chapter(
            index=i+1,
            title=title,
            text=text,
            status="completed",
            audio_path=str(ch_path),
            duration_sec=dur,
        ))

    # 3. Assemble M4B
    m4b_output = book_dir / f"{req.book_title}.m4b"
    final_file = assemble_m4b(
        chapters=chapter_objs,
        output_path=m4b_output,
        book_title=req.book_title,
        author=req.author,
    )

    return {
        "status": "completed",
        "output_path": str(final_file),
        "total_duration_sec": round(total_dur, 2),
        "chapters_count": len(chapter_objs),
    }
