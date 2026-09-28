"""
Русский текстовый чанкер.
Не рвёт по «т.д.», «т.е.», инициалам, числам с точкой.
"""
from __future__ import annotations
import re
from typing import List

# Abbreviations that should NOT be split at the period
_RU_ABBREVS = frozenset([
    "т.д", "т.е", "т.п", "т.к", "напр", "см", "ср", "ст", "пр",
    "ул", "пл", "пр-т", "д", "кв", "обл", "р-н",
    "янв", "февр", "апр", "авг", "сент", "окт", "нояб", "дек",
    "млн", "млрд", "тыс", "руб", "коп", "кг", "км", "мм", "см", "л",
    "рис", "табл", "стр", "гл", "ч",
])

# Pattern: sentence-ending punctuation followed by whitespace + capital or digit
_SENTENCE_END = re.compile(
    r'(?<![А-ЯA-Z]\.[А-ЯA-Z])'   # not initials like А.С.
    r'(?<!\b(?:' + '|'.join(re.escape(a) for a in _RU_ABBREVS) + r'))'
    r'([.!?…]{1,3}["»\)]?)'       # punctuation
    r'(?=\s+[А-ЯA-Z\d"«\(])'     # followed by capital/digit/quote
)


def split_text_ru(text: str, max_chars: int = 200) -> List[str]:
    """
    Разбить текст на предложения для синтеза.

    Правила:
    - Не разрывать аббревиатуры (т.д., т.е., инициалы)
    - Максимум max_chars символов на чанк
    - Если предложение длиннее max_chars — разбить по запятым/тире
    """
    text = text.strip()
    if not text:
        return []

    # First pass: split by sentence boundaries
    sentences = _split_sentences(text)

    # Second pass: merge short sentences and split long ones
    chunks: List[str] = []
    current = ""

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        if len(sent) > max_chars:
            # Save current buffer
            if current:
                chunks.append(current.strip())
                current = ""
            # Split long sentence by comma/dash
            sub = _split_by_comma(sent, max_chars)
            chunks.extend(sub)
        elif len(current) + len(sent) + 1 <= max_chars:
            current = (current + " " + sent).strip()
        else:
            if current:
                chunks.append(current.strip())
            current = sent

    if current:
        chunks.append(current.strip())

    return [c for c in chunks if c]


def _split_sentences(text: str) -> List[str]:
    """Split text at sentence boundaries."""
    parts = _SENTENCE_END.split(text)
    # _SENTENCE_END has 1 capturing group, so split interleaves text and matched punct
    sentences = []
    i = 0
    while i < len(parts):
        chunk = parts[i]
        if i + 1 < len(parts):
            chunk += parts[i + 1]  # append the punctuation
            i += 2
        else:
            i += 1
        if chunk.strip():
            sentences.append(chunk)
    return sentences


def _split_by_comma(text: str, max_chars: int) -> List[str]:
    """Split long sentence by commas/semicolons."""
    parts = re.split(r'[,;]\s*', text)
    chunks: List[str] = []
    current = ""
    for part in parts:
        if len(current) + len(part) + 2 <= max_chars:
            current = (current + ", " + part).strip(", ")
        else:
            if current:
                chunks.append(current)
            if len(part) > max_chars:
                # Hard split at max_chars
                while len(part) > max_chars:
                    chunks.append(part[:max_chars])
                    part = part[max_chars:]
            current = part
    if current:
        chunks.append(current)
    return chunks
