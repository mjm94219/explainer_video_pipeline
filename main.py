#!/usr/bin/env python3
"""
Autonomous AI Video Studio - Master Orchestrator
Coordinates configuration, LLM script planning, TTS speech dispatch,
Whisper subtitle alignment, ComfyUI diffusion, HTML animation rendering,
and multi-track video assembly with full checkpoint/resume support.
"""

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

from config import PROJECTS_BASE_DIR, SUBTITLE_FONT_SCALE
from cli import get_project_config, calculate_social_safe_bounds
from llm_planner import generate_script_manifest
from tts_engine import EnglishTTS
from subtitle_engine import transcribe_and_align
from diffusion_engine import render_background_plate
from infographic_engine import render_animation
from assembly_ffmpeg import assemble_video, get_duration


def _valid_asset(path_str: str | Path | None) -> bool:
    """Returns True if the file path exists on disk and is non-empty (> 0 bytes)."""
    if not path_str:
        return False
    p = Path(path_str)
    return p.is_file() and p.stat().st_size > 0


def _is_newer(source: Path, derived: Path) -> bool:
    """True when `source` was saved after `derived` was made (so `derived` is out of date)."""
    return _valid_asset(source) and _valid_asset(derived) and source.stat().st_mtime > derived.stat().st_mtime + 1


def _drop(*paths) -> None:
    for p in paths:
        if p:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError as e:
                print(f" -> [warning] could not delete {p}: {e}")


def build_project_paths(root: Path) -> Dict[str, Path]:
    """Returns and ensures the standardized explainer project folder tree."""
    paths = {
        "root": root,
        "project_json": root / "project.json",
        "audio": root / "Audio",
        "voiceover": root / "Audio" / "Voiceover",
        "voiceover_en": root / "Audio" / "Voiceover" / "English",
        "music": root / "Audio" / "Music",
        "sfx": root / "Audio" / "SoundEffects",
        "images": root / "Images",
        "graphics": root / "Graphics",
        "exports": root / "Exports",
        "subtitles": root / "Subtitles",
        "scripts": root / "Scripts",
        "scenes": root / "Scenes",
    }
    for key, p in paths.items():
        if key != "project_json":
            p.mkdir(parents=True, exist_ok=True)
    return paths


def project_folder_name(topic: str, languages) -> str:
    """English-only folder name built from the topic text you typed (never from the LLM), plus a language suffix.
    'How Computers Work From Electricity to Storage. Exactly 5 scenes.' -> How_Computers_Work_From_Electricity_to_Storag_en"""
    first = re.split(r"[.\n]", str(topic).strip(), maxsplit=1)[0]          # first sentence / first line
    first = first.encode("ascii", "ignore").decode()                         # drop any non-English characters
    first = re.sub(r"[^A-Za-z0-9 _-]", "", first)
    base = re.sub(r"\s+", "_", first.strip())[:45].strip("_-") or "Explainer_Video"
    if isinstance(languages, str):
        languages = languages.split(",")
    langs = [re.sub(r"[^a-z]", "", str(l).lower()) for l in (languages or [])]
    suffix = "_".join(l for l in langs if l) or "en"
    return f"{base}_{suffix}"


def init_project_workspace(topic: str, languages=None) -> Dict[str, Path]:
    """Creates the project root directory (English name + _en suffix) and initializes its folder tree."""
    root = (PROJECTS_BASE_DIR / project_folder_name(topic, languages)).resolve()
    return build_project_paths(root)


def save_project_json(project_json_path: Path, payload: Dict[str, Any]) -> None:
    """Persists the master project.json state with readable Unicode."""
    payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    with open(project_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def main():
    cli_result = get_project_config()
    resume_json_path = cli_result.get("resume_project_json")

    # -----------------------------------------------------------------------
    # Mode A: Resume Existing Project from project.json
    # -----------------------------------------------------------------------
    if resume_json_path:
        proj_file = Path(resume_json_path).resolve()
        print(f"\n[RESUME] Loading project state from: {proj_file}")
        with open(proj_file, "r", encoding="utf-8") as f:
            project_state = json.load(f)

        config = project_state["config"]
        bounds = project_state["safe_bounds"]
        scenes = project_state.get("scenes", [])
        dirs = build_project_paths(proj_file.parent)
        manifest_title = project_state.get("title", config["topic"])

        if not scenes:
            sys.exit("Error: No scenes found in project.json to resume.")

    # -----------------------------------------------------------------------
    # Mode B: Fresh Project Run (or Auto-Resume if identical folder exists)
    # -----------------------------------------------------------------------
    else:
        config = cli_result

        # 1. Script Decomposition via Ollama (qwen2.5:14b)
        manifest = generate_script_manifest(config)
        scenes = manifest.get("scenes", [])
        if not scenes:
            sys.exit("Error: No scenes generated.")

        manifest_title = manifest.get("title", config["topic"])

        # 2. Initialize Project Directory Tree
        dirs = init_project_workspace(config["topic"], config.get("languages"))
        print(f" -> Project Root initialized at: {dirs['root']}")

        # Copy background music into Audio/Music/ if provided
        if config.get("music") and Path(config["music"]).is_file():
            src_music = Path(config["music"]).resolve()
            dest_music = dirs["music"] / src_music.name
            if src_music != dest_music:
                shutil.copy2(str(src_music), str(dest_music))
            config["music"] = str(dest_music)

        # Save raw LLM script manifest into Scripts/script_manifest.json
        script_manifest_file = dirs["scripts"] / "script_manifest.json"
        with open(script_manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        # 3. Derive Subtitle & Mobile Safe Zone Boundaries
        font_size = max(28, int(config["height"] * SUBTITLE_FONT_SCALE))
        margin_v = int(config["height"] * 0.08)
        bounds = calculate_social_safe_bounds(
            canvas_height=config["height"],
            fontsize=font_size,
            margin_v=margin_v,
            max_lines=1,
            outline=3,
            aspect_ratio=config["aspect_ratio"]
        )
        print(f" -> Synchronized Bounds: sub_margin={bounds['sub_margin_ratio']}, safe_w={bounds['safe_width_ratio']}, x_off={bounds['x_offset_ratio']}")

        project_state = {
            "title": manifest_title,
            "topic": config["topic"],
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "config": config,
            "safe_bounds": bounds,
            "directories": {k: str(v) for k, v in dirs.items()},
            "scenes": scenes,
        }
        save_project_json(dirs["project_json"], project_state)

    # -----------------------------------------------------------------------
    # 4. Sequential Scene Synthesis with Per-Asset Checkpoint Verification
    # -----------------------------------------------------------------------
    import torch
    tts = EnglishTTS(device="cuda" if torch.cuda.is_available() else "cpu")

    for sc in scenes:
        sid = sc["scene_id"]
        print(f"\n--- Processing Scene {sid} ---")

        # Scripts/narration_sNN.txt is the source of truth: edit it, re-run, and the voice and subtitles follow it.
        narration_txt_path = dirs["scripts"] / f"narration_s{sid:02d}.txt"
        if _valid_asset(narration_txt_path):
            edited = narration_txt_path.read_text(encoding="utf-8-sig").strip()
            if edited:
                sc["narration"] = edited
        else:
            narration_txt_path.write_text(sc["narration"], encoding="utf-8")
        sc["narration_script_path"] = str(narration_txt_path)

        # Scripts/onscreen_sNN.json holds the animation, title and card texts for the scene: edit it and re-run.
        onscreen_path = dirs["scripts"] / f"onscreen_s{sid:02d}.json"
        if _valid_asset(onscreen_path):
            try:
                edited_ui = json.loads(onscreen_path.read_text(encoding="utf-8-sig"))
                for key in ("animation", "heading", "animation_params"):
                    if key in edited_ui:
                        sc[key] = edited_ui[key]
            except Exception as e:
                print(f" -> [warning] {onscreen_path.name} is not valid JSON ({e}); using the planner's text.")
        else:
            onscreen_path.write_text(json.dumps({k: sc.get(k) for k in ("animation", "heading", "animation_params")},
                                                ensure_ascii=False, indent=2), encoding="utf-8")

        wav_path = Path(sc["audio_path"]) if _valid_asset(sc.get("audio_path")) else (dirs["voiceover_en"] / f"narration_{sid:02d}.wav")
        ass_path = Path(sc["ass_path"]) if _valid_asset(sc.get("ass_path")) else (dirs["subtitles"] / f"captions_{sid:02d}.ass")
        expected_mov = Path(sc["info_path"]) if _valid_asset(sc.get("info_path")) else (dirs["graphics"] / f"infographic_{sid:02d}.mov")

        # Out-of-date checks: narration text -> voiceover -> subtitles and infographic (its length follows the voiceover)
        if _is_newer(narration_txt_path, wav_path):
            print(f" -> [Edited] {narration_txt_path.name} changed after the voiceover was made: redoing voice, subtitles and infographic.")
            _drop(wav_path, ass_path, expected_mov)
        if _is_newer(wav_path, ass_path):
            _drop(ass_path)
        if _is_newer(wav_path, expected_mov) or _is_newer(onscreen_path, expected_mov):
            _drop(expected_mov)

        # Step A: Voice (Kokoro) -> Audio/Voiceover/English
        if _valid_asset(wav_path):
            print(f" -> [Skip] Voiceover already exists: {wav_path.name}")
        else:
            tts.synthesize(sc["narration"], wav_path)
        sc["audio_path"] = str(wav_path)
        sc["lang"] = "en"
        save_project_json(dirs["project_json"], project_state)

        # Step B: Subtitles (faster-whisper word timing) -> Subtitles/
        if _valid_asset(ass_path):
            print(f" -> [Skip] Subtitles already exist: {ass_path.name}")
        else:
            transcribe_and_align(wav_path, ass_path, "en", config["width"], config["height"])
        sc["ass_path"] = str(ass_path)
        save_project_json(dirs["project_json"], project_state)

        # Step C: ComfyUI Diffusion Background Plate -> Images/
        bg_path = Path(sc["bg_path"]) if _valid_asset(sc.get("bg_path")) else (dirs["images"] / f"background_{sid:02d}.png")
        if _valid_asset(bg_path):
            print(f" -> [Skip] Background plate already exists: {bg_path.name}")
        else:
            render_background_plate(sc["visual_prompt"], bg_path, config["width"], config["height"])
        sc["bg_path"] = str(bg_path)
        save_project_json(dirs["project_json"], project_state)

        # Step D: HTML animation block (Playwright) -> Graphics
        if _valid_asset(expected_mov):
            print(f" -> [Skip] Animation already exists: {expected_mov.name}")
            info_path = expected_mov
        else:
            info_path = render_animation(
                sid, graphics_dir=dirs["graphics"],
                width=config["width"], height=config["height"], fps=config["fps"],
                duration=get_duration(wav_path) + 0.3,
                safe_w=bounds["safe_width_ratio"],
                sub_margin=bounds["sub_margin_ratio"],
                heading=sc.get("heading", ""),
                key_points=sc.get("key_points"),
                animation=sc.get("animation", ""),
                anim_params=sc.get("animation_params"),
            )
        sc["info_path"] = str(info_path)
        save_project_json(dirs["project_json"], project_state)

    # -----------------------------------------------------------------------
    # 5. Master Assembly -> Scenes/ (cuts) & Exports/ (final master)
    # -----------------------------------------------------------------------
    output_filename = Path(config.get("output", "master_explainer.mp4")).name
    final_export_path = dirs["exports"] / output_filename

    assemble_video(
        scenes=scenes,
        scenes_dir=dirs["scenes"],
        output_mp4=final_export_path,
        width=config["width"],
        height=config["height"],
        fps=config["fps"],
        bg_music=config.get("music")
    )
    project_state["final_video_path"] = str(final_export_path)

    save_project_json(dirs["project_json"], project_state)
    print(f" -> Project manifest updated: {dirs['project_json']}")


if __name__ == "__main__":
    main()