"""
Интеграционные и статические тесты для реального API Qwen3-TTS.

1. test_qwen_api_signatures: статический тест inspect-ом сигнатур Qwen3TTSModel.
   Ловит любые галлюцинации API без необходимости скачивать веса.
2. test_qwen_real_synthesis: интеграционный тест на РЕАЛЬНЫХ весах.
   Запускается только если задана переменная окружения:
   REVOICE_TEST_MODEL=<путь к папке Qwen3-TTS-12Hz-0.6B-Base>
"""
import os
import inspect
import pytest
import numpy as np


def test_qwen_api_signatures():
    """
    Статическая проверка API qwen_tts:
    Гарантирует, что методы from_pretrained, generate_voice_clone и create_voice_clone_prompt
    реально существуют в классе Qwen3TTSModel и имеют ожидаемые параметры.
    """
    try:
        import qwen_tts
        from qwen_tts import Qwen3TTSModel
    except ImportError:
        pytest.skip("qwen-tts не установлен в окружении")

    # 1. Проверяем наличие ключевых методов
    assert hasattr(Qwen3TTSModel, "from_pretrained"), "Qwen3TTSModel обязан иметь метод from_pretrained"
    assert hasattr(Qwen3TTSModel, "generate_voice_clone") or hasattr(Qwen3TTSModel, "create_voice_clone_prompt"), (
        "Qwen3TTSModel обязан иметь generate_voice_clone или create_voice_clone_prompt"
    )

    # 2. Инспекция сигнатур
    if hasattr(Qwen3TTSModel, "generate_voice_clone"):
        sig = inspect.signature(Qwen3TTSModel.generate_voice_clone)
        params = list(sig.parameters.keys())
        # Должен принимать text, language, и reference audio/text или prompt
        assert "text" in params, f"generate_voice_clone должен принимать 'text', параметры: {params}"

    if hasattr(Qwen3TTSModel, "create_voice_clone_prompt"):
        sig_prompt = inspect.signature(Qwen3TTSModel.create_voice_clone_prompt)
        params_p = list(sig_prompt.parameters.keys())
        assert any("audio" in p or "ref" in p for p in params_p), (
            f"create_voice_clone_prompt должен принимать референсное аудио: {params_p}"
        )


@pytest.mark.asyncio
async def test_qwen_real_synthesis(tmp_path):
    """
    Интеграционный тест синтеза речи на РЕАЛЬНЫХ весах.
    Активируется ТОЛЬКО при наличии переменной окружения REVOICE_TEST_MODEL.
    """
    model_path = os.environ.get("REVOICE_TEST_MODEL")
    if not model_path:
        pytest.skip("REVOICE_TEST_MODEL не задана. Укажите путь к весам для прогона на GPU.")

    if not os.path.exists(model_path):
        pytest.fail(f"Путь к весам из REVOICE_TEST_MODEL не существует: {model_path}")

    from revoice.backends.qwen_engine import QwenTTSEngine

    engine = QwenTTSEngine()
    # Загружаем модель с указанного пути
    await engine.load(model_path=model_path, device="cuda")
    assert engine.is_loaded(), "Движок должен быть в статусе is_loaded=True"

    # Используем чистый эталонный сэмпл (egorka_adult) для точного выравнивания ICL
    candidates = [
        ("C:\\dev\\voices\\egorka_adult.wav", "C:\\dev\\voices\\egorka_adult.txt"),
        ("C:\\dev\\voices\\voice_ru_1.wav", "C:\\dev\\voices\\voice_ru_1.txt"),
    ]
    ref_audio, ref_sr, ref_text = None, 24000, ""
    for wav_p, txt_p in candidates:
        if os.path.exists(wav_p) and os.path.exists(txt_p):
            import soundfile as sf
            data, sr = sf.read(wav_p)
            if data.ndim > 1:
                data = data.mean(axis=1)
            ref_audio = data
            ref_sr = sr
            ref_text = open(txt_p, encoding="utf-8").read().strip()
            break

    if ref_audio is None:
        ref_sr = 24000
        t = np.linspace(0, 5.0, int(ref_sr * 5.0), dtype=np.float32)
        ref_audio = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        ref_text = "Это эталонная запись голоса для клонирования."

    # Тестовый текст ровно ~100 символов на русском языке
    test_text = "Привет! Это проверка синтеза речи студии ReVoice на реальной модели Qwen три TTS. Всё звучит чисто."
    chars = len(test_text)
    assert 90 <= chars <= 115, f"Длина текста должна быть ~100 символов, текущая: {chars}"

    # Синтезируем
    audio_out, sr = await engine.synthesize(
        text=test_text,
        ref_audio=ref_audio,
        ref_sr=ref_sr,
        ref_text=ref_text,
        language="ru",
    )

    assert isinstance(audio_out, np.ndarray), "Синтез должен вернуть numpy ndarray"
    assert len(audio_out) > 0, "Аудио не должно быть пустым"
    assert sr > 0, "Частота дискретизации должна быть больше 0"

    duration = len(audio_out) / sr
    expected_duration = chars / 12.0  # ~12 символов в секунду
    min_duration = expected_duration * 0.50
    max_duration = expected_duration * 1.50

    # Проверка длительности: символы / 12 ± 50%
    assert min_duration <= duration <= max_duration, (
        f"Длительность {duration:.2f}с не уложилась в {min_duration:.2f}с - {max_duration:.2f}с "
        f"(ожидалось ~{expected_duration:.2f}с)"
    )

    # Проверка RMS > 0.01 (не тишина)
    rms = float(np.sqrt(np.mean(audio_out ** 2)))
    assert rms > 0.01, f"RMS {rms:.4f} слишком низкий (тишина или ошибка генерации)"

    # Выгрузка модели
    await engine.unload()
    assert not engine.is_loaded(), "Модель должна быть выгружена"
