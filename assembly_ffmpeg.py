"""
FFmpeg NVENC Hardware Compositor
Blends background plates, transparent animation overlays, and word subtitles,
finishing with dynamic two-pass sidechain music ducking.

PATCHED: each scene's length is now driven by its narration audio, not by the
animation overlay or a hard-coded zoompan frame count.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Dict, Any

TAIL_PAD_SEC = 0.3  # small breathing room after the last spoken word


def get_duration(file_path: Path) -> float:
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(file_path)]
    return float(json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True).stdout)["format"]["duration"])


def assemble_video(
    scenes: List[Dict[str, Any]], scenes_dir: Path, output_mp4: Path,
    width: int, height: int, fps: int, bg_music: str = None
) -> Path:
    print(f"\n[6/6] Assembling via FFmpeg NVENC ({width}x{height} @ {fps}fps)...")
    scenes_dir.mkdir(parents=True, exist_ok=True)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    rendered_clips = []

    for sc in scenes:
        sid = sc["scene_id"]
        clip_path = scenes_dir / f"cut_{sid:02d}.mp4"
        ass_clean = sc["ass_path"].replace("\\", "/").replace(":", "\\:")

        # Narration is the source of truth for scene length
        dur = get_duration(Path(sc["audio_path"])) + TAIL_PAD_SEC
        frames = max(1, int(round(dur * fps)))
        print(f" -> Scene {sid}: {dur:.1f}s ({frames} frames)")

        vf = (
            # Single still -> exactly `frames` frames of slow zoom
            f"[0:v]scale={width}x{height},"
            f"zoompan=z='min(zoom+0.0006,1.10)':d={frames}:s={width}x{height}:fps={fps}[bg];"
            # Hold the infographic's last frame (alpha preserved) so it never cuts the scene short
            f"[1:v]format=yuva444p,tpad=stop_mode=clone:stop_duration={dur:.2f}[info];"
            f"[bg][info]overlay=shortest=1[comp];"
            f"[comp]subtitles='{ass_clean}'[vout];"
            # Pad narration with silence up to the full scene length
            f"[2:a]apad[aout]"
        )
        cmd = [
            "ffmpeg", "-y", "-i", sc["bg_path"],          # no -loop 1: zoompan generates the frames
            "-i", sc["info_path"], "-i", sc["audio_path"],
            "-filter_complex", vf, "-map", "[vout]", "-map", "[aout]",
            "-t", f"{dur:.3f}",                            # hard stop at narration length
            "-c:v", "h264_nvenc", "-preset", "p6", "-b:v", "16M",
            "-r", str(fps), "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k",
            str(clip_path)
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        sc["scene_cut_path"] = str(clip_path)
        rendered_clips.append(clip_path)

    concat_txt = scenes_dir / "concat.txt"
    concat_txt.write_text("".join(f"file '{c.resolve()}'\n" for c in rendered_clips), encoding="utf-8")
    rough_cut = scenes_dir / "rough.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c", "copy", str(rough_cut)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )

    if bg_music and Path(bg_music).is_file():
        tot_dur = get_duration(rough_cut)
        fade_out = max(0.0, tot_dur - 3.0)
        af = (
            f"[1:a]volume=0.22,afade=t=in:st=0:d=2:curve=hsin,afade=t=out:st={fade_out:.2f}:d=3:curve=hsin[bg_vol];"
            f"[bg_vol][0:a]sidechaincompress=threshold=0.08:ratio=6:attack=20:release=450[ducked];"
            f"[0:a][ducked]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        subprocess.run([
            "ffmpeg", "-y", "-i", str(rough_cut), "-stream_loop", "-1", "-i", str(bg_music),
            "-filter_complex", af, "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", str(output_mp4)
        ], check=True)
    else:
        shutil.copy(str(rough_cut), str(output_mp4))

    print(f"\n[Success] Master Video Exported: {output_mp4.resolve()} ({get_duration(output_mp4):.1f}s)")
    return output_mp4
