"""
Animation Library Loader
Reads every animation_*.json file next to this script (one file per animation: name, description, params AND how it is drawn);
animator.html is the generic engine that draws them. Builds the catalog text
the LLM planner chooses from, and resolves a scene's chosen animation + parameters.

To add an animation: add a file animation_<name>.json (see animation_README.md). No code needs to change.
"""

import re
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config import EXPLAINER_ANIMATOR_HTML, EXPLAINER_ANIMATION_DIR, ANIMATION_FILE_PATTERN, DEFAULT_ANIMATION

_active_blocks_file: Path = EXPLAINER_ANIMATOR_HTML



def load_catalog(blocks_file: Optional[Path] = None, quiet: bool = False) -> Dict[str, Dict[str, Any]]:
    """Returns {name: {"name", "description", "params", "path", "spec", ...}} for every animation_*.json file."""
    page_path = Path(blocks_file or _active_blocks_file)
    catalog: Dict[str, Dict[str, Any]] = {}
    try:
        if not page_path.is_file():
            raise ValueError(f"engine page not found: {page_path}")
        if "setTime" not in page_path.read_text(encoding="utf-8"):
            raise ValueError("page has no setTime(t) function")
    except Exception as e:
        if not quiet:
            print(f" -> [animations] Skipping {page_path.name}: {e}")
        return catalog

    folder = EXPLAINER_ANIMATION_DIR if page_path == EXPLAINER_ANIMATOR_HTML else page_path.parent
    for json_path in sorted(folder.glob(ANIMATION_FILE_PATTERN)):
        try:
            item = json.loads(json_path.read_text(encoding="utf-8-sig"))
            if not isinstance(item, dict):
                raise ValueError("expected one JSON object")
            name = str(item.get("name") or json_path.stem[len("animation_"):]).strip()
            if not name:
                raise ValueError("no name")
            if not str(item.get("description", "")).strip():
                raise ValueError("needs a \"description\"")
            if not isinstance(item.get("tree"), list):
                raise ValueError("needs a \"tree\" (how to draw it)")
            if name in catalog and not quiet:
                print(f" -> [animations] '{name}' is defined twice; {json_path.name} replaces the earlier one.")
            catalog[name] = {
                "name": name, "kind": "html",
                "description": str(item["description"]).strip(),
                "hidden": bool(item.get("hidden")),
                "params": {str(k): str(v) for k, v in (item.get("params") or {}).items()},
                "path": page_path,
                "spec": {k: v for k, v in item.items() if k in ("setup", "frame", "tree", "heading")},
                "fixed": {},
            }
        except Exception as e:
            if not quiet:
                print(f" -> [animations] Skipping {json_path.name}: {e}")
    return catalog


def catalog_prompt(catalog: Dict[str, Dict[str, Any]]) -> str:
    """Plain-text list of animations and their parameters, for the planner's system prompt."""
    lines = []
    for entry in catalog.values():
        if entry.get("hidden"):          # still usable by name in onscreen_sNN.json, just not offered to the planner
            continue
        lines.append(f"- {entry['name']}: {entry['description']}")
        for key, desc in entry["params"].items():
            lines.append(f"    - {key}: {desc}")
    return "\n".join(lines)


def resolve(name: Optional[str], params: Any, catalog: Dict[str, Dict[str, Any]],
            fallback: str = DEFAULT_ANIMATION) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Maps a scene's requested animation to a catalog entry (falls back to flow, or None if the
    library is empty) and makes sure params is a dict."""
    wanted = str(name or "").strip()
    if wanted and wanted not in catalog:
        print(f" -> [animations] '{wanted}' is not in the library; using '{fallback}' instead.")
    entry = catalog.get(wanted) or catalog.get(fallback)
    return entry, (dict(params) if isinstance(params, dict) else {})
