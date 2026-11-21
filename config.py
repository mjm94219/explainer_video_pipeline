"""
Settings loader.
Every value you may want to change is in settings.json (edit that file, not this one). This module reads it once and exposes
each setting as a module-level name, so the rest of the code keeps using config.LLM_MODEL, config.EN_TTS_VOICE and so on.
A missing or mistyped setting stops the run with a message that names it.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Set

HERE = Path(__file__).resolve().parent
SETTINGS_FILE: Path = HERE / "settings.json"

# Fixed parts of the project layout (not settings): the animation engine page, the animation files and the pronunciation list.
EXPLAINER_ANIMATOR_HTML: Path = HERE / "animator.html"      # the generic page that draws whatever the animation_*.json files describe
EXPLAINER_ANIMATION_DIR: Path = HERE                        # folder holding the animation files
ANIMATION_FILE_PATTERN: str = "animation_*.json"            # one file per animation: animation_flow.json, animation_bits.json ...
PRONUNCIATION_FILE: Path = HERE / "pronunciation-en.json"

# name -> allowed type. "bool|null" accepts true, false or null; "float" also accepts whole numbers; "list" is a list of text.
_SCHEMA = {
    "LLM_MODEL": "str", "OLLAMA_THINK": "bool|null", "OLLAMA_NUM_CTX": "int", "OLLAMA_NUM_PREDICT": "int",
    "NARRATION_WORDS": "str", "WORDS_PER_SECOND": "float", "SCENE_WORDS_MIN": "int", "SCENE_WORDS_MAX": "int",
    "OLLAMA_URL": "str", "COMFY_URL": "str", "COMFY_SUBMIT_TIMEOUT": "int", "COMFY_POLL_TIMEOUT": "int", "COMFY_RENDER_DEADLINE": "int",
    "EN_TTS_VOICE": "str", "EN_TTS_SPEED": "float", "WHISPER_MODEL_SIZE": "str",
    "IMAGE_MODEL": "str", "DEFAULT_BLUR": "float", "BACKGROUND_ZOOM_MAX": "float",
    "DEFAULT_WIDTH": "int", "DEFAULT_HEIGHT": "int", "DEFAULT_FPS": "int", "DEFAULT_ANIMATION": "str",
    "SUBTITLE_FONT_SCALE": "float", "TAIL_PAD_SEC": "float", "VIDEO_BITRATE": "str", "AUDIO_BITRATE": "str", "MUSIC_VOLUME": "float",
    "PROJECTS_FOLDER": "str", "SUPPORTED_AUDIO_EXTENSIONS": "list",
}


def _fail(message: str):
    print(f"\n[settings] {message}\n          Fix {SETTINGS_FILE.name} (restore the value from the README table if unsure).", file=sys.stderr)
    raise SystemExit(1)


def _read() -> Dict[str, object]:
    if not SETTINGS_FILE.is_file():
        _fail(f"{SETTINGS_FILE.name} not found next to the scripts ({SETTINGS_FILE}).")
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8-sig"))
    except Exception as e:
        _fail(f"{SETTINGS_FILE.name} is not valid JSON: {e}")
    flat: Dict[str, object] = {}
    for key, value in data.items():                 # groups ("planner": {...}) are flattened; keys starting with _ are notes
        if str(key).startswith("_"):
            continue
        if isinstance(value, dict):
            flat.update({k: v for k, v in value.items() if not str(k).startswith("_")})
        else:
            flat[key] = value
    return flat


def _check(name: str, value, kind: str):
    ok = {
        "str": isinstance(value, str) and value.strip() != "",
        "int": isinstance(value, int) and not isinstance(value, bool),
        "float": isinstance(value, (int, float)) and not isinstance(value, bool),
        "bool|null": value is None or isinstance(value, bool),
        "list": isinstance(value, list) and all(isinstance(x, str) for x in value),
    }[kind]
    if not ok:
        shown = {"str": "text in quotes", "int": "a whole number", "float": "a number", "bool|null": "true, false or null", "list": "a list of text"}[kind]
        _fail(f"setting {name} must be {shown} (found {value!r}).")


_values = _read()
for _name, _kind in _SCHEMA.items():
    if _name not in _values:
        _fail(f"setting {_name} is missing.")
    _check(_name, _values[_name], _kind)
_unknown = sorted(set(_values) - set(_SCHEMA))
if _unknown:
    print(f"[settings] note: unknown setting(s) in {SETTINGS_FILE.name} are ignored: {', '.join(_unknown)}", file=sys.stderr)

# ---- the settings, as plain names -------------------------------------------------------------------------------------------
LLM_MODEL: str = _values["LLM_MODEL"]
OLLAMA_THINK = _values["OLLAMA_THINK"]
OLLAMA_NUM_CTX: int = _values["OLLAMA_NUM_CTX"]
OLLAMA_NUM_PREDICT: int = _values["OLLAMA_NUM_PREDICT"]
NARRATION_WORDS: str = _values["NARRATION_WORDS"]
WORDS_PER_SECOND: float = float(_values["WORDS_PER_SECOND"])
SCENE_WORDS_MIN: int = _values["SCENE_WORDS_MIN"]
SCENE_WORDS_MAX: int = _values["SCENE_WORDS_MAX"]

OLLAMA_URL: str = _values["OLLAMA_URL"]
COMFY_URL: str = _values["COMFY_URL"]
COMFY_SUBMIT_TIMEOUT: int = _values["COMFY_SUBMIT_TIMEOUT"]
COMFY_POLL_TIMEOUT: int = _values["COMFY_POLL_TIMEOUT"]
COMFY_RENDER_DEADLINE: int = _values["COMFY_RENDER_DEADLINE"]

EN_TTS_VOICE: str = _values["EN_TTS_VOICE"]
EN_TTS_SPEED: float = float(_values["EN_TTS_SPEED"])
WHISPER_MODEL_SIZE: str = _values["WHISPER_MODEL_SIZE"]

IMAGE_MODEL: str = _values["IMAGE_MODEL"]
DEFAULT_BLUR: float = float(_values["DEFAULT_BLUR"])
BACKGROUND_ZOOM_MAX: float = float(_values["BACKGROUND_ZOOM_MAX"])

DEFAULT_WIDTH: int = _values["DEFAULT_WIDTH"]
DEFAULT_HEIGHT: int = _values["DEFAULT_HEIGHT"]
DEFAULT_FPS: int = _values["DEFAULT_FPS"]
DEFAULT_ANIMATION: str = _values["DEFAULT_ANIMATION"]
SUBTITLE_FONT_SCALE: float = float(_values["SUBTITLE_FONT_SCALE"])
TAIL_PAD_SEC: float = float(_values["TAIL_PAD_SEC"])
VIDEO_BITRATE: str = _values["VIDEO_BITRATE"]
AUDIO_BITRATE: str = _values["AUDIO_BITRATE"]
MUSIC_VOLUME: float = float(_values["MUSIC_VOLUME"])

_projects = Path(_values["PROJECTS_FOLDER"])
PROJECTS_BASE_DIR: Path = _projects if _projects.is_absolute() else HERE / _projects
SUPPORTED_AUDIO_EXTENSIONS: Set[str] = {e.lower() if e.startswith(".") else "." + e.lower() for e in _values["SUPPORTED_AUDIO_EXTENSIONS"]}


def load_pronunciations() -> Dict[str, str]:
    """Reads pronunciation-en.json -> {word: spoken spelling}. Missing or broken file = no changes (with a warning)."""
    try:
        if not PRONUNCIATION_FILE.is_file():
            return {}
        data = json.loads(PRONUNCIATION_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("expected a JSON object like {\"RAM\": \"ram\"}")
        return {str(k): str(v) for k, v in data.items() if not str(k).startswith("_") and str(k).strip()}
    except Exception as e:
        print(f" -> [warning] could not read {PRONUNCIATION_FILE.name}: {e}")
        return {}
