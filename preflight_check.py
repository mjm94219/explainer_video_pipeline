#!/usr/bin/env python3
"""
Pre-flight check: run this before a long render.   python .\\preflight_check.py

Checks the Python packages, the NVIDIA GPU, FFmpeg, the Kokoro model files, and that Ollama and ComfyUI are running
with the model and checkpoint the pipeline needs. It only reads; it changes nothing.
"""

import importlib
import shutil
import subprocess
from pathlib import Path

import requests

import config

HERE = Path(__file__).resolve().parent
problems = []


def report(num: int, label: str, ok: bool, detail: str = "", hint: str = "") -> None:
    print(f"{num:>2}. {label:<28} {'OK' if ok else 'PROBLEM'}{('  ' + detail) if detail else ''}")
    if not ok:
        problems.append(f"{label}: {hint or detail}")


# 1. Python packages
needed = ["torch", "faster_whisper", "kokoro_onnx", "edge_tts", "soundfile", "playwright", "requests"]
missing = []
for name in needed:
    try:
        importlib.import_module(name)
    except Exception as e:
        missing.append(f"{name} ({type(e).__name__})")
report(1, "Python packages", not missing, "all import" if not missing else "missing: " + ", ".join(missing),
       "install with: python -m pip install <package>")

# 2. NVIDIA GPU through PyTorch
try:
    import torch
    cuda = torch.cuda.is_available()
    report(2, "GPU (PyTorch CUDA)", cuda, torch.cuda.get_device_name(0) if cuda else "CUDA not available",
           "install the CUDA build of PyTorch (see the tutorial, Step 4)")
except Exception as e:
    report(2, "GPU (PyTorch CUDA)", False, f"PyTorch not importable ({e})", "install PyTorch with CUDA")

# 3. FFmpeg, FFprobe and the NVENC encoder
ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
report(3, "FFmpeg and FFprobe", bool(ff and fp), "found on PATH" if ff and fp else "not on PATH",
       "winget install Gyan.FFmpeg, then open a new PowerShell window")
if ff:
    try:
        enc = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20).stdout
        report(4, "NVENC video encoder", "h264_nvenc" in enc, "h264_nvenc listed" if "h264_nvenc" in enc else "h264_nvenc missing",
               "needs an NVIDIA GPU and a recent FFmpeg build")
    except Exception as e:
        report(4, "NVENC video encoder", False, str(e))

# 5. Kokoro model files in the project folder
kokoro_files = ["kokoro-v1.0.onnx", "voices-v1.0.bin"]
absent = [f for f in kokoro_files if not (HERE / f).is_file()]
report(5, "Kokoro model files", not absent, "both present" if not absent else "missing: " + ", ".join(absent),
       f"download them from the kokoro-onnx releases page into {HERE}")

# 6. Ollama and the planner model
try:
    r = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=3)
    models = [m["name"] for m in r.json().get("models", [])]
    have = config.LLM_MODEL in models
    report(6, "Ollama and planner model", have, f"{config.LLM_MODEL} installed" if have else f"{config.LLM_MODEL} not installed (found: {models})",
           f"run: ollama pull {config.LLM_MODEL}")
except Exception as e:
    report(6, "Ollama and planner model", False, f"not running ({type(e).__name__})", "start Ollama")

# 7. ComfyUI and the background checkpoint
try:
    requests.get(f"{config.COMFY_URL}/system_stats", timeout=3).raise_for_status()
    try:
        from diffusion_engine import IMAGE_PROFILES
        want = IMAGE_PROFILES[config.IMAGE_MODEL]["ckpt"]
        info = requests.get(f"{config.COMFY_URL}/object_info/CheckpointLoaderSimple", timeout=5).json()
        have_ckpts = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        report(7, "ComfyUI and checkpoint", want in have_ckpts, f"{want} available" if want in have_ckpts else f"{want} not found in ComfyUI",
               f"put {want} in ComfyUI\\models\\checkpoints, then restart ComfyUI")
    except Exception as e:
        report(7, "ComfyUI and checkpoint", True, f"running (checkpoint not verified: {type(e).__name__})")
except Exception as e:
    report(7, "ComfyUI and checkpoint", False, f"not running ({type(e).__name__})", "start ComfyUI (run_nvidia_gpu.bat)")

print()
if problems:
    print(f"{len(problems)} problem(s) to fix before a run:")
    for p in problems:
        print(f"  - {p}")
else:
    print("All checks passed. Ready to run.")
