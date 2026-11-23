"""
Writes an .srt subtitle file for the finished video, so it can be uploaded to YouTube as closed captions.
The burned-in subtitles are word by word (Subtitles\\captions_NN.ass); here the words are grouped into short readable lines.
"""

import re
from pathlib import Path
from typing import List, Tuple

_DIALOGUE = re.compile(r"^Dialogue:\s*\d+,(\d+):(\d+):(\d+)\.(\d+),(\d+):(\d+):(\d+)\.(\d+),[^,]*,[^,]*,\d+,\d+,\d+,[^,]*,(.*)$")


def _secs(h, m, s, cs) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / (10 ** len(cs))


def read_words(ass_path) -> List[Tuple[float, float, str]]:
    """[(start, end, word), ...] from one scene's captions_NN.ass."""
    words = []
    for line in Path(ass_path).read_text(encoding="utf-8-sig").splitlines():
        m = _DIALOGUE.match(line)
        if m:
            text = m.group(9).strip()
            if text:
                words.append((_secs(*m.group(1, 2, 3, 4)), _secs(*m.group(5, 6, 7, 8)), text))
    return words


def _stamp(t: float) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def group_words(words: List[Tuple[float, float, str]], max_words: int = 9, max_secs: float = 4.0, gap: float = 0.7):
    """Groups words into lines: a line ends at . ? ! (or a comma once it has 5 words), a pause, 9 words or 4 seconds."""
    lines, cur = [], []
    for w in words:
        if cur and (w[0] - cur[-1][1] > gap or len(cur) >= max_words or w[1] - cur[0][0] > max_secs):
            lines.append(cur)
            cur = []
        cur.append(w)
        last = w[2][-1:]
        if last in ".?!" or (last in ",;:" and len(cur) >= 5):
            lines.append(cur)
            cur = []
    if cur:
        lines.append(cur)
    return lines


def write_srt(tracks: List[Tuple[float, object]], srt_path) -> int:
    """tracks = [(seconds into the final video where a scene starts, its captions_NN.ass path or None), ...]. Returns the number of lines."""
    n = 0
    out = []
    for offset, ass in tracks:
        if not ass or not Path(ass).is_file():
            continue
        for line in group_words(read_words(ass)):
            n += 1
            text = " ".join(w[2] for w in line)
            out.append(f"{n}\n{_stamp(offset + line[0][0])} --> {_stamp(offset + line[-1][1])}\n{text}\n")
    Path(srt_path).write_text("\n".join(out), encoding="utf-8")
    return n
