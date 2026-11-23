"""
CLI & Preset Management Engine
Handles CLI argument parsing, interactive configuration menus, JSON profile CRUD,
project resume selection, file/format validation, and platform safe-margin calculations.
"""

import json
import re
import copy
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List

from config import (SUPPORTED_AUDIO_EXTENSIONS, PROJECTS_BASE_DIR, DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_FPS,
                    DEFAULT_BLUR, SCENE_WORDS_MIN, SCENE_WORDS_MAX, WORDS_PER_SECOND)
from animation_library import load_catalog

PROFILES_FILE = Path(__file__).resolve().parent / "video_template.json"
DEFAULT_SIZE = (DEFAULT_WIDTH, DEFAULT_HEIGHT)


def aspect_of(width: int, height: int) -> str:
    """Orientation label used by the planner and the safe-margin maths: '9:16', '1:1' or '16:9'."""
    if height > width:
        return "9:16"
    if height == width:
        return "1:1"
    return "16:9"


def parse_size(text: str, fallback: tuple) -> tuple:
    """'1920x1080' -> (1920, 1080); anything else keeps the fallback."""
    m = re.fullmatch(r"\s*(\d{3,5})\s*[xX*]\s*(\d{3,5})\s*", text or "")
    if not m:
        return fallback
    w, h = int(m.group(1)), int(m.group(2))
    return (w - w % 2, h - h % 2)       # video encoders need even sizes


# ---------------------------------------------------------------------------
# 1. Profile Disk I/O & Validation
# ---------------------------------------------------------------------------
def load_profiles() -> Dict[str, Any]:
    """Loads saved profiles from video_template.json, falling back to built-in presets if missing."""
    if not PROFILES_FILE.is_file():
        w, h = DEFAULT_SIZE
        return {
            f"Video_Portrait_{w}x{h}": {"description": "Vertical portrait (built-in fallback; video_template.json is missing)",
                                        "width": h, "height": w, "fps": DEFAULT_FPS, "languages": ["en"], "music": None},
            f"Video_Landscape_{w}x{h}": {"description": "Widescreen landscape (built-in fallback; video_template.json is missing)",
                                         "width": w, "height": h, "fps": DEFAULT_FPS, "languages": ["en"], "music": None},
        }
    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to parse video_template.json ({e}). Using empty registry.")
        return {}


def save_profiles_file(profiles: Dict[str, Any]) -> bool:
    """Overwrites video_template.json with formatted JSON."""
    try:
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error writing to {PROFILES_FILE.name}: {e}")
        return False


def save_profile(name: str, profile_data: Dict[str, Any]) -> bool:
    """Persists a single sanitized profile into video_template.json."""
    profiles = load_profiles()
    clean_entry = {
        "description": profile_data.get("description", f"Preset for {profile_data.get('width', DEFAULT_SIZE[0])}x{profile_data.get('height', DEFAULT_SIZE[1])}"),
        "width": profile_data.get("width", DEFAULT_SIZE[0]),
        "height": profile_data.get("height", DEFAULT_SIZE[1]),
        "fps": profile_data.get("fps", DEFAULT_FPS),
        "languages": profile_data.get("languages", ["en"]),
        "music": profile_data.get("music", None)
    }
    profiles[name] = clean_entry
    if save_profiles_file(profiles):
        print(f" -> Successfully saved preset '{name}' to {PROFILES_FILE.name}!")
        return True
    return False


def find_existing_projects() -> List[Path]:
    """Returns a list of project directories containing a project.json file."""
    if not PROJECTS_BASE_DIR.exists():
        return []
    projects = [
        p.parent for p in PROJECTS_BASE_DIR.glob("*/project.json")
        if p.is_file()
    ]
    return sorted(projects, key=lambda p: p.stat().st_mtime, reverse=True)


def resolve_resume_path(resume_arg: str) -> Path:
    """Resolves a project folder path or project folder name to its project.json."""
    candidate = Path(resume_arg).expanduser()
    if candidate.is_file() and candidate.name == "project.json":
        return candidate.resolve()
    if candidate.is_dir() and (candidate / "project.json").is_file():
        return (candidate / "project.json").resolve()

    # Check inside PROJECTS_BASE_DIR by folder name
    in_base = PROJECTS_BASE_DIR / resume_arg / "project.json"
    if in_base.is_file():
        return in_base.resolve()

    raise FileNotFoundError(
        f"Could not find project.json for '{resume_arg}' directly or inside {PROJECTS_BASE_DIR}"
    )


def prompt_and_validate_audio_path(current_music: Optional[str]) -> Optional[str]:
    """Prompts for a soundtrack file path, validating format and disk existence."""
    display_current = current_music or "None"
    ext_list_str = ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))

    while True:
        music_in = input(f"Background Music Path [{display_current}]: ").strip()

        if not music_in:
            if current_music:
                check_path = Path(current_music).expanduser()
                if not check_path.is_file():
                    print(f"  [!] Warning: Existing path not found on disk: {check_path}")
                    act = input("      Keep missing path anyway? [y/N/clear]: ").strip().lower()
                    if act in ("y", "yes"):
                        return current_music
                    elif act == "clear":
                        return None
                    continue
            return current_music

        if music_in.lower() in ("none", "null", "clear"):
            return None

        entered_path = Path(music_in).expanduser()
        suffix = entered_path.suffix.lower()

        if suffix not in SUPPORTED_AUDIO_EXTENSIONS:
            print(f"  [!] Invalid format '{suffix or 'none'}'.")
            print(f"      Supported extensions: {ext_list_str}")
            choice = input("      [1] Re-enter path\n      [2] Force use anyway\n      [3] Clear (Set to None)\n      Choice [1-3, default=1]: ").strip()
            if choice == "2":
                pass
            elif choice == "3":
                return None
            else:
                continue

        if entered_path.is_file():
            print(f"  ✓ Verified audio file ({suffix}): {entered_path.name}")
            return str(entered_path)
        else:
            print(f"  [!] Warning: File does not exist at '{entered_path}'")
            choice = input("      [1] Re-enter path\n      [2] Save path anyway\n      [3] Clear (Set to None)\n      Choice [1-3, default=1]: ").strip()
            if choice == "2":
                return str(entered_path)
            elif choice == "3":
                return None


# ---------------------------------------------------------------------------
# 2. Preset CRUD Management Operations
# ---------------------------------------------------------------------------
def print_profile_card(name: str, p: Dict[str, Any]):
    print(f"\nPreset: [{name}]")
    print(f"  Description:      {p.get('description', 'N/A')}")
    print(f"  Size:             {p.get('width')}x{p.get('height')} ({aspect_of(p.get('width', 0), p.get('height', 0))})")
    print(f"  Frame Rate:       {p.get('fps')} fps")
    print(f"  Languages:        {', '.join(p.get('languages', []))}")
    print(f"  Background Music: {p.get('music') or 'None'}")


def view_all_profiles(profiles: Dict[str, Any]):
    if not profiles:
        print("\n[!] No presets found.")
        return
    print("\n" + "=" * 60)
    print("                SAVED PRESET PROFILES")
    print("=" * 60)
    for name, data in profiles.items():
        print_profile_card(name, data)
    print("=" * 60)


def modify_existing_profile(profiles: Dict[str, Any]) -> Dict[str, Any]:
    keys = list(profiles.keys())
    if not keys:
        print("\n[!] No presets available to modify.")
        return profiles

    print("\nSelect Preset to Modify:")
    for idx, k in enumerate(keys, 1):
        print(f"  {idx}) {k}")

    choice = input(f"Select preset [1-{len(keys)}]: ").strip()
    try:
        p_name = keys[int(choice) - 1]
    except (ValueError, IndexError):
        print("[!] Invalid selection.")
        return profiles

    p = profiles[p_name]
    print_profile_card(p_name, p)
    print("\n(Press Enter on any field to keep current value)")

    desc_in = input(f"Description [{p.get('description')}]: ").strip()
    desc = desc_in if desc_in else p.get("description")

    size_in = input(f"Size WIDTHxHEIGHT, e.g. 1920x1080 [{p.get('width')}x{p.get('height')}]: ").strip()
    width, height = parse_size(size_in, (p.get("width", DEFAULT_SIZE[0]), p.get("height", DEFAULT_SIZE[1])))

    fps_in = input(f"FPS (24 / 30 / 60) [{p.get('fps')}]: ").strip()
    fps = int(fps_in) if fps_in in ("24", "30", "60") else p.get("fps")

    current_langs_str = ",".join(p.get("languages", []))
    langs_in = input(f"Languages (comma-separated) [{current_langs_str}]: ").strip()
    langs = [l.strip().lower() for l in langs_in.split(",") if l.strip()] if langs_in else p.get("languages")

    music = prompt_and_validate_audio_path(p.get("music"))

    p.update({
        "description": desc, "width": width, "height": height,
        "fps": fps, "languages": langs, "music": music
    })

    profiles[p_name] = p
    if save_profiles_file(profiles):
        print(f" -> Preset '{p_name}' successfully updated!")
    return profiles


def duplicate_existing_profile(profiles: Dict[str, Any]) -> Dict[str, Any]:
    keys = list(profiles.keys())
    if not keys:
        print("\n[!] No presets available to duplicate.")
        return profiles

    print("\nSelect Preset to Duplicate / Clone:")
    for idx, k in enumerate(keys, 1):
        print(f"  {idx}) {k} ({profiles[k].get('description', '')})")

    choice = input(f"Select preset [1-{len(keys)}]: ").strip()
    try:
        source_name = keys[int(choice) - 1]
    except (ValueError, IndexError):
        print("[!] Invalid selection.")
        return profiles

    source_data = profiles[source_name]

    target_name = input(f"\nEnter name for new clone of '{source_name}': ").strip()
    while not target_name:
        target_name = input("Target name cannot be empty. Enter name: ").strip()

    if target_name in profiles:
        overwrite = input(f"Preset '{target_name}' already exists. Overwrite? [y/N]: ").strip().lower()
        if overwrite not in ("y", "yes"):
            print(" -> Duplication cancelled.")
            return profiles

    cloned_data = copy.deepcopy(source_data)
    default_desc = f"{cloned_data.get('description', '')} (Copy)".strip()
    new_desc = input(f"Description [{default_desc}]: ").strip()
    cloned_data["description"] = new_desc if new_desc else default_desc

    tweak = input("\nCustomize parameters for this clone now? [Y/n]: ").strip().lower()
    if tweak not in ("n", "no"):
        print("\n(Press Enter to accept current value from source preset)")

        cur_size = (cloned_data.get("width", DEFAULT_SIZE[0]), cloned_data.get("height", DEFAULT_SIZE[1]))
        size_in = input(f"Size WIDTHxHEIGHT, e.g. 1920x1080 [{cur_size[0]}x{cur_size[1]}]: ").strip()
        cloned_data["width"], cloned_data["height"] = parse_size(size_in, cur_size)

        cur_fps = cloned_data.get("fps", DEFAULT_FPS)
        fps_in = input(f"FPS (24 / 30 / 60) [{cur_fps}]: ").strip()
        if fps_in in ("24", "30", "60"):
            cloned_data["fps"] = int(fps_in)

        cur_langs_str = ",".join(cloned_data.get("languages", ["en"]))
        langs_in = input(f"Languages (comma-separated) [{cur_langs_str}]: ").strip()
        if langs_in:
            cloned_data["languages"] = [l.strip().lower() for l in langs_in.split(",") if l.strip()]

        cloned_data["music"] = prompt_and_validate_audio_path(cloned_data.get("music"))

    if save_profile(target_name, cloned_data):
        print(f" -> Successfully created, customized, and saved '{target_name}'!")
        profiles[target_name] = cloned_data

    return profiles


def delete_existing_profile(profiles: Dict[str, Any]) -> Dict[str, Any]:
    keys = list(profiles.keys())
    if not keys:
        print("\n[!] No presets available to delete.")
        return profiles

    print("\nSelect Preset to Delete:")
    for idx, k in enumerate(keys, 1):
        print(f"  {idx}) {k} ({profiles[k].get('description', '')})")

    choice = input(f"Select preset [1-{len(keys)}]: ").strip()
    try:
        p_name = keys[int(choice) - 1]
    except (ValueError, IndexError):
        print("[!] Invalid selection.")
        return profiles

    confirm = input(f"Are you sure you want to delete preset '{p_name}'? [y/N]: ").strip().lower()
    if confirm in ("y", "yes"):
        del profiles[p_name]
        if save_profiles_file(profiles):
            print(f" -> Preset '{p_name}' deleted.")
    else:
        print(" -> Deletion cancelled.")
    return profiles


def manage_profiles_menu(profiles: Dict[str, Any]) -> Dict[str, Any]:
    while True:
        print("\n" + "-" * 50)
        print("         PRESET PROFILE MANAGER")
        print("-" * 50)
        print("  1) View all presets in detail")
        print("  2) Modify an existing preset")
        print("  3) Duplicate / Clone a preset")
        print("  4) Delete a preset")
        print("  5) Return to Video Setup")
        sub_choice = input("Select [1-5, default=5]: ").strip()

        if sub_choice == "1":
            view_all_profiles(profiles)
        elif sub_choice == "2":
            profiles = modify_existing_profile(profiles)
        elif sub_choice == "3":
            profiles = duplicate_existing_profile(profiles)
        elif sub_choice == "4":
            profiles = delete_existing_profile(profiles)
        else:
            break
    return profiles


# ---------------------------------------------------------------------------
# 3. Dynamic Safe Bounds Computation
# ---------------------------------------------------------------------------
def calculate_social_safe_bounds(
    canvas_height: int,
    fontsize: int,
    margin_v: int,
    max_lines: int = 1,
    outline: int = 3,
    aspect_ratio: str = "9:16"
) -> Dict[str, float]:
    """
    Computes precise bounding ratios to prevent animation overlap with
    subtitles and native mobile overlay buttons (YouTube Shorts / Reels).
    """
    text_block_px = (max_lines * fontsize * 1.25) + (outline * 2)
    base_sub_envelope_px = margin_v + text_block_px

    if aspect_ratio == "9:16":
        min_bottom_ratio = 0.24
        right_rail_ratio = 0.16
        left_pad_ratio = 0.06
    else:
        min_bottom_ratio = 0.08
        right_rail_ratio = 0.06
        left_pad_ratio = 0.06

    derived_bottom_px = base_sub_envelope_px + int(canvas_height * 0.02)
    effective_bottom_ratio = max(min_bottom_ratio, derived_bottom_px / canvas_height)
    usable_width_ratio = 1.0 - (right_rail_ratio + left_pad_ratio)
    center_x_norm = (left_pad_ratio + (1.0 - right_rail_ratio)) / 2.0

    return {
        "sub_margin_ratio": round(effective_bottom_ratio, 3),
        "safe_width_ratio": round(usable_width_ratio, 3),
        "x_offset_ratio": round(center_x_norm - 0.5, 3)
    }


# ---------------------------------------------------------------------------
# 4. Interactive Configuration & Main CLI Parser
# ---------------------------------------------------------------------------
def prompt_interactive_config(profiles: Dict[str, Any], auto_save_name: Optional[str] = None) -> Dict[str, Any]:
    print("\n" + "=" * 65)
    print("       AI VIDEO PRODUCTION STUDIO - PROJECT SETUP")
    print("=" * 65)

    # Check if there are existing projects that can be resumed
    existing_projects = find_existing_projects()
    if existing_projects:
        print("\nProject Mode:")
        print("  1) Create a New Explainer Video Project")
        print(f"  2) Resume an Existing Project ({len(existing_projects)} found)")
        mode_choice = input("Choice [1-2, default=1]: ").strip()
        if mode_choice == "2":
            print("\nSelect Project to Resume:")
            for idx, proj_dir in enumerate(existing_projects, 1):
                print(f"  {idx}) {proj_dir.name}")
            sel = input(f"Select project [1-{len(existing_projects)}, default=1]: ").strip()
            try:
                chosen_proj = existing_projects[int(sel) - 1]
            except (ValueError, IndexError):
                chosen_proj = existing_projects[0]
            return {"resume_project_json": str((chosen_proj / "project.json").resolve())}

    topic = input("\nEnter Video Topic/Idea: ").strip()
    while not topic:
        topic = input("Topic cannot be empty. Please enter topic: ").strip()

    while True:
        print("\nSelect a video template:")
        profile_keys = list(profiles.keys())
        for idx, name in enumerate(profile_keys, 1):
            desc = profiles[name].get("description", "")
            print(f"  {idx}) [{name}] {profiles[name].get('width')}x{profiles[name].get('height')} - {desc}")
        manage_idx = len(profile_keys) + 1
        print(f"  {manage_idx}) [M] Manage templates (View / Edit / Clone / Delete)")

        choice_str = input(f"Choice [1-{manage_idx}, default=1]: ").strip().lower()
        if choice_str in ("m", str(manage_idx)):
            profiles = manage_profiles_menu(profiles)
            continue
        if not choice_str:
            choice_idx = 0
        else:
            try:
                choice_idx = int(choice_str) - 1
            except ValueError:
                choice_idx = -1
        if not 0 <= choice_idx < len(profile_keys):
            print("[!] Invalid choice.")
            continue

        chosen_profile_name = profile_keys[choice_idx]
        p_data = profiles[chosen_profile_name]
        print(f" -> Loaded template: '{chosen_profile_name}'")
        width = p_data.get("width", DEFAULT_SIZE[0])
        height = p_data.get("height", DEFAULT_SIZE[1])
        fps = p_data.get("fps", DEFAULT_FPS)
        languages = p_data.get("languages", ["en"])
        music = p_data.get("music", None)
        break

    if auto_save_name:
        save_profile(auto_save_name, {
            "description": input("Brief description for this template: ").strip() or f"Template {width}x{height}",
            "width": width, "height": height, "fps": fps, "languages": languages, "music": music
        })

    return {
        "topic": topic, "aspect_ratio": aspect_of(width, height),
        "width": width, "height": height, "fps": fps, "languages": languages,
        "music": music, "output": "master_explainer.mp4",
        "resume_project_json": None
    }


def load_topic_file(path_str: str) -> Dict[str, Any]:
    """Reads a topic JSON file (see topic.json) and returns {"topic": <text for the planner>, plus any settings it names}.
    File shape: {"topic": "...", "template": "...", "languages": ["en"], "scenes": [{"description": "...", "animation": "flow", "image": "...", "blur": 20, "words": 100}]}
    Only "topic" is required. Each scene needs a "description"; "animation", "image", "blur" and "words" are optional."""
    path = Path(path_str)
    if not path.is_file() and not path.is_absolute():
        path = Path(__file__).resolve().parent / path_str
    if not path.is_file():
        raise SystemExit(f"Error: topic file not found: {path_str}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as e:
        raise SystemExit(f"Error: {path.name} is not valid JSON ({e})")
    topic = str(data.get("topic", "")).strip()
    if not topic:
        raise SystemExit(f"Error: {path.name} needs a \"topic\" field")

    valid = set(load_catalog(quiet=True))
    scenes = data.get("scenes") or []
    lines = [f"{topic.rstrip('. ')}." + (f" Exactly {len(scenes)} scenes." if scenes else "")]
    for i, sc in enumerate(scenes, 1):
        if isinstance(sc, str):
            sc = {"description": sc}
        desc = str(sc.get("description", "")).strip()
        if not desc:
            raise SystemExit(f"Error: scene {i} in {path.name} needs a \"description\"")
        line = f"Scene {i}: {desc}"
        anim = str(sc.get("animation", "")).strip()
        if anim and anim in valid:
            line += f" (use {anim})"
        elif anim:
            print(f"Warning: scene {i} animation '{anim}' is not an animation (available: {', '.join(sorted(valid))}); the planner will choose one.")
        lines.append(line)
        image = str(sc.get("image", "")).strip()
        if image:
            lines.append(f"Image: {image}")
        words = sc.get("words")
        if words not in (None, ""):
            try:
                n_words = int(words)
                if not SCENE_WORDS_MIN <= n_words <= SCENE_WORDS_MAX:
                    raise ValueError
            except (TypeError, ValueError):
                raise SystemExit(f"Error: scene {i} \"words\" must be a whole number between {SCENE_WORDS_MIN} and {SCENE_WORDS_MAX} (about {WORDS_PER_SECOND:g} words per second)")
            lines.append(f"Words: {n_words}")
        blur = sc.get("blur")
        if blur not in (None, False, 0, ""):
            try:
                sigma = DEFAULT_BLUR if blur is True else float(blur)
            except (TypeError, ValueError):
                raise SystemExit(f"Error: scene {i} \"blur\" must be a number such as 20 (or true)")
            lines.append(f"Blur: {sigma:g}")

    settings = {k: data[k] for k in ("template", "languages", "fps", "music") if data.get(k) is not None}
    settings["topic"] = "\n".join(lines)
    print(f"[CLI] Loaded topic file: {path.name} ({len(scenes)} scene{'s' if len(scenes) != 1 else ''})")
    return settings


def get_project_config() -> Dict[str, Any]:
    profiles = load_profiles()

    parser = argparse.ArgumentParser(description="Autonomous Explainer Video Studio")
    parser.add_argument("-R", "--resume", type=str, metavar="PROJECT_DIR_OR_NAME", help="Resume an existing project from its folder name or path")
    parser.add_argument("-T", "--topic-file", type=str, nargs="?", const="", metavar="TOPIC_JSON",
                        help="REQUIRED to make a video: the JSON file with the topic, scenes and settings, e.g. -T topic.json")
    args = parser.parse_args()

    if args.resume:
        proj_json = resolve_resume_path(args.resume)
        return {"resume_project_json": str(proj_json)}

    if not args.topic_file:
        raise SystemExit("Error: no topic file given. The topic, scenes and settings come from a JSON file:\n"
                         "    python .\\main.py -T topic.json\n"
                         "To rebuild an existing project instead:  python .\\main.py -R projects\\<project folder>")
    file_cfg = load_topic_file(args.topic_file)

    base = {}
    template_name = file_cfg.get("template")
    if template_name and template_name not in profiles:
        raise SystemExit(f"Error: template '{template_name}' is not in video_template.json (available: {', '.join(profiles)})")
    if template_name:
        base = profiles[template_name]
        print(f"[CLI] Loaded preset profile: '{template_name}'")

    width = base.get("width", DEFAULT_SIZE[0])
    height = base.get("height", DEFAULT_SIZE[1])
    fps = file_cfg.get("fps") or base.get("fps", DEFAULT_FPS)

    languages = file_cfg.get("languages") or base.get("languages", ["en"])

    music = file_cfg.get("music", base.get("music", None))

    topic = str(file_cfg.get("topic") or "").strip()
    if not topic:
        raise SystemExit(f"Error: {args.topic_file} has no \"topic\" text. Add {{\"topic\": \"...\"}} to the file.")

    return {
        "topic": topic, "aspect_ratio": aspect_of(width, height),
        "width": width, "height": height, "fps": fps, "languages": languages,
        "music": music, "output": "master_explainer.mp4",
        "resume_project_json": None
    }