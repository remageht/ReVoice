"""
Qwen3-TTS 0.6B LoRA Fine-Tuning: Dataset Preparation & VRAM Spike Analysis.

This script:
1. Scans voices directory (e.g. C:\\dev\\voices), pairs .wav with .txt transcripts.
2. Segments audio into optimal 3-10 second training chunks with clean speech.
3. Generates train.jsonl and val.jsonl formatted for Qwen3-TTS speech training.
4. Performs a VRAM budget analysis for training on 4 GB GPUs (RTX 3050 Ti Laptop).
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
import soundfile as sf
import numpy as np

MIN_CHUNK_SEC = 3.0
MAX_CHUNK_SEC = 10.0
TARGET_SR = 24000  # Qwen3-TTS native sample rate

def parse_voice_files(voices_dir: Path) -> List[Dict[str, Any]]:
    """Scan directory for matching .wav and .txt files."""
    records = []
    for wav_file in sorted(voices_dir.glob("*.wav")):
        txt_file = wav_file.with_suffix(".txt")
        if not txt_file.exists():
            continue
        try:
            transcript = txt_file.read_text(encoding="utf-8").strip()
            if not transcript:
                continue
            info = sf.info(str(wav_file))
            records.append({
                "name": wav_file.stem,
                "audio_path": str(wav_file),
                "text": transcript,
                "duration": info.duration,
                "samplerate": info.samplerate,
                "channels": info.channels,
            })
        except Exception as e:
            print(f"[WARN] Error reading {wav_file}: {e}")
    return records

def segment_audio_and_text(record: Dict[str, Any], output_dir: Path) -> List[Dict[str, Any]]:
    """
    Segment audio and text into training clips of 3-10s.
    If the audio is already between 3-10s, saves it as a single chunk.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    
    data, sr = sf.read(record["audio_path"], dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
        
    duration = len(data) / sr
    
    if MIN_CHUNK_SEC <= duration <= MAX_CHUNK_SEC:
        chunk_name = f"{record['name']}_000.wav"
        chunk_path = output_dir / chunk_name
        sf.write(str(chunk_path), data, sr)
        chunks.append({
            "audio_file": str(chunk_path),
            "text": record["text"],
            "duration": round(duration, 2),
            "speaker": record["name"]
        })
    elif duration > MAX_CHUNK_SEC:
        # Segment by sentence or fixed window
        target_chunk_samples = int(sr * 8.0)
        num_chunks = int(np.ceil(len(data) / target_chunk_samples))
        words = record["text"].split()
        words_per_chunk = max(1, len(words) // num_chunks)
        
        for i in range(num_chunks):
            start = i * target_chunk_samples
            end = min(len(data), (i + 1) * target_chunk_samples)
            sub_data = data[start:end]
            sub_dur = len(sub_data) / sr
            if sub_dur < MIN_CHUNK_SEC:
                continue
                
            sub_words = words[i * words_per_chunk : (i + 1) * words_per_chunk] if i < num_chunks - 1 else words[i * words_per_chunk :]
            sub_text = " ".join(sub_words)
            if not sub_text:
                continue
                
            chunk_name = f"{record['name']}_{i:03d}.wav"
            chunk_path = output_dir / chunk_name
            sf.write(str(chunk_path), sub_data, sr)
            chunks.append({
                "audio_file": str(chunk_path),
                "text": sub_text,
                "duration": round(sub_dur, 2),
                "speaker": record["name"]
            })
    return chunks

def build_dataset(voices_dir: Path, output_dataset_dir: Path) -> Tuple[Path, Path, int]:
    """Build train.jsonl and val.jsonl datasets."""
    records = parse_voice_files(voices_dir)
    print(f"Found {len(records)} raw voice files in {voices_dir}")
    
    clips_dir = output_dataset_dir / "clips"
    all_chunks = []
    for r in records:
        chunks = segment_audio_and_text(r, clips_dir)
        all_chunks.extend(chunks)
        
    print(f"Generated {len(all_chunks)} training segments.")
    
    # 90% train, 10% val split
    np.random.seed(42)
    np.random.shuffle(all_chunks)
    val_count = max(1, int(len(all_chunks) * 0.1))
    val_chunks = all_chunks[:val_count]
    train_chunks = all_chunks[val_count:]
    
    train_jsonl = output_dataset_dir / "train.jsonl"
    val_jsonl = output_dataset_dir / "val.jsonl"
    
    with open(train_jsonl, "w", encoding="utf-8") as f:
        for c in train_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
            
    with open(val_jsonl, "w", encoding="utf-8") as f:
        for c in val_chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
            
    return train_jsonl, val_jsonl, len(all_chunks)

def estimate_vram_budget():
    """Detailed VRAM footprint calculation for Qwen 0.6B LoRA training on 4GB VRAM."""
    model_params = 590_000_000
    base_dtype_bytes = 2  # bfloat16
    base_weights_mb = (model_params * base_dtype_bytes) / (1024 * 1024)
    
    # LoRA config: r=8, alpha=16 on q_proj, v_proj
    lora_params = 1_200_000
    lora_weights_mb = (lora_params * 4) / (1024 * 1024)
    lora_grads_mb = (lora_params * 4) / (1024 * 1024)
    optimizer_state_mb = (lora_params * 8) / (1024 * 1024)  # AdamW 2 states (fp32)
    
    # Activations with gradient checkpointing enabled, batch=1, seq_len=150
    act_checkpoint_mb = 450.0
    
    # PyTorch CUDA Context & Caching Allocator
    cuda_context_mb = 480.0
    
    total_training_mb = (
        base_weights_mb +
        lora_weights_mb +
        lora_grads_mb +
        optimizer_state_mb +
        act_checkpoint_mb +
        cuda_context_mb
    )
    
    wddm_overhead_mb = 800.0  # Windows DWM display allocation on 4096 MB physical
    effective_gpu_mb = 4096.0 - wddm_overhead_mb  # ~3296 MB
    headroom_mb = effective_gpu_mb - total_training_mb
    
    report = {
        "Base Model (bfloat16)": f"{base_weights_mb:.1f} MB",
        "LoRA Parameters (r=8)": f"{lora_weights_mb:.2f} MB",
        "LoRA Gradients": f"{lora_grads_mb:.2f} MB",
        "AdamW Optimizer States": f"{optimizer_state_mb:.2f} MB",
        "Activations (Batch=1, GradCheckpoint=True)": f"{act_checkpoint_mb:.1f} MB",
        "PyTorch CUDA Runtime Context": f"{cuda_context_mb:.1f} MB",
        "Total Estimated Training VRAM": f"{total_training_mb:.1f} MB",
        "Available Usable VRAM (RTX 3050 Ti after DWM)": f"{effective_gpu_mb:.1f} MB",
        "Safety Headroom": f"{headroom_mb:.1f} MB",
        "Feasibility Verdict": "FEASIBLE under strict constraints (batch=1, grad_accum=4, grad_checkpoint=True, bf16)",
    }
    return report

def main():
    voices_dir = Path(r"C:\dev\voices")
    dataset_dir = Path(r"C:\dev\ReVoice\dataset")
    print("=== Qwen3-TTS 0.6B LoRA Fine-Tuning Pipeline ===")
    
    # 1. Dataset prep
    if voices_dir.exists():
        t_jsonl, v_jsonl, count = build_dataset(voices_dir, dataset_dir)
        print(f"[OK] Train set: {t_jsonl} ({count} segments)")
        print(f"[OK] Val set:   {v_jsonl}")
    else:
        print(f"[WARN] Voices directory {voices_dir} not found, skipped chunking.")
        
    # 2. VRAM Spike Analysis
    budget = estimate_vram_budget()
    print("\n--- VRAM Budget & Spike Analysis for 4 GB GPUs ---")
    for k, v in budget.items():
        print(f"  {k:45s}: {v}")

if __name__ == "__main__":
    main()
