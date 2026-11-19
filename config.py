"""
Global Configuration & Presets
Defines network endpoints, video canvas geometries, supported formats, and lexicons.
"""

from pathlib import Path
from typing import Dict, Tuple, Set

OLLAMA_URL: str = "http://127.0.0.1:11434"
COMFY_URL: str = "http://127.0.0.1:8188"
LLM_MODEL: str = "qwen2.5:14b"
OLLAMA_NUM_CTX: int = 8192
WHISPER_MODEL_SIZE: str = "base"

# Subtitle text size as a fraction of the video height (0.045 = 48 px at 1080p, 0.055 = 59 px).
# Keep it at or below about 0.055 so the subtitles stay clear of the animations; delete the Subtitles folder files to rebuild.
SUBTITLE_FONT_SCALE: float = 0.055

# Base directory where all Explainer Video project folders are created
PROJECTS_BASE_DIR: Path = Path(__file__).resolve().parent / "projects"

# Animation block pages. Add a block by editing the page (see blocks_README.md).
EXPLAINER_BLOCKS_HTML: Path = Path(__file__).resolve().parent / "blocks.html"   # flow, compare, steps, stat, bits, cells, ring

# Image model for backgrounds: "sdxl_base" (full quality, follows prompts well, slower)
# or "lightning" (4 steps, fast, but ignores detail). See IMAGE_PROFILES in diffusion_engine.py.
IMAGE_MODEL: str = "sdxl_base"


# Formats supported for background soundtracks
SUPPORTED_AUDIO_EXTENSIONS: Set[str] = {".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg"}

# Video aspect ratio to resolution mapping
RESOLUTION_PRESETS: Dict[str, Dict[str, Tuple[int, int]]] = {
    "16:9": {
        "720p": (1280, 720),
        "1080p": (1920, 1080),
        "4k": (3840, 2160),
        "4K": (3840, 2160)  # Added uppercase alias
    },
    "9:16": {
        "720p": (720, 1280),
        "1080p": (1080, 1920),
        "4k": (2160, 3840),
        "4K": (2160, 3840)  # Added uppercase alias
    },
    "1:1": {
        "720p": (720, 720),
        "1080p": (1080, 1080),
        "4k": (2160, 2160),
        "4K": (2160, 2160)  # Added uppercase alias
    }
}

# English narration (Kokoro). US male voices: am_adam, am_michael, am_eric, am_onyx, am_echo, am_fenrir, am_puck.
EN_TTS_VOICE: str = "am_adam"
EN_TTS_SPEED: float = 1.0   # 0.9 = slower, 1.1 = faster
