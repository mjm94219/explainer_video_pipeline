"""
Animation Library Loader
Reads the animation blocks from blocks.html (the animation-meta JSON at its top), builds the catalog text
the LLM planner chooses from, and resolves a scene's chosen animation + parameters.

To add a block: edit blocks.html (see blocks_README.md). No pipeline code needs to change.
"""

import re
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config import EXPLAINER_BLOCKS_HTML

_active_blocks_file: Path = EXPLAINER_BLOCKS_HTML

DEFAULT_ANIMATION = "flow"


def load_catalog(blocks_file: Optional[Path] = None, quiet: bool = False) -> Dict[str, Dict[str, Any]]:
    """Returns {name: {"name", "description", "params", "path", ...}} for every block listed in the active blocks page."""
    blocks_path = Path(blocks_file or _active_blocks_file)
    catalog: Dict[str, Dict[str, Any]] = {}
    if not blocks_path.is_file():
        if not quiet:
            print(f" -> [animations] Blocks page not found: {blocks_path}")
        return catalog

    # HTML animations (rendered by html_engine.py): the metadata sits in <script type="application/json" id="animation-meta">
    for path in [blocks_path]:
        try:
            m = re.search(r'<script[^>]*id="animation-meta"[^>]*>(.*?)</script>', path.read_text(encoding="utf-8"), re.S)
            meta = json.loads(m.group(1)) if m else None
            if not isinstance(meta, dict) or not (str(meta.get("description", "")).strip() or meta.get("blocks")):
                raise ValueError("missing animation-meta JSON with a description (or a blocks list)")
            if "setTime" not in path.read_text(encoding="utf-8"):
                raise ValueError("page has no setTime(t) function")
        except Exception as e:
            if not quiet:
                print(f" -> [animations] Skipping {path.name}: {e}")
            continue
        # A page can offer one animation, or several "blocks" that share the page (the blocks pages): each block becomes
        # its own catalog entry and the block name is passed to the page as the "block" parameter.
        items = meta["blocks"] if isinstance(meta.get("blocks"), list) else [meta]
        for item in items:
            try:
                name = str(item.get("name") or path.stem).strip()
                catalog[name] = {
                    "name": name, "kind": "html",
                    "description": str(item["description"]).strip(),
                    "hidden": bool(item.get("hidden")),
                    "params": {str(k): str(v) for k, v in (item.get("params") or {}).items()},
                    "path": path,
                    "fixed": {"block": name} if isinstance(meta.get("blocks"), list) else {},
                }
            except Exception as e:
                if not quiet:
                    print(f" -> [animations] Skipping a block in {path.name}: {e}")
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
