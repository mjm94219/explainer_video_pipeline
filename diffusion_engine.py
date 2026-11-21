"""
ComfyUI API Client
Dispatches background diffusion generations matched dynamically to resolution and aspect ratio,
with automatic FFmpeg dark-slate fallback if no checkpoint is loaded.

PATCHED: longer submit timeout, bounded polling, and cancellation of the queued
job when we give up (so abandoned prompts don't pile up in ComfyUI's queue).
"""

import time
import json
import uuid
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
import numpy as np
import config
from config import COMFY_URL

SUBMIT_TIMEOUT = config.COMFY_SUBMIT_TIMEOUT
POLL_TIMEOUT = config.COMFY_POLL_TIMEOUT
RENDER_DEADLINE = config.COMFY_RENDER_DEADLINE

# Model profiles. Pick one with IMAGE_MODEL in settings.json.
#   gen_mp: render at about this many megapixels (same aspect ratio), then scale to the target size.
#           None = render directly at the target size.
IMAGE_PROFILES = {
    "lightning": {
        "ckpt": "sdxl_lightning_4step.safetensors",
        "steps": 4, "cfg": 1.0, "sampler": "euler", "scheduler": "sgm_uniform",
        "negative": "blurry, low quality, distorted, text watermark, ugly",
        "suffix": "", "gen_mp": None,
    },
    "sdxl_base": {
        "ckpt": "sd_xl_base_1.0.safetensors",
        "steps": 28, "cfg": 6.5, "sampler": "dpmpp_2m", "scheduler": "karras",
        "negative": ("cartoon, illustration, drawing, 3d render, clutter, tangled wires, messy cables, text, "
                     "watermark, logo, signature, blurry, low quality, distorted, deformed, extra objects"),
        "suffix": ", photograph, sharp focus, natural soft lighting, clean uncluttered composition",
        "gen_mp": 1.0,
    },
}


def _gen_size(width: int, height: int, megapixels: float):
    """Size SDXL renders at: about `megapixels` MP, same aspect ratio, multiples of 64."""
    scale = (megapixels * 1_048_576 / (width * height)) ** 0.5
    gw = max(512, int(round(width * scale / 64)) * 64)
    gh = max(512, int(round(height * scale / 64)) * 64)
    return gw, gh


COMFY_WORKFLOW = {
    "3": {"class_type": "KSampler", "inputs": {"cfg": 1.0, "denoise": 1.0, "latent_image": ["5", 0], "model": ["4", 0], "negative": ["7", 0], "positive": ["6", 0], "sampler_name": "euler", "scheduler": "sgm_uniform", "seed": 42, "steps": 4}},
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdxl_lightning_4step.safetensors"}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"batch_size": 1, "height": 1080, "width": 1920}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": ""}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": "blurry, low quality, distorted, text watermark, ugly"}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "aivideo_frame", "images": ["8", 0]}}
}


def _post_json(path: str, payload: dict, timeout: float):
    req = urllib.request.Request(
        f"{COMFY_URL}{path}", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _cancel_prompt(prompt_id: str):
    """Best-effort removal of an abandoned job from the queue (and interrupt it if running)."""
    try:
        _post_json("/queue", {"delete": [prompt_id]}, timeout=10).close()
    except Exception:
        pass
    try:
        _post_json("/interrupt", {}, timeout=10).close()
    except Exception:
        pass


def render_background_plate(prompt_text: str, dest_png: Path, width: int, height: int) -> Path:
    print(f" -> Queueing ComfyUI background ({width}x{height})...")
    prefix = f"bg_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    name = config.IMAGE_MODEL
    prof = IMAGE_PROFILES.get(name)
    if prof is None:
        print(f" -> [Unknown IMAGE_MODEL '{name}', using 'lightning']")
        prof = IMAGE_PROFILES["lightning"]
    workflow = json.loads(json.dumps(COMFY_WORKFLOW))
    workflow["4"]["inputs"]["ckpt_name"] = prof["ckpt"]
    ks = workflow["3"]["inputs"]
    ks.update(steps=prof["steps"], cfg=prof["cfg"], sampler_name=prof["sampler"], scheduler=prof["scheduler"])
    workflow["7"]["inputs"]["text"] = prof["negative"]
    gw, gh = (width, height) if not prof["gen_mp"] else _gen_size(width, height, prof["gen_mp"])
    workflow["5"]["inputs"]["width"] = gw
    workflow["5"]["inputs"]["height"] = gh
    workflow["6"]["inputs"]["text"] = prompt_text + prof["suffix"]
    workflow["3"]["inputs"]["seed"] = int(np.random.randint(1, 99999999))
    if (gw, gh) != (width, height):
        # scale the render up/down to the exact canvas size
        workflow["10"] = {"class_type": "ImageScale", "inputs": {
            "image": ["8", 0], "upscale_method": "lanczos", "width": width, "height": height, "crop": "center"}}
        workflow["9"]["inputs"]["images"] = ["10", 0]
    print(f" -> Image model: {name} ({prof['steps']} steps, render {gw}x{gh})")
    workflow["9"]["inputs"]["filename_prefix"] = prefix

    payload = {"prompt": workflow, "client_id": str(uuid.uuid4())}
    prompt_id = None
    try:
        with _post_json("/prompt", payload, timeout=SUBMIT_TIMEOUT) as resp:
            prompt_id = json.loads(resp.read())["prompt_id"]

        deadline = time.time() + RENDER_DEADLINE
        while True:
            if time.time() > deadline:
                raise TimeoutError(f"ComfyUI render exceeded {RENDER_DEADLINE}s")
            time.sleep(1.5)
            with urllib.request.urlopen(f"{COMFY_URL}/history/{prompt_id}", timeout=POLL_TIMEOUT) as h_resp:
                hist = json.loads(h_resp.read())
            if prompt_id in hist:
                img_info = hist[prompt_id]["outputs"]["9"]["images"][0]
                filename = img_info["filename"]
                subfolder = img_info.get("subfolder", "")
                break

        query = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": "output"})
        urllib.request.urlretrieve(f"{COMFY_URL}/view?{query}", str(dest_png))
        print(f" -> Background plate rendered: {dest_png.name}")
    except Exception as e:
        if prompt_id:
            _cancel_prompt(prompt_id)
        print(f" -> [ComfyUI Error/Skipped: {e}] Generating fallback dark slate plate via FFmpeg...")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x12161f:s={width}x{height}:d=1",
            "-frames:v", "1", str(dest_png)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return dest_png
