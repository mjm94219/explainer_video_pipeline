"""
LLM Director & Script Decomposition
Calls Ollama (model set by LLM_MODEL in settings.json) to build structured JSON scene manifests with VRAM auto-eviction.

PATCHED: honors the scene count requested in the topic (default 4-6), asks for
narration of the length set by NARRATION_WORDS in settings.json (a scene can override it with a Words: line), and gives the model enough
context/output budget to avoid truncated JSON.
"""

import json
import re
import requests
from typing import Dict, Any
import animation_library as animlib
from config import OLLAMA_URL, LLM_MODEL, OLLAMA_NUM_CTX, OLLAMA_NUM_PREDICT, OLLAMA_THINK, NARRATION_WORDS, WORDS_PER_SECOND, DEFAULT_ANIMATION




def _topic_image_prompts(topic):
    """Pull per-scene 'Image: ...' lines out of the topic text -> {scene_number: prompt}.
    A line is attached to the most recent 'Scene N' mentioned before it (same line or later lines)."""
    found, current = {}, None
    for line in str(topic).splitlines():
        m = re.search(r"\bscene\s*(\d+)", line, re.I)
        if m:
            current = int(m.group(1))
        im = re.search(r"\bimage\s*:\s*(.+)", line, re.I)
        if im and current is not None:
            found[current] = im.group(1).strip().strip(" \"'\u201c\u201d.")
    return found


def _topic_blurs(topic):
    """Pull per-scene 'Blur: N' lines out of the topic text -> {scene_number: sigma}."""
    found, current = {}, None
    for line in str(topic).splitlines():
        m = re.search(r"\bscene\s*(\d+)", line, re.I)
        if m:
            current = int(m.group(1))
        bm = re.match(r"\s*blur\s*:\s*([0-9.]+)", line, re.I)
        if bm and current is not None:
            found[current] = float(bm.group(1))
    return found


def _named_animations(topic, catalog):
    """If EVERY 'Scene N: ... (use name)' line in the topic names a known animation, returns that set of names
    (the planner then only needs those). Otherwise None: some scene is left for the planner to choose from the full list."""
    names, scenes = [], 0
    for line in str(topic).splitlines():
        if re.match(r"\s*scene\s*\d+\b", line, re.I):
            scenes += 1
            m = re.search(r"\(use\s+([A-Za-z0-9_]+)\)", line)
            if not m or m.group(1) not in catalog:
                return None
            names.append(m.group(1))
    return set(names) if scenes and len(names) == scenes else None


def _topic_words(topic):
    """Pull per-scene 'Words: N' lines out of the topic text -> {scene_number: target word count}."""
    found, current = {}, None
    for line in str(topic).splitlines():
        m = re.search(r"\bscene\s*(\d+)", line, re.I)
        if m:
            current = int(m.group(1))
        wm = re.match(r"\s*words\s*:\s*(\d+)", line, re.I)
        if wm and current is not None:
            found[current] = int(wm.group(1))
    return found


def _topic_animations(topic):
    """Pull the '(use name)' of each 'Scene N: ...' line out of the topic text -> {scene_number: animation name}."""
    found = {}
    for line in str(topic).splitlines():
        m = re.match(r"\s*scene\s*(\d+)\b", line, re.I)
        u = re.search(r"\(use\s+([A-Za-z0-9_]+)\)", line)
        if m and u:
            found[int(m.group(1))] = u.group(1)
    return found


def _fill_params(scene, entry):
    """Asks the model for the parameters of one animation for one scene (used when the model ignored the animation the topic named)."""
    spec = "\n".join(f"- {k}: {v}" for k, v in entry["params"].items())
    prompt = (f"Fill in the parameters of the animation '{entry['name']}' for one scene of an explainer video.\n"
              f"What the animation shows: {entry['description']}\n"
              f"Scene heading: {scene.get('heading', '')}\nNarration: {scene.get('narration', '')}\n\n"
              f"Parameters to fill in:\n{spec}\n\n"
              "Return ONLY a JSON object whose keys are exactly those parameter names. Keep every text short and in plain English.")
    payload = {"model": LLM_MODEL, "prompt": prompt, "format": "json", "stream": False,
               "options": {"num_ctx": OLLAMA_NUM_CTX, "num_predict": 1024}, "keep_alive": 0}
    if OLLAMA_THINK is not None:
        payload["think"] = OLLAMA_THINK
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=300)
        resp.raise_for_status()
        obj = json.loads(resp.json()["response"])
        return obj if isinstance(obj, dict) else {}
    except Exception as e:
        print(f"    [warning] could not fill the parameters of '{entry['name']}' ({type(e).__name__}); using its defaults")
        return {}


def _language_problems(manifest):
    """Spot narration that is empty or not written in English letters."""
    problems = []
    for i, sc in enumerate(manifest.get("scenes", []), 1):
        letters = [c for c in str(sc.get("narration", "")) if c.isalpha()]
        if not letters:
            problems.append(f"scene {i} has no narration")
        elif len([c for c in letters if ord(c) > 0x024F]) > 0.05 * len(letters):
            problems.append(f"scene {i} is not English")
    return problems


def _english_title(title, topic):
    """The title becomes the project folder name, so keep it plain Latin text."""
    t = str(title or "").strip()
    if t and t.isascii():
        return t
    words = re.findall(r"[A-Za-z0-9]+", str(topic).split(".")[0])[:6]
    return " ".join(words) or "Explainer Video"


def generate_script_manifest(config: Dict[str, Any]) -> Dict[str, Any]:
    print(f"\n[1/6] Planning scenes via Ollama ({LLM_MODEL})...")
    allowed_langs = ", ".join(f"'{l}'" for l in config["languages"])

    catalog = animlib.load_catalog(quiet=True)
    offered = catalog                                   # what the planner is told about
    named = _named_animations(config["topic"], catalog)
    if named:                                           # every scene already names its animation: no need to list the others
        offered = {k: dict(v, hidden=False) for k, v in catalog.items() if k in named}
        print(f"    Every scene names its animation; the planner is only told about: {', '.join(sorted(named))}")
    if catalog:
        scene_fields = (
            "5. heading (a 2 to 4 word on-screen title for the scene)\n"
            "6. animation (the name of the best-fitting animation from the list below; use " + DEFAULT_ANIMATION + " if none fits. "
            "If the user's topic names an animation for a scene, use that one.)\n"
            "7. animation_params (an object with the parameters that animation needs, filled in for this scene)\n\n"
            "Available animations:\n" + animlib.catalog_prompt(offered) + "\n"
        )
        scene_schema = (
            '      "heading": "...",\n'
            '      "animation": "<one name from the list above>",\n'
            '      "animation_params": {"<parameter name>": "<value for this scene>"}\n'
        )
    else:
        scene_fields = (
            "5. heading (a 2 to 4 word on-screen title for the scene)\n"
            "6. key_points (a list of 3 or 4 on-screen labels, each 1 to 3 words, in the order the narration mentions them)\n"
        )
        scene_schema = '      "heading": "...",\n      "key_points": ["...", "...", "..."]\n'

    orientation = "Landscape"
    if config["aspect_ratio"] == "9:16":
        orientation = "Vertical portrait. Stack objects top-to-bottom along the Y-axis."
    elif config["aspect_ratio"] == "1:1":
        orientation = "Square. Keep objects compact and centered."

    lang_rules = (
        "LANGUAGE RULES: write everything in plain English. "
        "Never mention animation names, file names or the word 'scene' in the narration. "
        "The JSON keys, the \"title\", every \"visual_prompt\" and every animation name must be in plain English.\n"
    )
    words_rule = f"{str(NARRATION_WORDS).strip()} words"
    nums = [int(x) for x in re.findall(r"\d+", str(NARRATION_WORDS))] or [50, 70]
    secs_rule = f"about {round(min(nums) / WORDS_PER_SECOND)} to {round(max(nums) / WORDS_PER_SECOND)} seconds"

    system_prompt = f"""You are an elite technical explainer video director and animation engineer.
Deconstruct the topic into structured scenes. If the user requests a specific number of scenes, produce EXACTLY that many. Otherwise use 4 to 6 scenes.
Target Canvas: {config['width']}x{config['height']} ({config['aspect_ratio']}, {orientation}).
Allowed Languages: {allowed_langs}.
{lang_rules}
For each scene provide:
1. scene_id (int, starting at 1)
2. lang (one of: {allowed_langs})
3. narration: {words_rule} of spoken text ({secs_rule}). Write clear, flowing explanatory paragraphs, never a single short sentence. If the topic gives a \"Words: N\" line for a scene, write about N words (between N-10 and N+10) for that scene instead. 
4. visual_prompt (descriptive background diffusion prompt, 4k digital art, clean, subtle colors). Describe ONE clear scene with 2 to 4 concrete, nameable objects and their layout (for example "a white wall outlet with a power cord plugged in, the cord running to a laptop on a desk"). Avoid abstract words like "electricity" or "flow" and avoid clutter, tangled wires and text. If the topic gives an "Image:" line for a scene, use that text verbatim as the visual_prompt for that scene.
{scene_fields}
OUTPUT STRICT JSON ONLY:
{{
  "title": "Short title",
  "scenes": [
    {{
      "scene_id": 1,
      "lang": "{config['languages'][0]}",
      "narration": "...",
      "visual_prompt": "...",
{scene_schema}    }}
  ]
}}"""
    payload = {
        "model": LLM_MODEL,
        "prompt": f"Topic: {config['topic']}\nGenerate the production manifest.",
        "system": system_prompt,
        "format": "json",
        "stream": False,
        "options": {
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": OLLAMA_NUM_PREDICT
        },
        "keep_alive": 0  # Evicts LLM weights from VRAM immediately
    }
    if OLLAMA_THINK is not None:
        payload["think"] = OLLAMA_THINK          # False: no hidden reasoning text, so "response" holds only the JSON
    manifest = None
    for attempt in range(1, 4):
        resp = requests.post(f"{OLLAMA_URL}/api/generate", json=payload, timeout=600)
        resp.raise_for_status()
        manifest = json.loads(resp.json()["response"])
        problems = _language_problems(manifest)
        if not problems:
            break
        print(f" -> Attempt {attempt}: the plan is not in English ({'; '.join(problems)}).")
        if attempt < 3:
            print(" -> Asking the model again...")
        else:
            print(" -> [WARNING] Giving up after 3 attempts; check the narration in project.json before rendering.")

    manifest["title"] = _english_title(manifest.get("title"), config["topic"])

    scenes = manifest.get("scenes", [])
    print(f" -> Generated {len(scenes)} scenes.")
    forced = _topic_image_prompts(config["topic"])
    blurs = _topic_blurs(config["topic"])
    wanted_words = _topic_words(config["topic"])
    named_by_topic = _topic_animations(config["topic"])
    for i, sc in enumerate(scenes, 1):
        num = sc.get("scene_id", i)
        try:
            num = int(num)
        except (TypeError, ValueError):
            num = i
        if num in forced:
            sc["visual_prompt"] = forced[num] + ", 4k digital art, clean, uncluttered, subtle colors"
            print(f"    Scene {num}: image prompt taken from the topic")
        if num in blurs:
            sc["background_blur"] = blurs[num]
            print(f"    Scene {num}: background blur {blurs[num]:g}")
    for sc in scenes:
        words = len(str(sc.get("narration", "")).split())
        extra = ""
        if catalog:
            name = str(sc.get("animation", "")).strip()
            try:
                scene_no = int(sc.get("scene_id"))
            except (TypeError, ValueError):
                scene_no = 0
            asked = named_by_topic.get(scene_no)
            if asked and asked in catalog and asked != name:       # the model ignored "(use ...)": do what the topic says
                print(f"    Scene {scene_no}: the model chose '{name}' but the topic says '{asked}'; using '{asked}'")
                name = asked
                sc["animation"] = asked
                sc["animation_params"] = _fill_params(sc, catalog[asked]) if catalog[asked]["params"] else {}
            if name not in catalog:
                name = animlib.DEFAULT_ANIMATION if animlib.DEFAULT_ANIMATION in catalog else next(iter(catalog))
            sc["animation"] = name
            if not isinstance(sc.get("animation_params"), dict):
                sc["animation_params"] = {}
            if sc.get("key_points") and "labels" in catalog[name]["params"] and not sc["animation_params"].get("labels"):
                sc["animation_params"]["labels"] = sc["key_points"]
            extra = f", animation: {name}"
        target = wanted_words.get(int(sc.get("scene_id") or 0))
        note = ""
        if target and abs(words - target) > max(15, 0.3 * target):
            note = f"  [WARNING: asked for about {target} words; edit Scripts\\narration_*.txt to adjust]"
        print(f"    Scene {sc.get('scene_id')}: {words} narration words (~{words / WORDS_PER_SECOND:.0f}s){extra}{note}")
    return manifest
