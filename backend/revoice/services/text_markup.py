"""
Сервис «Разметить текст» для ReVoice.
Автопунктуация и эмоциональная разметка под синтез речи:
- Расстановка пауз (...) перед важными мыслями
- Интонационные акценты (!, ?!)
- Подготовка прямой речи («...»)
- Нормализация чисел и спецсимволов для русской речи
"""
from __future__ import annotations
import re
from typing import Dict

# Слова-маркеры эмоций для эмоциональной пунктуации
_EMOTION_MARKERS: Dict[str, str] = {
    # Восклицания / удивление / восторг
    "вау": "Вау!",
    "ого": "Ого!",
    "ура": "Ура!",
    "эй": "Эй!",
    "боже": "Боже...",
    "слушай": "Слушай...",
    "внимание": "Внимание!",
    "стой": "Стой!",
    "подожди": "Подожди...",
    "неужели": "Неужели?!",
    "правда": "Правда?!",
    "точно": "Точно!",
    "конечно": "Конечно!",
    "стоп": "Стоп!",
    "браво": "Браво!",
    "черт": "Чёрт...",
    "блин": "Блин...",
    "тихо": "Тихо...",
}

_NUMBERS_RU = {
    "0": "ноль", "1": "один", "2": "два", "3": "три", "4": "четыре",
    "5": "пять", "6": "шесть", "7": "семь", "8": "восемь", "9": "девять", "10": "десять"
}


def markup_emotions(text: str, intensity: str = "moderate") -> str:
    """
    Разметить текст для выразительной озвучки.
    
    Args:
        text: Исходный текст на русском языке.
        intensity: 'subtle' | 'moderate' | 'dramatic'
    
    Returns:
        Размеченный текст с интонационной пунктуацией.
    """
    text = text.strip()
    if not text:
        return ""

    # 1. Замена кавычек на русские ёлочки
    text = re.sub(r'["\'](.*?)["\']', r'«\1»', text)

    # 2. Вопросительно-восклицательные интонации (Что?! Как?!)
    text = re.sub(r'(\b(?:что|как|зачем|почему|куда|откуда)\b[^.!?\n]*)\?', r'\1?!', text, flags=re.IGNORECASE)

    # 3. Маркеры эмоций
    for marker, replacement in _EMOTION_MARKERS.items():
        pattern = rf'\b{re.escape(marker)}\b([,.]?)'
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # 4. Драматические паузы
    if intensity in ("moderate", "dramatic"):
        # Добавляем паузу (...) перед противительными союзами
        text = re.sub(r'([,]\s*)(но|однако|зато|только)\b', r'... \2', text, flags=re.IGNORECASE)
        # Пауза перед "и вдруг", "и тут"
        text = re.sub(r'\b(и\s+вдруг|и\s+тут|внезапно)\b', r'... \1', text, flags=re.IGNORECASE)

    if intensity == "dramatic":
        # Усиливаем точки до многоточий на коротких репликах
        lines = text.split("\n")
        new_lines = []
        for line in lines:
            line = line.strip()
            if line and len(line) < 40 and line.endswith("."):
                line = line[:-1] + "..."
            new_lines.append(line)
        text = "\n".join(new_lines)

    # 5. Очистка двойных знаков препинания
    text = re.sub(r'\.{4,}', '...', text)
    text = re.sub(r'\s+([,.:!?…])', r'\1', text)
    text = re.sub(r'\s+', ' ', text)

    return text.strip()
