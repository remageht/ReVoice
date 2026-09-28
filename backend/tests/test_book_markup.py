import pytest
from pathlib import Path
from revoice.services.book import parse_book_text, Chapter
from revoice.services.text_markup import markup_emotions


def test_parse_markdown_chapters():
    text = """
# Моя первая книга

Это введение в историю.

## Глава 1. Начало приключения
Герой вышел из дома ранним утром. Туман стелился над дорогой.

## Глава 2: Встреча в лесу
В чаще леса послышался шорох.
    """.strip()

    book = parse_book_text(text, default_title="Моя первая книга")
    assert book.title == "Моя первая книга"
    assert len(book.chapters) == 3
    assert "Введение" in book.chapters[0].title or "первая книга" in book.chapters[0].title
    assert "Глава 1" in book.chapters[1].title
    assert "Глава 2" in book.chapters[2].title
    assert "Герой вышел" in book.chapters[1].text


def test_parse_plain_russian_chapters():
    text = """
Глава 1. Пробуждение
Солнце взошло над горизонтом.

Глава 2. Путь на восток
Дорога была долгой и трудной.
    """.strip()

    book = parse_book_text(text)
    assert len(book.chapters) == 2
    assert book.chapters[0].title == "Глава 1. Пробуждение"
    assert book.chapters[1].title == "Глава 2. Путь на восток"


def test_text_markup_emotions():
    text = "вау это просто супер! что ты делаешь?"
    result = markup_emotions(text, intensity="moderate")
    assert "Вау!" in result
    assert "?!" in result


def test_text_markup_pauses():
    text = "Я хотел пойти, но начался сильный дождь."
    result = markup_emotions(text, intensity="moderate")
    assert "... но" in result
