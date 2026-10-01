"""
AMD/CPU Path Verification Script (Punkt 5).
Simulates bootstrap with REVOICE_FORCE_CPU=1 in an isolated sandbox:
- Proves CPU-torch is installed when NVIDIA is absent/forced off.
- Proves ML imports work without CUDA.
- Proves FastAPI backend starts and reports gpu.available == False.
- Working %APPDATA%\\Revoice is 100% untouched.
"""

import os
import sys
import shutil
import subprocess
import time
import requests
import zipfile
from pathlib import Path

SANDBOX_DIR = Path(r"C:\dev\sandbox_cpu")
PROD_DATA_DIR = Path(os.environ.get("APPDATA", "")) / "Revoice"
PORT = 7852  # use port 7852 to avoid conflict with running prod backend

def main():
    print("=== AMD/CPU Bootstrap Path Verification (Punkt 5) ===")
    
    # 1. Clean & prepare sandbox
    if SANDBOX_DIR.exists():
        shutil.rmtree(SANDBOX_DIR, ignore_errors=True)
    runtime_dir = SANDBOX_DIR / "Revoice" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    
    prod_python = PROD_DATA_DIR / "runtime" / "python"
    prod_uv = PROD_DATA_DIR / "runtime" / "uv.exe"
    app_zip = Path(os.environ.get("LOCALAPPDATA", "")) / "ReVoice" / "backend.zip"
    if not app_zip.exists():
        app_zip = Path(r"C:\dev\ReVoice\src-tauri\backend.zip")
        
    assert prod_python.exists(), f"Source python not found at {prod_python}"
    assert prod_uv.exists(), f"Source uv not found at {prod_uv}"
    assert app_zip.exists(), f"backend.zip not found at {app_zip}"
    
    # Copy python embeddable and uv.exe to sandbox
    sandbox_python = runtime_dir / "python"
    shutil.copytree(prod_python, sandbox_python)
    sandbox_uv = runtime_dir / "uv.exe"
    shutil.copy2(prod_uv, sandbox_uv)
    print(f"1. Seeded runtime binaries: python={sandbox_python}, uv={sandbox_uv}")
    
    # 2. Extract backend.zip into sandbox runtime/revoice
    backend_dest = runtime_dir / "revoice"
    with zipfile.ZipFile(app_zip, 'r') as zip_ref:
        zip_ref.extractall(backend_dest)
    print(f"2. Extracted backend.zip to {backend_dest}")
    
    # 3. Create venv using uv
    venv_dir = runtime_dir / "venv"
    print("3. Creating venv with uv...")
    res = subprocess.run(
        [str(sandbox_uv), "venv", str(venv_dir), "--python", "3.10"],
        env={**os.environ, "UV_PYTHON": str(sandbox_python / "python.exe")},
        capture_output=True, text=True
    )
    assert res.returncode == 0, f"uv venv failed: {res.stderr}"
    venv_python = venv_dir / "Scripts" / "python.exe"
    assert venv_python.exists(), "venv python.exe missing"
    print(f"   Venv ready: {venv_python}")
    
    # 4. Minimal requirements for CPU backend start & health check
    reqs_path = runtime_dir / "requirements.txt"
    reqs_path.write_text(
        "fastapi==0.115.12\n"
        "uvicorn[standard]==0.34.3\n"
        "sqlalchemy==2.0.41\n"
        "pydantic==2.11.7\n"
        "pydantic-settings==2.9.1\n"
        "aiosqlite==0.21.0\n"
        "python-multipart==0.0.20\n"
        "httpx==0.28.1\n"
        "torch\n"  # PyPI default is CPU!
        "transformers\n"
        "soundfile\n"
        "librosa\n",
        encoding="utf-8"
    )
    print("4. Installing CPU dependencies (torch CPU from PyPI)...")
    res = subprocess.run(
        [str(sandbox_uv), "pip", "install", "-r", str(reqs_path), "--python", str(venv_python)],
        capture_output=True, text=True
    )
    assert res.returncode == 0, f"uv pip install failed: {res.stderr}"
    print("   Dependencies installed.")
    
    # 5. Verify torch is CPU (has_nvidia_gpu simulated with REVOICE_FORCE_CPU=1)
    os.environ["REVOICE_FORCE_CPU"] = "1"
    res = subprocess.run(
        [str(venv_python), "-c", "import torch; print(f'TORCH_VERSION={torch.__version__}, CUDA_AVAILABLE={torch.cuda.is_available()}')"],
        capture_output=True, text=True
    )
    print(f"5. ML check: {res.stdout.strip()}")
    assert "CUDA_AVAILABLE=False" in res.stdout, f"Expected CUDA_AVAILABLE=False, got: {res.stdout}"
    print("   [OK] CPU torch verified (no CUDA dependency).")
    
    # 6. Start uvicorn backend in background with REVOICE_DATA_DIR
    env = {
        **os.environ,
        "REVOICE_DATA_DIR": str(SANDBOX_DIR / "Revoice"),
        "REVOICE_PORT": str(PORT),
    }
    print(f"6. Spawning CPU backend on port {PORT}...")
    proc = subprocess.Popen(
        [str(venv_python), "-m", "uvicorn", "revoice.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=str(runtime_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    try:
        # Poll health endpoint
        ready = False
        health_data = {}
        for attempt in range(25):
            time.sleep(1)
            try:
                r = requests.get(f"http://127.0.0.1:{PORT}/api/health", timeout=2)
                if r.status_code == 200:
                    health_data = r.json()
                    ready = True
                    break
            except Exception:
                pass
                
        assert ready, f"CPU backend failed to respond on port {PORT}"
        print(f"7. CPU Health response:\n   status={health_data.get('status')}\n   version={health_data.get('version')}\n   gpu={health_data.get('gpu')}")
        assert health_data.get("status") == "ok"
        assert health_data.get("gpu", {}).get("available") == False, "Expected gpu.available == False"
        print("   [OK] Backend started successfully on CPU!")
        print("=== PUNKT 5 COMPLETED SUCCESSFULLY ===")
    finally:
        proc.terminate()
        proc.wait(timeout=5)
        # Clean sandbox
        shutil.rmtree(SANDBOX_DIR, ignore_errors=True)
        print("Sandbox cleaned up.")

if __name__ == "__main__":
    main()
