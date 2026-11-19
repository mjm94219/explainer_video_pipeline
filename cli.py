"""
CLI & Preset Management Engine
Handles CLI argument parsing, interactive configuration menus, JSON profile CRUD,
project resume selection, file/format validation, and platform safe-margin calculations.
"""

import json
import copy
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List

from config import RESOLUTION_PRESETS, SUPPORTED_AUDIO_EXTENSIONS, PROJECTS_BASE_DIR

PROFILES_FILE = Path(__file__).resolve().parent / "profiles.json"


# ---------------------------------------------------------------------------
# 1. Profile Disk I/O & Validation
# ---------------------------------------------------------------------------
def load_profiles() -> Dict[str, Any]:
    """Loads saved profiles from profiles.json, falling back to built-in presets if missing."""
    if not PROFILES_FILE.is_file():
        return {
            "Video_Portrait_1080p_9x16": {
                "description": "Vertical 9:16 portrait optimized for YouTube Shorts",
                "aspect_ratio": "9:16", "resolution_tier": "1080p",
                "fps": 60, "languages": ["en"], "music": None
            },
            "Video_Landscape_1080p_16x9": {
                "description": "Standard 16:9 widescreen landscape for desktop YouTube",
                "aspect_ratio": "16:9", "resolution_tier": "1080p",
                "fps": 30, "languages": ["en"], "music": None
            }
        }
    try:
        with open(PROFILES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Failed to parse profiles.json ({e}). Using empty registry.")
        return {}


def save_profiles_file(profiles: Dict[str, Any]) -> bool:
    """Overwrites profiles.json with formatted JSON."""
    try:
        with open(PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(profiles, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error writing to {PROFILES_FILE.name}: {e}")
        return False


def save_profile(name: str, profile_data: Dict[str, Any]) -> bool:
    """Persists a single sanitized profile into profiles.json."""
    profiles = load_profiles()
    clean_entry = {
        "description": profile_data.get("description", f"Preset for {profile_data.get('aspect_ratio')}"),
        "aspect_ratio": profile_data.get("aspect_ratio", "16:9"),
        "resolution_tier": profile_data.get("resolution_tier", "1080p"),
        "fps": profile_data.get("fps", 30),
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
    print(f"  Aspect Ratio:     {p.get('aspect_ratio')}")
    print(f"  Resolution Tier:  {p.get('resolution_tier')}")
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

    aspect_in = input(f"Aspect Ratio (16:9 / 9:16 / 1:1) [{p.get('aspect_ratio')}]: ").strip()
    aspect = aspect_in if aspect_in in ("16:9", "9:16", "1:1") else p.get("aspect_ratio")

    res_in = input(f"Resolution Tier (720p / 1080p / 4k) [{p.get('resolution_tier')}]: ").strip()
    res_tier = res_in if res_in in ("720p", "1080p", "4k") else p.get("resolution_tier")

    fps_in = input(f"FPS (24 / 30 / 60) [{p.get('fps')}]: ").strip()
    fps = int(fps_in) if fps_in in ("24", "30", "60") else p.get("fps")

    current_langs_str = ",".join(p.get("languages", []))
    langs_in = input(f"Languages (comma-separated) [{current_langs_str}]: ").strip()
    langs = [l.strip().lower() for l in langs_in.split(",") if l.strip()] if langs_in else p.get("languages")

    music = prompt_and_validate_audio_path(p.get("music"))

    p.update({
        "description": desc, "aspect_ratio": aspect, "resolution_tier": res_tier,
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

        cur_aspect = cloned_data.get("aspect_ratio", "16:9")
        aspect_in = input(f"Aspect Ratio (16:9 / 9:16 / 1:1) [{cur_aspect}]: ").strip()
        if aspect_in in ("16:9", "9:16", "1:1"):
            cloned_data["aspect_ratio"] = aspect_in

        cur_res = cloned_data.get("resolution_tier", "1080p")
        res_in = input(f"Resolution Tier (720p / 1080p / 4k) [{cur_res}]: ").strip()
        if res_in in ("720p", "1080p", "4k"):
            cloned_data["resolution_tier"] = res_in

        cur_fps = cloned_data.get("fps", 30)
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
        print("\nSelect Configuration Source:")
        profile_keys = list(profiles.keys())
        for idx, name in enumerate(profile_keys, 1):
            desc = profiles[name].get("description", "")
            print(f"  {idx}) Use Profile: [{name}] - {desc}")
        custom_idx = len(profile_keys) + 1
        manage_idx = len(profile_keys) + 2
        print(f"  {custom_idx}) Custom Manual Configuration")
        print(f"  {manage_idx}) [M] Manage Presets (View / Edit / Clone / Delete)")

        choice_str = input(f"Choice [1-{manage_idx}, default=1]: ").strip().lower()

        if choice_str in ("m", str(manage_idx)):
            profiles = manage_profiles_menu(profiles)
            continue

        try:
            choice_idx = int(choice_str) - 1
        except ValueError:
            choice_idx = 0

        if 0 <= choice_idx < len(profile_keys):
            chosen_profile_name = profile_keys[choice_idx]
            p_data = profiles[chosen_profile_name]
            print(f" -> Loaded profile: '{chosen_profile_name}'")

            aspect = p_data.get("aspect_ratio", "16:9")
            res_tier = p_data.get("resolution_tier", "1080p")
            fps = p_data.get("fps", 30)
            languages = p_data.get("languages", ["en"])
            music = p_data.get("music", None)
            break
        else:
            print("\nSelect Aspect Ratio:\n  1) 16:9 (Landscape)\n  2) 9:16 (Vertical)\n  3) 1:1 (Square)")
            ratio_map = {"1": "16:9", "2": "9:16", "3": "1:1"}
            aspect = ratio_map.get(input("Choice [1-3, default=1]: ").strip(), "16:9")

            print(f"\nSelect Resolution for {aspect}:\n  1) 720p\n  2) 1080p\n  3) 4K")
            res_map = {"1": "720p", "2": "1080p", "3": "4k"}
            res_tier = res_map.get(input("Choice [1-3, default=2]: ").strip(), "1080p")

            print("\nSelect Frame Rate:\n  1) 24 fps\n  2) 30 fps\n  3) 60 fps")
            fps_map = {"1": 24, "2": 30, "3": 60}
            fps = fps_map.get(input("Choice [1-3, default=2]: ").strip(), 30)

            langs_raw = input("\nTarget Languages (comma-separated, default='en'): ").strip()
            languages = [l.strip().lower() for l in langs_raw.split(",")] if langs_raw else ["en"]

            music = prompt_and_validate_audio_path(None)

            target_save_name = auto_save_name
            if not target_save_name:
                prompt_save = input("\nSave this configuration as a reusable preset in profiles.json? [y/N]: ").strip().lower()
                if prompt_save in ("y", "yes"):
                    target_save_name = input("Enter a name for this preset: ").strip()

            if target_save_name:
                desc = input("Brief description for this preset: ").strip() or f"Custom preset for {aspect}"
                save_payload = {
                    "description": desc, "aspect_ratio": aspect, "resolution_tier": res_tier,
                    "fps": fps, "languages": languages, "music": music
                }
                save_profile(target_save_name, save_payload)

            break

    width, height = RESOLUTION_PRESETS[aspect][res_tier]
    return {
        "topic": topic, "aspect_ratio": aspect, "resolution_tier": res_tier,
        "width": width, "height": height, "fps": fps, "languages": languages,
        "music": music, "output": "master_explainer.mp4",
        "resume_project_json": None
    }


def get_project_config() -> Dict[str, Any]:
    profiles = load_profiles()

    parser = argparse.ArgumentParser(description="Autonomous Explainer Video Studio")
    parser.add_argument("-R", "--resume", type=str, metavar="PROJECT_DIR_OR_NAME", help="Resume an existing project from its folder name or path")
    parser.add_argument("-t", "--topic", type=str, help="Video topic or concept")
    parser.add_argument("-p", "--profile", type=str, choices=list(profiles.keys()), help="Saved preset profile from profiles.json")
    parser.add_argument("-a", "--aspect", choices=["16:9", "9:16", "1:1"], help="Aspect ratio override")
    parser.add_argument("-r", "--resolution", choices=["720p", "1080p", "4k"], help="Resolution tier override")
    parser.add_argument("-f", "--fps", type=int, choices=[24, 30, 60], help="Frame rate override")
    parser.add_argument("-l", "--languages", type=str, help="Comma-separated language codes, e.g. 'en'")
    parser.add_argument("-m", "--music", type=str, help="Background music audio file override")
    parser.add_argument("-o", "--output", type=str, default="master_explainer.mp4", help="Output MP4 file")
    parser.add_argument("--manage-profiles", action="store_true", help="Open the preset profile manager directly")
    parser.add_argument(
        "--save-profile",
        nargs="?",
        const="__PROMPT__",
        default=None,
        metavar="PROFILE_NAME",
        help="Save current parameters into profiles.json under this preset name"
    )
    args = parser.parse_args()

    if args.manage_profiles:
        manage_profiles_menu(profiles)
        profiles = load_profiles()

    if args.resume:
        proj_json = resolve_resume_path(args.resume)
        return {"resume_project_json": str(proj_json)}

    if not args.topic and not args.profile:
        auto_save = None if args.save_profile == "__PROMPT__" else args.save_profile
        return prompt_interactive_config(profiles, auto_save_name=auto_save)

    base = {}
    if args.profile and args.profile in profiles:
        base = profiles[args.profile]
        print(f"[CLI] Loaded preset profile: '{args.profile}'")

    aspect = args.aspect or base.get("aspect_ratio", "16:9")
    res_tier = args.resolution or base.get("resolution_tier", "1080p")
    fps = args.fps or base.get("fps", 30)

    if args.languages:
        languages = [l.strip().lower() for l in args.languages.split(",") if l.strip()]
    else:
        languages = base.get("languages", ["en"])

    music = args.music if args.music is not None else base.get("music", None)

    if args.save_profile:
        save_name = args.save_profile
        if save_name == "__PROMPT__":
            save_name = input("\nEnter name for this new preset: ").strip()
        if save_name:
            desc = input(f"Description for preset '{save_name}': ").strip() or f"Custom preset for {aspect}"
            save_payload = {
                "description": desc, "aspect_ratio": aspect, "resolution_tier": res_tier,
                "fps": fps, "languages": languages, "music": music
            }
            save_profile(save_name, save_payload)

    topic = args.topic
    if not topic:
        topic = input("\nEnter Video Topic/Idea: ").strip()
        while not topic:
            topic = input("Topic cannot be empty: ").strip()

    width, height = RESOLUTION_PRESETS[aspect][res_tier]
    return {
        "topic": topic, "aspect_ratio": aspect, "resolution_tier": res_tier,
        "width": width, "height": height, "fps": fps, "languages": languages,
        "music": music, "output": args.output,
        "resume_project_json": None
    }