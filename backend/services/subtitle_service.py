"""
subtitle_service.py — DashClip V4 Fixed
Clean all script artifacts before generating SRT.
No more NARRATOR:, Scene tags, camera directions in subtitles.
"""
import re

def clean_for_subtitle(text: str) -> str:
    """Strip ALL non-narration artifacts from text before making subtitles."""
    t = text
    # Remove "Here is the script" and similar LLM preambles
    t = re.sub(r'Here is the (script|video script|screenplay)[:\.]?', '', t, flags=re.I)
    t = re.sub(r'Here\'?s? (the )?(script|video)[:\.]?', '', t, flags=re.I)
    # Remove scene headers like [SCENE 1], Scene 1, SCENE 1:
    t = re.sub(r'\[?SCENE\s*\d+\]?[:\s]*', '', t, flags=re.I)
    t = re.sub(r'^Scene\s*\d+[:\s]*', '', t, flags=re.I | re.M)
    t = re.sub(r'^\d+\.\s*[A-Z][^a-z]{3,}\n', '', t, flags=re.M)  # numbered scene headers
    # Remove voiceover/narrator tags
    t = re.sub(r'\[?(?:VOICEOVER|Voice ?Over|Voiceover)\]?:?\s*', '', t, flags=re.I)
    t = re.sub(r'\[?(?:NARRATOR|Narrator|VO|V\.O\.)\]?:?\s*', '', t, flags=re.I)
    t = re.sub(r'(?:NARRATOR|Narrator|VO):?\s*', '', t, flags=re.I)
    # Remove Description: lines
    t = re.sub(r'Description:[^\n]*\n?', '', t, flags=re.I)
    # Remove camera direction lines
    t = re.sub(r'\[CAMERA[^\]]*\]', '', t, flags=re.I)
    t = re.sub(r'\[CUT TO[^\]]*\]', '', t, flags=re.I)
    t = re.sub(r'\[FADE[^\]]*\]', '', t, flags=re.I)
    # Remove any remaining bracket content
    t = re.sub(r'\[[^\]]*\]', '', t)
    # Remove asterisks
    t = re.sub(r'\*+', '', t)
    # Remove lines that are clearly camera directions (short, start with shot types)
    cam_words = r'(aerial shot|wide shot|close.?up|medium shot|establishing shot|'
    cam_words += r'cut to|fade in|fade out|zoom in|zoom out|pan (left|right|up|down)|'
    cam_words += r'tracking shot|dolly shot|crane shot|handheld|steadicam)'
    t = re.sub(cam_words + r'[^\n]*\n?', '', t, flags=re.I)
    # Remove numbered list markers that are scene indicators
    t = re.sub(r'^\s*\d+\.\s*(?:Dark|Light|Close|Wide|Medium|Aerial|Shot)[^\n]*\n?', '', t, flags=re.I | re.M)
    # Clean up whitespace
    t = re.sub(r'\n{3,}', '\n\n', t)
    t = re.sub(r' {2,}', ' ', t)
    t = t.strip()
    return t

def generate_srt_from_text(narration_text: str, total_duration: float,
                            words_per_subtitle: int = 6) -> str:
    """Generate SRT subtitle file from narration text."""
    # Clean the text first
    clean_text = clean_for_subtitle(narration_text)
    if not clean_text or total_duration <= 0:
        return ""

    words = clean_text.split()
    if not words:
        return ""

    chunks = [words[i:i+words_per_subtitle]
              for i in range(0, len(words), words_per_subtitle)]
    if not chunks:
        return ""

    time_per_chunk = total_duration / len(chunks)
    srt_lines = []

    for i, chunk in enumerate(chunks):
        start_sec = i * time_per_chunk
        end_sec = start_sec + time_per_chunk - 0.05
        srt_lines.append(f"{i+1}")
        srt_lines.append(f"{_fmt_time(start_sec)} --> {_fmt_time(end_sec)}")
        srt_lines.append(" ".join(chunk))
        srt_lines.append("")

    return "\n".join(srt_lines)

def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def generate_srt_from_voiceover_file(vo_path: str, duration: float) -> str:
    """Attempt to generate subtitles from a voiceover file (no transcription — use duration)."""
    return ""  # Placeholder — actual transcription would need whisper
