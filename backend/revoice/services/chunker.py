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

# Candidate sentence boundary: punctuation followed by space and capital/digit/quote
_CANDIDATE_PUNCT = re.compile(r'([.!?…]{1,3}["»\)]?)(\s+(?=[А-ЯA-Z\d"«\(])|$)')


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


def _is_abbrev_or_initial(prefix: str) -> bool:
    """Check if the text immediately preceding the dot is an abbreviation or initial."""
    prefix = prefix.rstrip()
    if re.search(r'\b[А-ЯA-Z]\.[А-ЯA-Z]$', prefix) or re.search(r'\b[А-ЯA-Z]$', prefix):
        return True
    words = prefix.split()
    if words:
        last_word = words[-1].lower().lstrip("«\"'([")
        if last_word in _RU_ABBREVS:
            return True
    return False


def _split_sentences(text: str) -> List[str]:
    """Split text at sentence boundaries."""
    sentences = []
    start = 0
    for match in _CANDIDATE_PUNCT.finditer(text):
        punct = match.group(1)
        end_idx = match.start() + len(punct)
        prefix = text[start:match.start()]
        if punct.startswith('.') and _is_abbrev_or_initial(prefix):
            continue
        sent = text[start:end_idx].strip()
        if sent:
            sentences.append(sent)
        start = match.end()
    remaining = text[start:].strip()
    if remaining:
        sentences.append(remaining)
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
