"""
clip_ranking_service.py
Fetches and ranks clips from Pexels. Prefers horizontal, non-duplicate, relevant clips.
"""
import os
import httpx
from db import get_db, execute, fetchall

PEXELS_KEY  = os.getenv("PEXELS_API_KEY", "")
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY", "")


def _score_clip(video: dict, prefer_vertical: bool = False) -> float:
    """Score a Pexels video by quality signals."""
    score = 0.0
    files = video.get("video_files", [])
    if not files:
        return 0.0

    widths = [f.get("width", 0) for f in files]
    heights = [f.get("height", 0) for f in files]
    max_w = max(widths) if widths else 0
    max_h = max(heights) if heights else 0

    # Prefer HD
    if max_w >= 1920:
        score += 3.0
    elif max_w >= 1280:
        score += 2.0
    elif max_w >= 854:
        score += 1.0

    # Orientation preference
    if prefer_vertical:
        if max_h > max_w:
            score += 2.0
    else:
        if max_w > max_h:
            score += 2.0

    # Prefer clips 5-15 seconds (ideal for scenes)
    duration = video.get("duration", 0)
    if 5 <= duration <= 15:
        score += 2.0
    elif 3 <= duration <= 30:
        score += 1.0

    return score


def _best_file(video: dict, prefer_vertical: bool = False) -> dict | None:
    files = video.get("video_files", [])
    mp4_files = [f for f in files if f.get("file_type") == "video/mp4"]
    if not mp4_files:
        mp4_files = files

    if prefer_vertical:
        mp4_files.sort(key=lambda f: (f.get("height", 0), -f.get("width", 1)), reverse=True)
    else:
        mp4_files.sort(key=lambda f: f.get("width", 0), reverse=True)

    # Cap at 1920 width for reasonable file sizes
    for f in mp4_files:
        if f.get("width", 0) <= 1920:
            return f
    return mp4_files[0] if mp4_files else None


async def fetch_and_rank_clips(
    scene_id: int,
    keywords: list[str],
    per_keyword: int = 3,
    prefer_vertical: bool = False
) -> list[dict]:
    """
    Fetch clips for multiple keywords, deduplicate, rank by quality.
    Returns up to 5 best clips.
    """
    if not PEXELS_KEY:
        raise ValueError("PEXELS_API_KEY not set")

    seen_ids = set()
    candidates = []

    async with httpx.AsyncClient(timeout=15) as client:
        for kw in keywords[:3]:  # Max 3 keyword searches
            resp = await client.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": PEXELS_KEY},
                params={
                    "query": kw,
                    "per_page": per_keyword,
                    "orientation": "portrait" if prefer_vertical else "landscape"
                }
            )
            if resp.status_code != 200:
                continue

            for video in resp.json().get("videos", []):
                vid_id = video.get("id")
                if vid_id in seen_ids:
                    continue
                seen_ids.add(vid_id)

                best = _best_file(video, prefer_vertical)
                if not best:
                    continue

                score = _score_clip(video, prefer_vertical)
                candidates.append({
                    "video_url":      best["link"],
                    "preview_url":    video.get("url"),
                    "thumbnail_url":  video.get("image"),
                    "duration":       video.get("duration"),
                    "width":          best.get("width"),
                    "height":         best.get("height"),
                    "relevance_score": score,
                    "keyword":        kw
                })

    # Sort by score descending, take top 5
    candidates.sort(key=lambda c: c["relevance_score"], reverse=True)
    top = candidates[:5]

    # Persist to DB
    conn = get_db()
    saved = []
    for c in top:
        row = execute(conn,
            """INSERT INTO clips
               (scene_id, video_url, preview_url, thumbnail_url, duration, width, height, relevance_score)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT DO NOTHING
               RETURNING id""",
            (scene_id, c["video_url"], c["preview_url"], c["thumbnail_url"],
             c["duration"], c["width"], c["height"], c["relevance_score"])
        )
        if row:
            c["id"] = row["id"]
        else:
            existing = fetchall(conn,
                "SELECT id FROM clips WHERE video_url=%s AND scene_id=%s",
                (c["video_url"], scene_id)
            )
            c["id"] = existing[0]["id"] if existing else None
        saved.append(c)

    conn.commit()
    conn.close()
    return saved
