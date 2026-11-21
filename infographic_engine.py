"""
Renders a scene's animation block (drawn by animator.html from the animation_*.json files) to a transparent ProRes 4444 .mov overlay
through Playwright + FFmpeg (html_engine.py).
"""

from pathlib import Path

import animation_library
import html_engine


def render_animation(scene_id: int, graphics_dir: Path, width: int, height: int, fps: int,
                     duration: float, safe_w: float, sub_margin: float,
                     heading: str = "", key_points: list = None,
                     animation: str = "", anim_params: dict = None) -> Path:
    catalog = animation_library.load_catalog(quiet=True)
    entry, params = animation_library.resolve(animation, anim_params, catalog)
    if not entry:
        raise RuntimeError(f"No animation blocks found in {animation_library._active_blocks_file}")
    params = dict(params)
    if heading:
        params["heading"] = heading
    if key_points and not params.get("labels") and entry["name"] == "flow":
        params["labels"] = list(key_points)
    dur = duration if duration > 0 else 12.0
    payload = dict(params)
    payload.update(entry.get("fixed") or {})
    payload["spec"] = entry.get("spec") or {}          # how to draw it (from the animation_*.json files)
    payload.update({"duration": round(dur, 2), "vertical": height > width,
                    "sub_margin": float(sub_margin), "safe_w": float(safe_w)})
    target = graphics_dir / f"infographic_{scene_id:02d}.mov"
    print(f" -> Scene {scene_id}: animation '{entry['name']}'")
    if not html_engine.render_html_animation(entry["path"], payload, target, width, height, fps, dur):
        raise RuntimeError(f"Animation render failed for scene {scene_id} ('{entry['name']}'). "
                           "Check that Playwright is installed: python -m pip install playwright")
    print(f" -> Infographic rendered: {target.name} | '{entry['name']}' {dur:.1f}s")
    return target
