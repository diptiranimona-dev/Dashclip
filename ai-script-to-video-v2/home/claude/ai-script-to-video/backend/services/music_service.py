"""
music_service.py
Handles background music:
  1. Search Pixabay music API (copyright-free)
  2. Upload own music file
  3. Manual URL/name entry
"""
import os
import uuid
import subprocess
from pathlib import Path

import httpx
from db import get_db, execute, fetchall

PIXABAY_KEY = os.getenv("PIXABAY_API_KEY", "")
UPLOAD_DIR  = Path(os.getenv("UPLOAD_DIR", "./uploads/music"))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ─── SEARCH ──────────────────────────────────────────────────────────────────

async def search_music(query: str, page: int = 1, per_page: int = 10) -> list[dict]:
    """Search Pixabay for copyright-free music."""
    if not PIXABAY_KEY:
        raise ValueError("PIXABAY_API_KEY not set")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            "https://pixabay.com/api/",
            params={
                "key":        PIXABAY_KEY,
                "q":          query,
                "media_type": "music",
                "per_page":   per_page,
                "page":       page,
            }
        )
    if resp.status_code != 200:
        raise RuntimeError(f"Pixabay API error {resp.status_code}: {resp.text[:200]}")

    results = []
    for hit in resp.json().get("hits", []):
        results.append({
            "title":          hit.get("tags", "Unknown Track"),
            "url":            hit.get("pageURL", ""),
            "preview_url":    hit.get("previewURL", ""),
            "duration":       hit.get("duration", 0),
            "source":         "pixabay",
            "copyright_safe": True,   # Pixabay music is royalty-free
        })
    return results


async def add_music_from_search(project_id: int, title: str, url: str,
                                 preview_url: str = "", duration: float = 0) -> dict:
    """Save a searched music track to the project (downloads preview for render)."""
    save_path = None

    if preview_url:
        try:
            save_path = UPLOAD_DIR / f"music_{uuid.uuid4().hex}.mp3"
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                resp = await client.get(preview_url)
                resp.raise_for_status()
                save_path.write_bytes(resp.content)
        except Exception:
            save_path = None

    conn = get_db()
    # Deselect any existing music for this project
    execute(conn, "UPDATE music_tracks SET selected = FALSE WHERE project_id = %s", (project_id,))
    row = execute(conn,
        """INSERT INTO music_tracks (project_id, title, source, url, file_path, copyright_safe, selected)
           VALUES (%s, %s, 'pixabay', %s, %s, TRUE, TRUE) RETURNING *""",
        (project_id, title, url, str(save_path) if save_path else None)
    )
    conn.commit()
    conn.close()
    return dict(row)


# ─── UPLOAD ───────────────────────────────────────────────────────────────────

async def save_uploaded_music(project_id: int, file_bytes: bytes, filename: str) -> dict:
    ext = Path(filename).suffix.lower()
    if ext not in {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac"}:
        raise ValueError(f"Unsupported format: {ext}")

    save_path = UPLOAD_DIR / f"upload_{uuid.uuid4().hex}{ext}"
    save_path.write_bytes(file_bytes)
    duration = _get_duration(str(save_path))

    conn = get_db()
    execute(conn, "UPDATE music_tracks SET selected = FALSE WHERE project_id = %s", (project_id,))
    row = execute(conn,
        """INSERT INTO music_tracks (project_id, title, source, file_path, copyright_safe, selected)
           VALUES (%s, %s, 'upload', %s, FALSE, TRUE) RETURNING *""",
        (project_id, filename, str(save_path))
    )
    conn.commit()
    conn.close()
    return dict(row)


# ─── MANUAL ───────────────────────────────────────────────────────────────────

async def add_music_manual(project_id: int, title: str, url: str = "") -> dict:
    """User types a song name or pastes a direct URL manually."""
    conn = get_db()
    execute(conn, "UPDATE music_tracks SET selected = FALSE WHERE project_id = %s", (project_id,))
    row = execute(conn,
        """INSERT INTO music_tracks (project_id, title, source, url, copyright_safe, selected)
           VALUES (%s, %s, 'manual', %s, FALSE, TRUE) RETURNING *""",
        (project_id, title, url)
    )
    conn.commit()
    conn.close()
    return dict(row)


def get_project_music(project_id: int) -> list[dict]:
    conn = get_db()
    rows = fetchall(conn,
        "SELECT * FROM music_tracks WHERE project_id = %s ORDER BY created_at DESC",
        (project_id,)
    )
    conn.close()
    return rows


def _get_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0
