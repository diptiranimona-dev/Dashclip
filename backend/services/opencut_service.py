"""
opencut_service.py — B4 (NEW FILE)
Builds the OpenCut timeline payload from DashClip project data.
Handles the export webhook from OpenCut.
"""
import os
import uuid
from pathlib import Path
from db import get_db, fetchone, fetchall, execute


UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
API_BASE = "http://127.0.0.1:8000"


def build_opencut_payload(project_id: int) -> dict:
    """
    Build the complete OpenCut timeline payload from DashClip project.
    This gets sent to OpenCut via postMessage when the iframe loads.
    """
    conn = get_db()
    
    # Get project
    project = fetchone(conn, "SELECT * FROM projects WHERE id = %s", (project_id,))
    if not project:
        conn.close()
        raise ValueError(f"Project {project_id} not found")

    # Get selected clips from timeline_items (ordered by start_time)
    tl_tracks = fetchall(conn,
        "SELECT * FROM timeline_tracks WHERE project_id = %s ORDER BY track_index",
        (project_id,)
    )
    
    clips = []
    for track in tl_tracks:
        if track["track_type"] == "video":
            items = fetchall(conn,
                "SELECT * FROM timeline_items WHERE track_id = %s ORDER BY start_time",
                (track["id"],)
            )
            for item in items:
                clips.append({
                    "id": item["clip_id"] or 0,
                    "scene_index": item["scene_index"] or 0,
                    "url": item["source_url"] or "",
                    "duration": float(item["duration"] or 6),
                    "trim_in": float(item["trim_in"] or 0),
                    "trim_out": float(item["trim_out"] or 0),
                    "label": item["label"] or f"Scene {item['scene_index']+1}",
                    "width": 1920,
                    "height": 1080,
                })

    # Get voiceover
    voiceover = fetchone(conn,
        "SELECT * FROM voiceovers WHERE project_id = %s ORDER BY created_at DESC LIMIT 1",
        (project_id,)
    )
    
    # Get music
    music = fetchone(conn,
        "SELECT * FROM music_tracks WHERE project_id = %s AND selected = TRUE ORDER BY created_at DESC LIMIT 1",
        (project_id,)
    )
    if not music:
        music = fetchone(conn,
            "SELECT * FROM music_tracks WHERE project_id = %s ORDER BY created_at DESC LIMIT 1",
            (project_id,)
        )

    # Get subtitles
    subtitle = fetchone(conn,
        "SELECT * FROM subtitles WHERE project_id = %s ORDER BY created_at DESC LIMIT 1",
        (project_id,)
    )
    
    conn.close()

    # Build total duration
    total_duration = sum(c["duration"] for c in clips) if clips else 30.0

    # Build audio section
    audio = {}
    if voiceover and voiceover.get("file_path"):
        fp = Path(voiceover["file_path"])
        if fp.exists():
            rel_path = f"/uploads/voices/{fp.name}"
            audio["voiceover"] = {
                "url": rel_path,
                "duration": float(voiceover.get("duration") or 30),
            }

    if music and music.get("file_path"):
        fp = Path(music["file_path"])
        if fp.exists():
            rel_path = f"/uploads/music/{fp.name}"
            audio["music"] = {
                "url": rel_path,
                "duration": float(music.get("duration") or total_duration),
                "volume": 0.12,
            }

    # Parse subtitles if available
    subtitle_list = []
    if subtitle and subtitle.get("srt_content"):
        subtitle_list = _parse_srt(subtitle["srt_content"])

    return {
        "type": "DASHCLIP_LOAD_TIMELINE",
        "version": "1.0",
        "project": {
            "id": project_id,
            "title": project.get("title", "Untitled"),
            "style": project.get("style_preset", "cinematic"),
            "format": project.get("video_format", "landscape"),
            "total_duration": total_duration,
        },
        "clips": clips,
        "audio": audio,
        "subtitles": subtitle_list,
        # B5 extension points (empty now, populated by AI Director later)
        "_b5": {
            "scene_intelligence": None,
            "visual_dna": None,
            "story_arc": None,
            "music_director": None,
        }
    }


def process_opencut_export(project_id: int, export_data: dict) -> dict:
    """
    Receives the edited timeline from OpenCut export.
    Saves to DB and triggers FFmpeg render via render_service.
    """
    conn = get_db()
    
    # Update timeline_items from OpenCut's edited state
    clips = export_data.get("clips", [])
    
    # Clear existing timeline
    execute(conn, "DELETE FROM timeline_items WHERE project_id = %s", (project_id,))
    execute(conn, "DELETE FROM timeline_tracks WHERE project_id = %s", (project_id,))
    
    # Recreate video track
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO timeline_tracks (project_id, track_type, track_index, label) VALUES (%s,'video',0,'Video') RETURNING id",
            (project_id,)
        )
        video_track_id = cur.fetchone()[0]
    
    cursor_time = 0.0
    clip_ids = []
    clip_urls = []
    
    for i, clip in enumerate(clips):
        duration = clip.get("end_time", 6) - clip.get("start_time", 0)
        
        # Try to find clip_id from URL
        clip_id = clip.get("clip_id")
        url = clip.get("url", "")
        
        if not clip_id and url:
            row = fetchone(conn, "SELECT id FROM clips WHERE video_url = %s LIMIT 1", (url,))
            if row:
                clip_id = row["id"]
        
        execute(conn, """
            INSERT INTO timeline_items
            (track_id, project_id, item_type, scene_index, clip_id,
             source_url, start_time, end_time, duration, trim_in, trim_out, label)
            VALUES (%s,%s,'video',%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            video_track_id, project_id, i, clip_id, url,
            cursor_time, cursor_time + duration, duration,
            float(clip.get("trim_in", 0)),
            float(clip.get("trim_out", 0)),
            clip.get("label", f"Scene {i+1}")
        ))
        
        if clip_id:
            clip_ids.append(clip_id)
        clip_urls.append(url)
        cursor_time += duration
    
    conn.commit()
    conn.close()
    
    return {
        "clip_ids": clip_ids,
        "clip_urls": clip_urls,
        "voiceover_url": export_data.get("voiceover_url"),
        "music_url": export_data.get("music_url"),
        "music_volume": export_data.get("music_volume", 0.12),
    }


def _parse_srt(srt_content: str) -> list:
    """Parse SRT into list of {start, end, text} dicts."""
    result = []
    blocks = srt_content.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        try:
            times = lines[1].split(" --> ")
            start = _srt_time_to_seconds(times[0].strip())
            end = _srt_time_to_seconds(times[1].strip())
            text = " ".join(lines[2:])
            result.append({"start": start, "end": end, "text": text})
        except Exception:
            continue
    return result


def _srt_time_to_seconds(t: str) -> float:
    t = t.replace(",", ".")
    parts = t.split(":")
    h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    return h * 3600 + m * 60 + s
