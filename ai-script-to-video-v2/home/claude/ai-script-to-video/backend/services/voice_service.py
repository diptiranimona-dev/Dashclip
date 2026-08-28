"""
voice_service.py
Handles three voiceover modes:
  1. AI-generated TTS via edge-tts (free, local, no voice cloning)
  2. User file upload
  3. Search Pixabay audio (narration/spoken word)

No voice cloning. No real-person imitation.
"""
import os
import uuid
import asyncio
import subprocess
from pathlib import Path

import httpx
from db import get_db, execute, fetchone

UPLOAD_DIR  = Path(os.getenv("UPLOAD_DIR", "./uploads/voices"))
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY", "")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ─── OPTION 1: AI TTS via edge-tts ───────────────────────────────────────────
# edge-tts is a free Microsoft Edge TTS client — no API key, no voice cloning
# Install: pip install edge-tts

VOICE_OPTIONS = [
    {"id": "en-US-AriaNeural",   "label": "Aria (Female, Warm)"},
    {"id": "en-US-GuyNeural",    "label": "Guy (Male, Professional)"},
    {"id": "en-GB-SoniaNeural",  "label": "Sonia (Female, British)"},
    {"id": "en-AU-NatashaNeural","label": "Natasha (Female, Australian)"},
]


async def generate_tts(project_id: int, text: str, voice_id: str = "en-US-AriaNeural") -> dict:
    """Generate voiceover using edge-tts (free, local, no cloning)."""
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        raise RuntimeError("edge-tts not installed. Run: pip install edge-tts")

    out_path = UPLOAD_DIR / f"tts_{uuid.uuid4().hex}.mp3"

    communicate = __import__("edge_tts").Communicate(text, voice_id)
    await communicate.save(str(out_path))

    # Get duration via ffprobe
    duration = _get_audio_duration(str(out_path))

    conn = get_db()
    row = execute(conn,
        """INSERT INTO voiceovers (project_id, type, file_path, text_content, duration)
           VALUES (%s, 'ai', %s, %s, %s) RETURNING *""",
        (project_id, str(out_path), text, duration)
    )
    conn.commit()
    conn.close()
    return dict(row)


def get_voice_options() -> list[dict]:
    return VOICE_OPTIONS


# ─── OPTION 2: User upload ────────────────────────────────────────────────────

async def save_uploaded_voice(project_id: int, file_bytes: bytes, filename: str) -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in {".mp3", ".wav", ".m4a", ".ogg", ".aac"}:
        raise ValueError(f"Unsupported audio format: {ext}")

    save_path = UPLOAD_DIR / f"upload_{uuid.uuid4().hex}{ext}"
    save_path.write_bytes(file_bytes)

    duration = _get_audio_duration(str(save_path))

    conn = get_db()
    row = execute(conn,
        """INSERT INTO voiceovers (project_id, type, file_path, duration)
           VALUES (%s, 'upload', %s, %s) RETURNING *""",
        (project_id, str(save_path), duration)
    )
    conn.commit()
    conn.close()
    return dict(row)


# ─── OPTION 3: Search Pixabay audio ──────────────────────────────────────────

async def search_voice_audio(query: str, page: int = 1) -> list[dict]:
    """Search Pixabay for spoken-word / narration audio."""
    if not PIXABAY_KEY:
        raise ValueError("PIXABAY_API_KEY not set — needed for audio search")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://pixabay.com/api/",
            params={
                "key":       PIXABAY_KEY,
                "q":         query,
                "media_type":"music",
                "per_page":  10,
                "page":      page,
            }
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Pixabay error: {resp.status_code}")

    results = []
    for hit in resp.json().get("hits", []):
        results.append({
            "title":    hit.get("tags", "Unknown"),
            "url":      hit.get("pageURL", ""),
            "preview":  hit.get("previewURL", ""),
            "duration": hit.get("duration", 0),
            "source":   "pixabay",
        })
    return results


async def save_searched_voice(project_id: int, url: str, title: str = "") -> dict:
    """Download a found audio clip and save it as a voiceover."""
    save_path = UPLOAD_DIR / f"search_{uuid.uuid4().hex}.mp3"

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        save_path.write_bytes(resp.content)

    duration = _get_audio_duration(str(save_path))

    conn = get_db()
    row = execute(conn,
        """INSERT INTO voiceovers (project_id, type, file_path, text_content, duration)
           VALUES (%s, 'search', %s, %s, %s) RETURNING *""",
        (project_id, str(save_path), title, duration)
    )
    conn.commit()
    conn.close()
    return dict(row)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def _get_audio_duration(path: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0
