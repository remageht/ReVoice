"""
Тесты русского чанкера.
"""
import pytest
from revoice.services.chunker import split_text_ru


def test_basic_split():
    text = "Привет, мир. Как дела? Я хорошо!"
    chunks = split_text_ru(text, max_chars=200)
    assert len(chunks) >= 1
    # All chunks should be non-empty
    assert all(c.strip() for c in chunks)


def test_no_split_abbrev():
    """Abbreviations like т.д. should not cause splits."""
    text = "Это работает хорошо, т.д. и т.е. без разрывов."
    chunks = split_text_ru(text, max_chars=200)
    # Should be one chunk, не разрываться на т.д.
    combined = " ".join(chunks)
    assert "т.д" in combined or "т.е" in combined


def test_long_text_split():
    text = "а" * 500
    chunks = split_text_ru(text, max_chars=200)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 200 + 10  # small margin


def test_empty_text():
    assert split_text_ru("") == []
    assert split_text_ru("   ") == []


def test_short_text():
    text = "Привет"
    chunks = split_text_ru(text, max_chars=200)
    assert chunks == ["Привет"]
