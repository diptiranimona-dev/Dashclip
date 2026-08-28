"""
voice_service.py — DashClip V4
Fixed: Windows subprocess via ThreadPoolExecutor, hardcoded fallback voices.
"""
import os, asyncio, uuid, concurrent.futures, subprocess
from pathlib import Path
import aiofiles
from db import get_db, execute, fetchone

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads")) / "voices"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

FALLBACK_VOICES = [
    {"id": "en-US-GuyNeural",       "label": "Guy — US Male",         "lang": "en-US", "style": "general"},
    {"id": "en-US-AriaNeural",      "label": "Aria — US Female",      "lang": "en-US", "style": "general"},
    {"id": "en-US-DavisNeural",     "label": "Davis — US Male",       "lang": "en-US", "style": "energetic"},
    {"id": "en-US-JennyNeural",     "label": "Jenny — US Female",     "lang": "en-US", "style": "conversational"},
    {"id": "en-US-ChristopherNeural","label": "Christopher — US Male","lang": "en-US", "style": "authoritative"},
    {"id": "en-GB-RyanNeural",      "label": "Ryan — UK Male",        "lang": "en-GB", "style": "documentary"},
    {"id": "en-GB-SoniaNeural",     "label": "Sonia — UK Female",     "lang": "en-GB", "style": "luxury"},
    {"id": "en-AU-WilliamNeural",   "label": "William — AU Male",     "lang": "en-AU", "style": "calm"},
    {"id": "en-IN-NeerjaNeural",    "label": "Neerja — IN Female",    "lang": "en-IN", "style": "warm"},
    {"id": "en-US-TonyNeural",      "label": "Tony — US Male",        "lang": "en-US", "style": "narrative"},
    {"id": "en-US-NancyNeural",     "label": "Nancy — US Female",     "lang": "en-US", "style": "professional"},
    {"id": "en-US-BrandonNeural",   "label": "Brandon — US Male",     "lang": "en-US", "style": "dramatic"},
]

STYLE_VOICE_MAP = {
    "cinematic":    "en-US-ChristopherNeural",
    "documentary":  "en-GB-RyanNeural",
    "youtube":      "en-US-DavisNeural",
    "educational":  "en-US-AriaNeural",
    "dark":         "en-GB-RyanNeural",
    "luxury":       "en-GB-SoniaNeural",
    "energetic":    "en-US-DavisNeural",
    "minimal":      "en-US-JennyNeural",
    "storytelling": "en-US-ChristopherNeural",
    "history":      "en-GB-RyanNeural",
    "science":      "en-US-GuyNeural",
    "travel":       "en-US-AriaNeural",
    "business":     "en-US-TonyNeural",
}

async def get_voice_options() -> list:
    """Always returns voices — hardcoded fallback so dropdown is never empty."""
    return FALLBACK_VOICES

def _run_edge_tts(voice_id: str, text: str, dest: str) -> tuple[int, str]:
    """Run edge-tts synchronously in a thread — Windows compatible."""
    result = subprocess.run(
        ["edge-tts", f"--voice={voice_id}", f"--text={text}", f"--write-media={dest}"],
        capture_output=True, text=True, timeout=120
    )
    return result.returncode, result.stderr

def _run_ffprobe_duration(path: str) -> float:
    """Get audio duration via ffprobe — synchronous, run in thread."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15
        )
        return float(result.stdout.strip() or 0)
    except Exception:
        return 0.0

async def generate_tts(project_id: int, text: str, voice_id: str = "en-US-GuyNeural") -> dict:
    if not text or not text.strip():
        raise ValueError("No narration text provided")
    if not voice_id or not voice_id.strip():
        voice_id = "en-US-GuyNeural"

    # Clean text — remove script tags
    import re
    clean_text = re.sub(r'\[[\w\s\d]+\]', '', text, flags=re.I)
    clean_text = re.sub(r'\*+', '', clean_text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()[:5000]
    if not clean_text:
        clean_text = text[:5000]

    fname = f"{project_id}_{uuid.uuid4().hex[:8]}.mp3"
    dest = UPLOAD_DIR / fname

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        returncode, stderr = await loop.run_in_executor(
            pool, _run_edge_tts, voice_id, clean_text, str(dest)
        )

    if returncode != 0:
        if "NotSupportedError" in stderr or "InvalidVoice" in stderr:
            # Retry with fallback voice
            with concurrent.futures.ThreadPoolExecutor() as pool:
                returncode, stderr = await loop.run_in_executor(
                    pool, _run_edge_tts, "en-US-GuyNeural", clean_text, str(dest)
                )
        if returncode != 0:
            raise RuntimeError(f"edge-tts failed: {stderr[:300]}")

    if not dest.exists() or dest.stat().st_size < 100:
        raise RuntimeError("edge-tts produced no audio output")

    # Get duration in thread
    with concurrent.futures.ThreadPoolExecutor() as pool:
        duration = await loop.run_in_executor(pool, _run_ffprobe_duration, str(dest))
    if not duration:
        duration = len(clean_text.split()) / 2.5

    conn = get_db()
    row = execute(conn,
        "INSERT INTO voiceovers (project_id,type,file_path,text_content,duration) VALUES (%s,'tts',%s,%s,%s) RETURNING id",
        (project_id, str(dest), clean_text, duration))
    conn.commit(); conn.close()
    return {"id": row["id"], "file_path": str(dest), "duration": round(duration, 2), "text_content": clean_text}

async def auto_generate_voiceover(project_id: int, script: str, style: str = "cinematic") -> dict:
    """Auto-generate TTS from script using style-appropriate voice."""
    import re
    # Extract only voiceover text
    lines = script.split('\n')
    vo_lines = []
    in_vo = False
    for line in lines:
        line = line.strip()
        if not line: continue
        if re.match(r'\[VOICEOVER\]', line, re.I):
            in_vo = True
            rest = re.sub(r'\[VOICEOVER\]', '', line, flags=re.I).strip()
            if rest: vo_lines.append(rest)
        elif re.match(r'\[SCENE\s*\d+\]', line, re.I):
            in_vo = False
        elif re.match(r'\[CAMERA', line, re.I) or re.match(r'Description:', line, re.I):
            in_vo = False
        elif in_vo:
            vo_lines.append(line)

    narration = ' '.join(vo_lines).strip()
    if not narration or len(narration) < 20:
        # Strip all tags
        narration = re.sub(r'\[[\w\s\d]+\]', '', script, flags=re.I)
        narration = re.sub(r'Description:', '', narration, flags=re.I)
        narration = re.sub(r'\*+', '', narration)
        narration = re.sub(r'\s+', ' ', narration).strip()

    voice_id = STYLE_VOICE_MAP.get(style, "en-US-GuyNeural")
    return await generate_tts(project_id, narration, voice_id)

async def save_uploaded_voice(project_id: int, data: bytes, filename: str) -> dict:
    safe = "".join(c for c in filename if c.isalnum() or c in "._-")
    dest = UPLOAD_DIR / f"{project_id}_{uuid.uuid4().hex[:6]}_{safe}"
    async with aiofiles.open(dest, "wb") as f:
        await f.write(data)

    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        duration = await loop.run_in_executor(pool, _run_ffprobe_duration, str(dest))

    conn = get_db()
    row = execute(conn,
        "INSERT INTO voiceovers (project_id,type,file_path,text_content,duration) VALUES (%s,'upload',%s,%s,%s) RETURNING id",
        (project_id, str(dest), filename, duration))
    conn.commit(); conn.close()
    return {"id": row["id"], "file_path": str(dest), "duration": round(duration, 2)}

def get_project_voiceovers(project_id: int) -> list:
    conn = get_db()
    rows = []
    try:
        from db import fetchall
        rows = fetchall(conn, "SELECT * FROM voiceovers WHERE project_id=%s ORDER BY created_at DESC", (project_id,))
    except Exception: pass
    conn.close()
    return rows
