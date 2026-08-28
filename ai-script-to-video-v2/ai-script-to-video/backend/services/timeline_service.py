"""
timeline_service.py
Builds and manages the timeline from AI-generated scenes.
"""
import psycopg2.extras
from db import get_db


def _execute(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)


def _fetchone(conn, sql, params=()):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _fetchall(conn, sql, params=()):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def build_timeline_from_scenes(project_id: int, scenes: list, selected_clips: list) -> dict:
    conn = get_db()
    try:
        # Clear existing timeline for this project
        _execute(conn, "DELETE FROM timeline_items WHERE project_id = %s", (project_id,))
        _execute(conn, "DELETE FROM timeline_tracks WHERE project_id = %s", (project_id,))

        # Create the 4 tracks
        _execute(conn,
            "INSERT INTO timeline_tracks (project_id, track_type, track_index, label) VALUES (%s,'video',0,'Video')",
            (project_id,))
        video_track = _fetchone(conn, "SELECT lastval()")["lastval"]

        _execute(conn,
            "INSERT INTO timeline_tracks (project_id, track_type, track_index, label) VALUES (%s,'audio',1,'Voiceover')",
            (project_id,))
        vo_track = _fetchone(conn, "SELECT lastval()")["lastval"]

        _execute(conn,
            "INSERT INTO timeline_tracks (project_id, track_type, track_index, label) VALUES (%s,'music',2,'Music')",
            (project_id,))
        music_track = _fetchone(conn, "SELECT lastval()")["lastval"]

        _execute(conn,
            "INSERT INTO timeline_tracks (project_id, track_type, track_index, label) VALUES (%s,'subtitle',3,'Subtitles')",
            (project_id,))
        subtitle_track = _fetchone(conn, "SELECT lastval()")["lastval"]

        # Place each scene as a clip on the video track
        cursor_time = 0.0
        items = []
        for i, scene in enumerate(scenes):
            duration = float(scene.get("duration_hint", 6))
            clip = next((c for c in selected_clips if c.get("scene_index") == i), None)
            clip_url = clip["url"] if clip else ""
            clip_id = clip.get("id") if clip else None

            _execute(conn, """
                INSERT INTO timeline_items
                (track_id, project_id, item_type, scene_index, clip_id,
                 source_url, start_time, end_time, duration, label)
                VALUES (%s,%s,'video',%s,%s,%s,%s,%s,%s,%s)
            """, (
                video_track, project_id, i, clip_id, clip_url,
                cursor_time, cursor_time + duration, duration,
                scene.get("description", f"Scene {i+1}")
            ))
            items.append({
                "scene_index": i,
                "start_time": cursor_time,
                "end_time": cursor_time + duration,
                "duration": duration,
                "label": scene.get("description", f"Scene {i+1}"),
                "clip_url": clip_url
            })
            cursor_time += duration

        conn.commit()
        return {"total_duration": cursor_time, "items": items}
    finally:
        conn.close()


def get_timeline(project_id: int) -> dict:
    conn = get_db()
    try:
        track_rows = _fetchall(conn,
            "SELECT * FROM timeline_tracks WHERE project_id = %s ORDER BY track_index",
            (project_id,))
        tracks = []
        for track in track_rows:
            t = dict(track)
            t["items"] = [dict(r) for r in _fetchall(conn,
                "SELECT * FROM timeline_items WHERE track_id = %s ORDER BY start_time",
                (track["id"],))]
            tracks.append(t)
        return {"project_id": project_id, "tracks": tracks}
    finally:
        conn.close()


def update_timeline_item(item_id: int, updates: dict) -> bool:
    allowed = ["start_time", "end_time", "duration", "trim_in", "trim_out", "label", "source_url"]
    sets, vals = [], []
    for k, v in updates.items():
        if k in allowed:
            sets.append(f"{k} = %s")
            vals.append(v)
    if not sets:
        return False
    conn = get_db()
    try:
        vals.append(item_id)
        _execute(conn,
            f"UPDATE timeline_items SET {', '.join(sets)}, updated_at=NOW() WHERE id = %s",
            tuple(vals))
        conn.commit()
        return True
    finally:
        conn.close()


def delete_timeline_item(item_id: int) -> bool:
    conn = get_db()
    try:
        _execute(conn, "DELETE FROM timeline_items WHERE id = %s", (item_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def reorder_timeline_items(project_id: int, ordered_ids: list) -> bool:
    conn = get_db()
    try:
        cursor_time = 0.0
        for item_id in ordered_ids:
            row = _fetchone(conn, "SELECT duration FROM timeline_items WHERE id = %s", (item_id,))
            if not row:
                continue
            dur = float(row["duration"])
            _execute(conn,
                "UPDATE timeline_items SET start_time=%s, end_time=%s, updated_at=NOW() WHERE id=%s",
                (cursor_time, cursor_time + dur, item_id))
            cursor_time += dur
        conn.commit()
        return True
    finally:
        conn.close()