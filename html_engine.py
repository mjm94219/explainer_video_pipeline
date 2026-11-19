"""
HTML animation renderer (Playwright + FFmpeg)
Renders a blocks page to a transparent ProRes 4444 .mov overlay.

How it works: the page exposes setTime(t). For every frame we call setTime(frame / fps), take a transparent PNG
screenshot, and stream the PNGs into FFmpeg. Frames are exact (no real-time capture), so timing never drifts.

Browser: tries your installed Edge, then Chrome (already trusted by Windows), then Playwright's own Chromium.
Setup once:  python -m pip install playwright      (and, only if you have no Edge/Chrome:  python -m playwright install chromium)
"""

import json
import subprocess
from pathlib import Path
from typing import Optional


def _launch(p):
    last = None
    for kwargs in ({"channel": "msedge"}, {"channel": "chrome"}, {}):
        try:
            return p.chromium.launch(**kwargs)
        except Exception as e:                      # not installed / blocked: try the next one
            last = e
    raise RuntimeError(f"no usable browser for Playwright ({last})")


def render_html_animation(html_path: Path, params: dict, dest_mov: Path, width: int, height: int,
                          fps: int, duration: float, preview_png: Optional[Path] = None,
                          preview_time: float = 5.0) -> bool:
    """Returns True when dest_mov was written. If preview_png is given, saves one frame at preview_time instead of a video."""
    from playwright.sync_api import sync_playwright

    payload = json.dumps(params, ensure_ascii=False)
    total = max(1, int(round(duration * fps)))
    ff = None
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.add_init_script(f"window.__PARAMS__ = {payload};")
            page.goto(Path(html_path).resolve().as_uri())
            page.evaluate("document.fonts.ready")
            if not page.evaluate("typeof window.setTime === 'function'"):
                raise RuntimeError("page has no setTime(t) function")

            if preview_png:
                page.evaluate(f"setTime({preview_time})")
                page.screenshot(path=str(preview_png), omit_background=True)
                browser.close()
                return True

            ff = subprocess.Popen(
                ["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-",
                 "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-vendor", "apl0", str(dest_mov)],
                stdin=subprocess.PIPE)
            for i in range(total):
                page.evaluate(f"setTime({i / fps:.4f})")
                ff.stdin.write(page.screenshot(omit_background=True, type="png"))
            ff.stdin.close()
            ff.wait()
            browser.close()
        return ff.returncode == 0 and dest_mov.is_file() and dest_mov.stat().st_size > 0
    except Exception as e:
        print(f" -> [html_engine] render failed: {e}")
        if ff and ff.stdin and not ff.stdin.closed:
            try:
                ff.stdin.close()
            except Exception:
                pass
        return False
