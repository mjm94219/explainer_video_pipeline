"""
Word-Level Subtitle Alignment & ASS Generation
Runs faster-whisper alignment, formats resolution-aware ASS caption styles,

"""

from pathlib import Path
import torch
import re
from config import WHISPER_MODEL_SIZE, SUBTITLE_FONT_SCALE, load_caption_fixes

def _write_header(f, width: int, height: int):
    font_size = max(28, int(height * SUBTITLE_FONT_SCALE))
    margin_v = int(height * 0.08)
    f.write(f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nScaledBorderAndShadow: yes\n\n")
    f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
    f.write(f"Style: Explainer,Segoe UI,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,1,3,2,2,40,40,{margin_v},1\n\n")
    f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")


def _ass_time(x: float) -> str:
    return f"{int(x//3600):01d}:{int((x%3600)//60):02d}:{x%60:05.2f}"


def _apply_caption_fixes(words: list, fixes: dict) -> list:
    """words = [(start, end, text), ...] as heard. Replaces a word, or a run of words, listed in caption-en.json
    ("comfy ui": "ComfyUI") with the right spelling; a run becomes one caption word spanning the same time."""
    if not fixes:
        return words
    parts = [re.match(r"^(\W*)(.*?)(\W*)$", w[2].strip()) for w in words]
    longest = max(len(k.split()) for k in fixes)
    out, i = [], 0
    while i < len(words):
        for n in range(min(longest, len(words) - i), 0, -1):
            key = " ".join((parts[j].group(2) or words[j][2].strip()).lower() for j in range(i, i + n))   # a lone symbol such as "%" counts as a word
            if key in fixes:
                text = parts[i].group(1) + fixes[key] + parts[i + n - 1].group(3)
                out.append((words[i][0], words[i + n - 1][1], text))
                i += n
                break
        else:
            out.append((words[i][0], words[i][1], words[i][2].strip()))
            i += 1
    # a file extension heard as its own word (".json", ".py") is joined onto the word before it: "project" + ".json" -> "project.json"
    joined = []
    for s0, e0, text in out:
        if joined and len(text) > 1 and text[0] == "." and text[1].isalnum() and joined[-1][2][-1:].isalnum():
            joined[-1] = (joined[-1][0], e0, joined[-1][2] + text)
        else:
            joined.append((s0, e0, text))
    return joined


def transcribe_and_align(audio_path: Path, ass_path: Path, lang: str, width: int, height: int) -> Path:
    from faster_whisper import WhisperModel
    print(f" -> Word alignment via faster-whisper [{lang}]...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    comp = "float16" if device == "cuda" else "int8"
    model = WhisperModel(WHISPER_MODEL_SIZE, device=device, compute_type=comp)

    segments, _ = model.transcribe(
        str(audio_path), language=lang,
        condition_on_previous_text=False, word_timestamps=True, temperature=0.0
    )

    heard = [(w.start, w.end, w.word) for seg in segments if seg.words for w in seg.words]
    with open(ass_path, "w", encoding="utf-8") as f:
        _write_header(f, width, height)
        for start, end, text in _apply_caption_fixes(heard, load_caption_fixes()):
            f.write(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Explainer,,0,0,0,,{text}\n")

    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return ass_path