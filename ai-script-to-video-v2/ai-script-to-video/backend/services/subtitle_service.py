"""
subtitle_service.py
Generates SRT subtitles from narration text and burns them into video using FFmpeg.
Two presets: minimal and cinematic.
"""
import re
import subprocess
from pathlib import Path
from db import get_db, execute


SUBTITLE_PRESETS = {
    "minimal": {
        "FontName":    "Arial",
        "FontSize":    "22",
        "PrimaryColour": "&H00FFFFFF",
        "OutlineColour": "&H00000000",
        "Outline":     "1",
        "Shadow":      "0",
        "Alignment":   "2",        # bottom center
        "MarginV":     "30",
    },
    "cinematic": {
        "FontName":    "Georgia",
        "FontSize":    "26",
        "PrimaryColour": "&H00FFFFFF",
        "OutlineColour": "&H00000000",
        "BackColour":  "&H80000000",
        "Outline":     "0",
        "Shadow":      "1",
        "Alignment":   "2",
        "MarginV":     "50",
        "Bold":        "1",
    }
}


def generate_srt_from_text(text: str, total_duration: float) -> str:
    """
    Split narration text into timed SRT subtitle blocks.
    Distributes lines evenly across the video duration.
    """
    # Split into sentences / natural breaks
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return ""

    # Break long sentences into max-7-word chunks
    chunks = []
    for sentence in sentences:
        words = sentence.split()
        for i in range(0, len(words), 7):
            chunks.append(" ".join(words[i:i+7]))

    if not chunks:
        return ""

    duration_per_chunk = total_duration / len(chunks)
    srt_lines = []

    for i, chunk in enumerate(chunks):
        start = i * duration_per_chunk
        end   = start + duration_per_chunk - 0.1

        srt_lines.append(str(i + 1))
        srt_lines.append(f"{_fmt_time(start)} --> {_fmt_time(end)}")
        srt_lines.append(chunk)
        srt_lines.append("")

    return "\n".join(srt_lines)


def _fmt_time(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def save_srt_file(srt_content: str, path: Path) -> Path:
    path.write_text(srt_content, encoding="utf-8")
    return path


def burn_subtitles(input_video: str, srt_path: str, output_video: str, preset: str = "minimal") -> str:
    """
    Burn SRT subtitles into video using FFmpeg subtitles filter.
    Returns output path on success, raises on failure.
    """
    style = SUBTITLE_PRESETS.get(preset, SUBTITLE_PRESETS["minimal"])
    style_str = ",".join(f"{k}={v}" for k, v in style.items())

    # FFmpeg needs forward slashes even on Windows
    srt_safe = srt_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video,
        "-vf", f"subtitles='{srt_safe}':force_style='{style_str}'",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "copy",
        output_video
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg subtitle burn failed: {result.stderr[-500:]}")
    return output_video


def save_subtitle_record(project_id: int, srt_content: str, preset: str) -> dict:
    conn = get_db()
    row = execute(conn,
        """INSERT INTO subtitles (project_id, srt_content, preset)
           VALUES (%s, %s, %s) RETURNING *""",
        (project_id, srt_content, preset)
    )
    conn.commit()
    conn.close()
    return dict(row)
