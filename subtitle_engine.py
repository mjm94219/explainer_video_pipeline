"""
Word-Level Subtitle Alignment & ASS Generation
Runs faster-whisper alignment, formats resolution-aware ASS caption styles,

"""

from pathlib import Path
import torch
from config import WHISPER_MODEL_SIZE, SUBTITLE_FONT_SCALE

def _write_header(f, width: int, height: int):
    font_size = max(28, int(height * SUBTITLE_FONT_SCALE))
    margin_v = int(height * 0.08)
    f.write(f"[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nScaledBorderAndShadow: yes\n\n")
    f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
    f.write(f"Style: Explainer,Segoe UI,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,1,3,2,2,40,40,{margin_v},1\n\n")
    f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")


def _ass_time(x: float) -> str:
    return f"{int(x//3600):01d}:{int((x%3600)//60):02d}:{x%60:05.2f}"


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

    with open(ass_path, "w", encoding="utf-8") as f:
        _write_header(f, width, height)
        for seg in segments:
            if not seg.words:
                continue
            for w in seg.words:
                s_t, e_t = _ass_time(w.start), _ass_time(w.end)
                f.write(f"Dialogue: 0,{s_t},{e_t},Explainer,,0,0,0,,{w.word.strip()}\n")

    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return ass_path