import sys
import os
import requests
import json
import soundfile as sf
import re
from pathlib import Path

BASE_URL = "http://127.0.0.1:7851"

def normalize_text(t: str) -> str:
    t = t.lower().replace("ё", "е")
    return re.sub(r"[^\w\s]", "", t).strip()

def main():
    print("=== ReVoice E2E Test (Punkt 3) ===")
    
    # 1. Health check
    r = requests.get(f"{BASE_URL}/api/health")
    assert r.status_code == 200, f"Health check failed: {r.text}"
    health = r.json()
    print(f"1. Health OK: version={health['version']}, gpu={health['gpu']['available']}, loaded={health['loaded_engines']}")
    assert health["version"] == "0.1.5", f"Expected version 0.1.5, got {health['version']}"
    
    # 2. Check qwen model is loaded
    r = requests.get(f"{BASE_URL}/api/models")
    models = r.json()
    qwen = next((m for m in models if m["id"] == "qwen-tts-0.6b"), None)
    assert qwen is not None, "qwen-tts-0.6b not found in catalogue"
    print(f"2. Model qwen-tts-0.6b is_loaded={qwen['is_loaded']}")
    if not qwen["is_loaded"]:
        print("Loading qwen-tts-0.6b...")
        r_load = requests.post(f"{BASE_URL}/api/models/qwen-tts-0.6b/load", json={"device": "cuda"})
        assert r_load.status_code == 200, f"Load failed: {r_load.text}"
        print("Model loaded successfully.")

    # 3. Get or Create profile
    r = requests.get(f"{BASE_URL}/api/profiles")
    profiles = r.json()
    profile = next((p for p in profiles if p["name"] == "Егорка Автотест" and len(p.get("samples", [])) > 0), None)
    
    if profile:
        profile_id = profile["id"]
        print(f"3. Using existing profile ID: {profile_id} with {len(profile.get('samples', []))} sample(s)")
    else:
        profile_data = {
            "name": "Егорка Автотест",
            "description": "Сквозной тест 0.1.5",
            "language": "ru",
            "default_engine": "qwen"
        }
        r = requests.post(f"{BASE_URL}/api/profiles", json=profile_data)
        assert r.status_code in (200, 201), f"Create profile failed: {r.text}"
        profile = r.json()
        profile_id = profile["id"]
        print(f"3. Created profile ID: {profile_id}")

        # 4. Upload sample egorka_adult.wav + transcript
        sample_wav = Path(r"C:\dev\voices\egorka_adult.wav")
        sample_txt_path = Path(r"C:\dev\voices\egorka_adult.txt")
        ref_text = sample_txt_path.read_text(encoding="utf-8").strip()
        
        with open(sample_wav, "rb") as f:
            files = {"audio": (sample_wav.name, f, "audio/wav")}
            data = {"reference_text": ref_text}
            r = requests.post(f"{BASE_URL}/api/profiles/{profile_id}/samples", files=files, data=data)
        assert r.status_code in (200, 201), f"Add sample failed: {r.text}"
        sample_res = r.json()
        print(f"4. Sample uploaded: duration={sample_res.get('duration_sec')}s, is_valid={sample_res.get('is_valid')}")
        assert sample_res.get("is_valid") == True, f"Sample invalid: {sample_res.get('rejection_reason')}"

    # 5. Synthesize ~100 characters Russian text
    synth_text = "Сегодня отличная погода, светит яркое солнце и дует легкий ветерок. Мы идем гулять в наш старый парк."
    char_count = len(synth_text)
    print(f"5. Synthesizing text ({char_count} chars): '{synth_text}'")
    
    synth_payload = {
        "profile_id": profile_id,
        "text": synth_text,
        "engine": "qwen",
        "language": "ru"
    }
    r = requests.post(f"{BASE_URL}/api/synthesize", json=synth_payload)
    assert r.status_code in (200, 201), f"Synthesis failed: {r.text}"
    synth_res = r.json()
    print(f"Synthesis response: {json.dumps(synth_res, ensure_ascii=False)}")
    
    out_audio_path = synth_res.get("audio_path")
    assert out_audio_path and os.path.exists(out_audio_path), f"Audio file not found: {out_audio_path}"
    
    # 6. Check duration = chars / 12 +/- 50%
    data, sr = sf.read(out_audio_path)
    actual_duration = len(data) / sr
    expected_duration = char_count / 12.0
    min_allowed = expected_duration * 0.5
    max_allowed = expected_duration * 1.5
    print(f"6. Duration check: actual={actual_duration:.2f}s, expected={expected_duration:.2f}s (allowed: [{min_allowed:.2f}s .. {max_allowed:.2f}s])")
    assert min_allowed <= actual_duration <= max_allowed, (
        f"Duration {actual_duration:.2f}s outside bounds [{min_allowed:.2f}s .. {max_allowed:.2f}s]!"
    )
    print("Duration check PASSED!")

    # 7. Transcribe output using faster-whisper on CPU
    print("7. Transcribing output audio using faster-whisper...")
    from faster_whisper import WhisperModel
    whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = whisper_model.transcribe(out_audio_path, language="ru")
    transcribed_text = " ".join(seg.text for seg in segments).strip()
    print(f"Transcribed output: '{transcribed_text}'")
    
    norm_input = normalize_text(synth_text)
    norm_output = normalize_text(transcribed_text)
    print(f"Normalized input:  '{norm_input}'")
    print(f"Normalized output: '{norm_output}'")
    
    # Calculate word overlap
    in_words = set(norm_input.split())
    out_words = set(norm_output.split())
    overlap = in_words.intersection(out_words)
    overlap_ratio = len(overlap) / len(in_words)
    print(f"Word overlap: {len(overlap)}/{len(in_words)} ({overlap_ratio*100:.1f}%) -> {overlap}")
    assert overlap_ratio >= 0.70, f"Transcription match too low: {overlap_ratio*100:.1f}%"
    print("Transcription match PASSED!")
    
    # Cleanup test profile
    requests.delete(f"{BASE_URL}/api/profiles/{profile_id}")
    print("Cleanup: test profile deleted.")
    print("=== PUNKT 3 COMPLETED SUCCESSFULLY ===")

if __name__ == "__main__":
    main()
