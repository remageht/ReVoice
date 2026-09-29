"""
Сервис режима «Книга» (Audiobook / Book Mode) для ReVoice.
- Парсинг Markdown / TXT на главы
- Чанкинг глав по абзацам с контролем длины
- Синтез очереди глав
- Экспорт глав в MP3 и сборка аудиокниги M4B с оглавлением
"""
from __future__ import annotations
import re
import os
import shutil
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Dict
import numpy as np
import soundfile as sf

from .tts import synthesize_text
from .chunker import split_text_ru
from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class Chapter:
    index: int
    title: str
    text: str
    status: str = "pending"  # pending, synthesizing, completed, failed
    audio_path: Optional[str] = None
    duration_sec: float = 0.0
    error: Optional[str] = None


@dataclass
class BookProject:
    id: str
    title: str
    author: str
    chapters: List[Chapter] = field(default_factory=list)


def parse_book_text(raw_text: str, default_title: str = "Книга") -> BookProject:
    """
    Распарсить сырой текст/Markdown на главы.
    Распознает:
    - # Заголовок
    - ## Глава X
    - Глава 1. Название
    - Часть 1 / Chapter 1
    """
    import uuid
    lines = raw_text.splitlines()
    chapters: List[Chapter] = []
    
    current_title = "Введение"
    current_lines: List[str] = []
    chapter_idx = 1

    chapter_pattern = re.compile(
        r'^(?:#{1,3}\s+(.+)|(?:глава|часть|пролог|эпилог|chapter)\s*(?:\d+)?[:.]?\s*(.*))$',
        re.IGNORECASE
    )

    for line in lines:
        match = chapter_pattern.match(line.strip())
        if match:
            # Save previous chapter if has content
            text_block = "\n".join(current_lines).strip()
            if text_block:
                chapters.append(Chapter(
                    index=chapter_idx,
                    title=current_title,
                    text=text_block,
                ))
                chapter_idx += 1
                current_lines = []

            # Extract new chapter title
            title_part = match.group(1) or line.strip()
            current_title = title_part.strip() or f"Глава {chapter_idx}"
        else:
            current_lines.append(line)

    # Add final chapter
    final_text = "\n".join(current_lines).strip()
    if final_text:
        chapters.append(Chapter(
            index=chapter_idx,
            title=current_title,
            text=final_text,
        ))

    if not chapters:
        chapters.append(Chapter(index=1, title="Глава 1", text=raw_text.strip()))

    return BookProject(
        id=str(uuid.uuid4()),
        title=default_title,
        author="Автор",
        chapters=chapters,
    )


def assemble_m4b(
    chapters: List[Chapter],
    output_path: Path,
    book_title: str = "Аудиокнига",
    author: str = "ReVoice",
) -> Path:
    """
    Собрать главы в единый файл M4B с метаданными оглавления.
    Если ffmpeg доступен — создаёт нативный M4B с главами (QuickTime/AAC).
    Если ffmpeg недоступен — собирает склеенный WAV/FLAC.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if ffmpeg is on system, with imageio_ffmpeg fallback
    ffmpeg_exe = shutil.which("ffmpeg")
    if not ffmpeg_exe:
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_exe = None
    
    # Calculate chapter timings
    valid_chapters = [c for c in chapters if c.audio_path and Path(c.audio_path).exists()]
    if not valid_chapters:
        raise ValueError("Нет готовых глав с аудио для сборки M4B")

    if ffmpeg_exe:
        logger.info("Using ffmpeg to build M4B with chapters metadata")
        # Build ffmetadata file
        meta_lines = [";FFMETADATA1", f"title={book_title}", f"artist={author}"]
        concat_list = []
        current_time_ms = 0

        for ch in valid_chapters:
            dur_ms = int(ch.duration_sec * 1000)
            meta_lines.append("[CHAPTER]")
            meta_lines.append("TIMEBASE=1/1000")
            meta_lines.append(f"START={current_time_ms}")
            meta_lines.append(f"END={current_time_ms + dur_ms}")
            meta_lines.append(f"title={ch.title}")
            current_time_ms += dur_ms

            # For ffmpeg concat
            ch_path_esc = str(Path(ch.audio_path).resolve()).replace("\\", "/")
            concat_list.append(f"file '{ch_path_esc}'")

        meta_file = output_path.parent / "metadata.txt"
        concat_file = output_path.parent / "concat.txt"
        meta_file.write_text("\n".join(meta_lines), encoding="utf-8")
        concat_file.write_text("\n".join(concat_list), encoding="utf-8")

        # Run ffmpeg command
        import subprocess
        cmd = [
            ffmpeg_exe, "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", str(meta_file),
            "-map_metadata", "1",
            "-c:a", "aac", "-b:a", "128k",
            str(output_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            logger.info("M4B generated successfully: %s", output_path)
            return output_path
        else:
            logger.warning("ffmpeg failed: %s, falling back to audio concatenation", res.stderr)

    # Fallback: concatenate all wav files directly
    logger.info("Falling back to pure audio concatenation")
    all_data = []
    sr = 24000
    for ch in valid_chapters:
        data, file_sr = sf.read(ch.audio_path, dtype="float32")
        sr = file_sr
        all_data.append(data)
    
    combined = np.concatenate(all_data) if len(all_data) > 1 else all_data[0]
    wav_out = output_path.with_suffix(".wav")
    sf.write(str(wav_out), combined, sr, subtype="PCM_16")
    logger.info("Audiobook saved as WAV: %s", wav_out)
    return wav_out
