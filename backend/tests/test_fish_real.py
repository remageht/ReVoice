"""
Интеграционные и статические тесты для Fish Speech 1.5.

1. test_fish_api_signatures: статический тест inspect-ом сигнатур Fish Speech.
   Проверяет наличие TTSInferenceEngine, ServeTTSRequest, ServeReferenceAudio,
   launch_thread_safe_queue и load_model без вызова весов.
2. test_fish_real_synthesis: интеграционный тест на РЕАЛЬНЫХ весах.
   Запускается только если задана переменная окружения:
   REVOICE_TEST_FISH=<путь к чекпоинтам fish-speech-1.5>
"""
import os
import sys
import inspect
import pytest
import numpy as np


def _ensure_fish_in_path():
    for p in ["C:/dev/fish-speech", "C:\\dev\\fish-speech"]:
        if os.path.exists(p) and p not in sys.path:
            sys.path.insert(0, p)


def test_fish_api_signatures():
    """
    Статическая проверка API fish-speech:
    Гарантирует наличие TTSInferenceEngine, ServeTTSRequest, ServeReferenceAudio
    и фабрик моделей в реальном пакете fish-speech.
    """
    _ensure_fish_in_path()

    try:
        from fish_speech.inference_engine import TTSInferenceEngine
        from fish_speech.utils.schema import ServeTTSRequest, ServeReferenceAudio
        from fish_speech.models.text2semantic.inference import launch_thread_safe_queue
        from fish_speech.models.vqgan.inference import load_model as load_decoder_model
        from fish_speech.text import clean_text, split_text
    except ImportError as e:
        pytest.skip(f"fish-speech не установлен или недоступен: {e}")

    # 1. Проверяем TTSInferenceEngine и его методы
    assert hasattr(TTSInferenceEngine, "inference"), "TTSInferenceEngine обязан иметь метод inference"
    sig_inf = inspect.signature(TTSInferenceEngine.inference)
    assert "req" in sig_inf.parameters, f"inference должен принимать 'req': {list(sig_inf.parameters.keys())}"

    # 2. Проверяем ServeTTSRequest и ключевые поля
    assert hasattr(ServeTTSRequest, "model_fields") or hasattr(ServeTTSRequest, "__fields__"), (
        "ServeTTSRequest обязан быть pydantic-моделью"
    )
    fields = getattr(ServeTTSRequest, "model_fields", getattr(ServeTTSRequest, "__fields__", {}))
    assert "text" in fields, "ServeTTSRequest обязан содержать поле 'text'"
    assert "references" in fields, "ServeTTSRequest обязан содержать поле 'references'"
    assert "chunk_length" in fields, "ServeTTSRequest обязан содержать поле 'chunk_length'"
    assert "max_new_tokens" in fields, "ServeTTSRequest обязан содержать поле 'max_new_tokens'"

    # 3. Проверяем ServeReferenceAudio
    ref_fields = getattr(ServeReferenceAudio, "model_fields", getattr(ServeReferenceAudio, "__fields__", {}))
    assert "audio" in ref_fields, "ServeReferenceAudio обязан содержать поле 'audio'"
    assert "text" in ref_fields, "ServeReferenceAudio обязан содержать поле 'text'"

    # 4. Проверяем фабричные функции загрузки
    assert callable(launch_thread_safe_queue), "launch_thread_safe_queue обязана быть вызываемой"
    assert callable(load_decoder_model), "load_decoder_model обязана быть вызываемой"
    assert callable(clean_text), "clean_text обязана быть вызываемой"
    assert callable(split_text), "split_text обязана быть вызываемой"


@pytest.mark.asyncio
async def test_fish_real_synthesis(tmp_path):
    """
    Интеграционный тест синтеза речи на РЕАЛЬНЫХ весах Fish Speech 1.5.
    Активируется при наличии переменной окружения REVOICE_TEST_FISH.
    """
    model_path = os.environ.get("REVOICE_TEST_FISH")
    if not model_path:
        pytest.skip("REVOICE_TEST_FISH не задана. Укажите путь к чекпоинтам для GPU-прогона.")

    if not os.path.exists(model_path):
        pytest.skip(f"Путь к весам из REVOICE_TEST_FISH не существует: {model_path}")

    from revoice.backends.fish_engine import FishTTSEngine

    engine = FishTTSEngine()
    # Загружаем модель Fish Speech на GPU
    await engine.load(model_path=model_path, device="cuda")
    assert engine.is_loaded(), "FishTTSEngine должен быть в статусе is_loaded=True"

    # Подбираем эталонный сэмпл голоса
    candidates = [
        ("C:\\dev\\voices\\egorka_adult.wav", "C:\\dev\\voices\\egorka_adult.txt"),
        ("C:\\dev\\voices\\voice_ru_1.wav", "C:\\dev\\voices\\voice_ru_1.txt"),
    ]
    ref_audio, ref_sr, ref_text = None, 44100, ""
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
        ref_sr = 44100
        t = np.linspace(0, 5.0, int(ref_sr * 5.0), dtype=np.float32)
        ref_audio = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        ref_text = "Это эталонная запись голоса для клонирования."

    # Тестовый текст ровно ~100 символов на русском языке
    test_text = "Привет! Это проверка синтеза речи студии ReVoice на модели Fish Speech. Звучит чисто и живо."
    chars = len(test_text)
    assert 85 <= chars <= 115, f"Длина текста должна быть ~100 символов, текущая: {chars}"

    # Синтезируем
    audio_out, sr = await engine.synthesize(
        text=test_text,
        ref_audio=ref_audio,
        ref_sr=ref_sr,
        ref_text=ref_text,
        language="ru",
        seed=1,
    )

    assert isinstance(audio_out, np.ndarray), "Синтез должен вернуть numpy ndarray"
    assert len(audio_out) > 0, "Синтезированное аудио не должно быть пустым"
    assert sr == 44100, f"Частота дискретизации Fish Speech должна быть 44100 Гц, получено: {sr}"

    duration = len(audio_out) / sr
    expected_duration = chars / 12.0  # ~12 символов в секунду
    min_duration = expected_duration * 0.50
    max_duration = expected_duration * 1.50

    # Проверка длительности: символы / 12 ± 50%
    assert min_duration <= duration <= max_duration, (
        f"Длительность {duration:.2f}с не уложилась в диапазон {min_duration:.2f}с - {max_duration:.2f}с "
        f"(ожидалось ~{expected_duration:.2f}с)"
    )

    # Проверка RMS > 0.01 (не тишина)
    rms = float(np.sqrt(np.mean(audio_out ** 2)))
    assert rms > 0.01, f"RMS {rms:.4f} слишком низкий (тишина или ошибка генерации)"

    # Выгрузка модели
    await engine.unload()
    assert not engine.is_loaded(), "Модель Fish Speech должна быть полностью выгружена"
