"""
English speech synthesis for the tutorial video.
Kokoro-82M (CUDA) first; if that fails, Kokoro through ONNX (kokoro-onnx); if that fails too, Edge-TTS (needs internet).
"""

import os
import re
import asyncio
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import edge_tts

import config


def _voice() -> str:
    return str(config.EN_TTS_VOICE)


def _speed() -> float:
    return float(config.EN_TTS_SPEED)


def _clamp_speed(s: float) -> float:
    return min(2.0, max(0.5, float(s)))


def _edge_rate(speed: float) -> str:
    """Edge-TTS rate string, e.g. 1.1 -> '+10%'."""
    return f"{round((_clamp_speed(speed) - 1.0) * 100):+d}%"


def _respell(text: str) -> str:
    """Swaps words for the spelling the voice pronounces correctly (pronunciation-en.json)."""
    for word, spoken in config.load_pronunciations().items():
        text = re.sub(r"(?<![A-Za-z])" + re.escape(word) + r"(?![A-Za-z])", spoken, text, flags=re.IGNORECASE)
    return text


# Windows CUDA DLL preloader: prevents "Failed to load library cublasLt64_12.dll" errors
if os.name == "nt":
    torch_lib_dir = Path(torch.__file__).parent / "lib"
    if torch_lib_dir.exists():
        os.add_dll_directory(str(torch_lib_dir))


class EnglishTTS:
    def __init__(self, device: str = "cuda"):
        self.device = device
        self._kokoro = None
        self._kokoro_onnx = None

    def get_kokoro(self):
        if self._kokoro is None:
            from kokoro import KPipeline
            print(f" -> Loading Kokoro English pipeline ({self.device.upper()})...")
            self._kokoro = KPipeline(lang_code="a", device=self.device)
        return self._kokoro

    def _kokoro_onnx_synth(self, text: str, out_wav: Path):
        """Kokoro through ONNX: the same voice without PyTorch/spaCy. Needs kokoro-v1.0.onnx and voices-v1.0.bin next to this file."""
        from kokoro_onnx import Kokoro
        base = Path(__file__).resolve().parent
        model, voices = base / "kokoro-v1.0.onnx", base / "voices-v1.0.bin"
        if not (model.is_file() and voices.is_file()):
            raise FileNotFoundError(f"{model.name} / {voices.name} not found in {base}")
        if self._kokoro_onnx is None:
            self._kokoro_onnx = Kokoro(str(model), str(voices))
        samples, sr = self._kokoro_onnx.create(text, voice=_voice(), speed=_speed(), lang="en-us")
        sf.write(str(out_wav), samples, sr)

    async def _edge_fallback(self, text: str, out_wav: Path):
        temp_mp3 = out_wav.with_suffix(".temp.mp3")
        await edge_tts.Communicate(text, "en-US-GuyNeural", rate=_edge_rate(_speed())).save(str(temp_mp3))
        subprocess.run(["ffmpeg", "-y", "-i", str(temp_mp3), "-ar", "24000", "-ac", "1", str(out_wav)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        temp_mp3.unlink(missing_ok=True)

    def synthesize(self, text: str, out_wav: Path) -> None:
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        text = _respell(text)
        print(" -> [Kokoro-82M] Synthesizing English...")
        try:
            generator = self.get_kokoro()(text, voice=_voice(), speed=_speed())
            sf.write(str(out_wav), np.concatenate([audio for _, _, audio in generator]), 24000)
        except Exception as e:      # for example Windows Application Control blocking one of Kokoro's native modules
            print(f"Kokoro error ({type(e).__name__}: {str(e)[:120]}).\n -> Trying Kokoro through ONNX (kokoro-onnx)...")
            try:
                self._kokoro_onnx_synth(text, out_wav)
            except Exception as e2:
                print(f"kokoro-onnx error ({type(e2).__name__}: {str(e2)[:120]}).\n -> Falling back to Edge-TTS (needs internet)...")
                asyncio.run(self._edge_fallback(text, out_wav))
