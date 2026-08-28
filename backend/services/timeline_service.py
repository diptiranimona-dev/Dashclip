"""
timeline_service.py  —  DashClip V3 Phase C
Builds and manages timeline tracks from AI-generated scenes + clips.
Phase C additions: split, duplicate, ripple delete, layer/lock/mute management,
and expanded update_timeline_item to cover all advanced editing properties.
"""
import psycopg2.extras
from db import get_db


def _execute(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)


def _fetchone(conn, sql, params=()):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def _fetchall(conn, sql, params=()):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def _insert_track(conn, project_id: int, track_type: str, track_index: int, label: str) -> int:
    """Insert a timeline track and return its ID."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO timeline_tracks (project_id, track_type, track_index, label)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (project_id, track_type, track_index, label)
        )
        return cur.fetchone()[0]


def build_timeline_from_scenes(project_id: int, scenes: list, selected_clips: list) -> dict:
    """
    Convert AI scenes + selected clips into timeline tracks in the DB.
    Called when user clicks Continue to Timeline OR starts a render.
    """
    conn = get_db()
    try:
        # Clear existing timeline for this project
        _execute(conn, "DELETE FROM timeline_items WHERE project_id = %s", (project_id,))
        _execute(conn, "DELETE FROM timeline_tracks WHERE project_id = %s", (project_id,))

        # Create the 4 standard tracks
        video_track_id    = _insert_track(conn, project_id, "video",    0, "Video")
        vo_track_id       = _insert_track(conn, project_id, "audio",    1, "Voiceover")
        music_track_id    = _insert_track(conn, project_id, "music",    2, "Music")
        subtitle_track_id = _insert_track(conn, project_id, "subtitle", 3, "Subtitles")

        # Place each scene as a clip item on the video track
        cursor_time = 0.0
        items = []

        for i, scene in enumerate(scenes):
            duration = float(scene.get("duration_hint", 6))

            # Match clip to scene by scene_index
            clip = next(
                (c for c in selected_clips if int(c.get("scene_index", -1)) == i),
                None
            )
            clip_url = clip.get("url", "") if clip else ""
            clip_id  = clip.get("id")      if clip else None

            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO timeline_items
                       (track_id, project_id, item_type, scene_index, clip_id,
                        source_url, start_time, end_time, duration, label)
                       VALUES (%s,%s,'video',%s,%s,%s,%s,%s,%s,%s)
                       RETURNING id""",
                    (
                        video_track_id, project_id, i, clip_id, clip_url,
                        cursor_time, cursor_time + duration, duration,
                        scene.get("description", f"Scene {i+1}")
                    )
                )
                item_id = cur.fetchone()[0]

            items.append({
                "id":          item_id,
                "scene_index": i,
                "start_time":  cursor_time,
                "end_time":    cursor_time + duration,
                "duration":    duration,
                "label":       scene.get("description", f"Scene {i+1}"),
                "clip_url":    clip_url
            })
            cursor_time += duration

        conn.commit()
        return {
            "total_duration": cursor_time,
            "tracks": {
                "video_track_id":    video_track_id,
                "voiceover_track_id": vo_track_id,
                "music_track_id":    music_track_id,
                "subtitle_track_id": subtitle_track_id
            },
            "items": items
        }
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_timeline(project_id: int) -> dict:
    """Load full timeline for a project including all tracks and items."""
    conn = get_db()
    try:
        track_rows = _fetchall(conn,
            "SELECT * FROM timeline_tracks WHERE project_id = %s ORDER BY track_index",
            (project_id,)
        )
        tracks = []
        for track in track_rows:
            t = dict(track)
            t["items"] = _fetchall(conn,
                "SELECT * FROM timeline_items WHERE track_id = %s ORDER BY start_time",
                (track["id"],)
            )
            tracks.append(t)
        return {"project_id": project_id, "tracks": tracks}
    finally:
        conn.close()


def update_timeline_item(item_id: int, updates: dict) -> bool:
    """Update a single timeline item (trim, label, duration)."""
    allowed = ["start_time", "end_time", "duration", "trim_in", "trim_out", "label", "source_url",
               "speed", "opacity", "track_layer", "is_locked", "is_muted",
               "color_grade", "transform", "transition_in", "transition_out"]
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
            tuple(vals)
        )
        conn.commit()
        return True
    finally:
        conn.close()


def delete_timeline_item(item_id: int) -> bool:
    """Delete a clip from the timeline."""
    conn = get_db()
    try:
        _execute(conn, "DELETE FROM timeline_items WHERE id = %s", (item_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def reorder_timeline_items(project_id: int, ordered_ids: list) -> bool:
    """Reassign start_time based on new drag-drop order."""
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
                (cursor_time, cursor_time + dur, item_id)
            )
            cursor_time += dur
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════
# PHASE C — SPLIT, DUPLICATE, RIPPLE, LAYERS
# ═══════════════════════════════════════════════════════════════════

def split_timeline_item(item_id: int, split_offset: float) -> dict:
    """Split one item into two at split_offset seconds from its start_time."""
    conn = get_db()
    try:
        item = _fetchone(conn, "SELECT * FROM timeline_items WHERE id=%s", (item_id,))
        if not item:
            raise ValueError(f"Item {item_id} not found")
        dur = float(item["duration"])
        if not (0 < split_offset < dur):
            raise ValueError("split_offset must be inside the item's duration")

        trim_in = float(item.get("trim_in") or 0)
        new_trim_split = trim_in + split_offset

        with conn.cursor() as cur:
            # Shrink the original item to end at the split point
            cur.execute(
                "UPDATE timeline_items SET end_time=%s, duration=%s, trim_out=%s, updated_at=NOW() WHERE id=%s",
                (item["start_time"] + split_offset, split_offset,
                 float(item.get("trim_out") or 0) + (dur - split_offset), item_id)
            )
            # Create the second half as a new item right after
            cur.execute(
                """INSERT INTO timeline_items
                   (track_id, project_id, item_type, scene_index, clip_id, source_url,
                    start_time, end_time, duration, trim_in, trim_out, label,
                    speed, opacity, track_layer)
                   SELECT track_id, project_id, item_type, scene_index, clip_id, source_url,
                          %s, %s, %s, %s, trim_out, label, speed, opacity, track_layer
                   FROM timeline_items WHERE id=%s RETURNING id""",
                (item["start_time"] + split_offset, item["end_time"],
                 dur - split_offset, new_trim_split, item_id)
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        return {"original_id": item_id, "new_id": new_id, "split_offset": split_offset}
    except Exception as e:
        conn.rollback(); raise e
    finally:
        conn.close()


def duplicate_timeline_item(item_id: int) -> dict:
    """Duplicate an item, placing the copy immediately after the original."""
    conn = get_db()
    try:
        item = _fetchone(conn, "SELECT * FROM timeline_items WHERE id=%s", (item_id,))
        if not item:
            raise ValueError(f"Item {item_id} not found")
        dur = float(item["duration"])
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO timeline_items
                   (track_id, project_id, item_type, scene_index, clip_id, source_url,
                    start_time, end_time, duration, trim_in, trim_out, label,
                    speed, opacity, track_layer, color_grade, transform)
                   SELECT track_id, project_id, item_type, scene_index, clip_id, source_url,
                          %s, %s, duration, trim_in, trim_out, label,
                          speed, opacity, track_layer, color_grade, transform
                   FROM timeline_items WHERE id=%s RETURNING id""",
                (item["end_time"], item["end_time"] + dur, item_id)
            )
            new_id = cur.fetchone()[0]
        conn.commit()
        new_item = _fetchone(conn, "SELECT * FROM timeline_items WHERE id=%s", (new_id,))
        return new_item
    except Exception as e:
        conn.rollback(); raise e
    finally:
        conn.close()


def ripple_delete_item(item_id: int) -> bool:
    """Delete an item and shift every later item on the same track left to close the gap."""
    conn = get_db()
    try:
        item = _fetchone(conn, "SELECT * FROM timeline_items WHERE id=%s", (item_id,))
        if not item:
            return False
        track_id = item["track_id"]
        gap = float(item["duration"])
        cutoff = float(item["start_time"])

        _execute(conn, "DELETE FROM timeline_items WHERE id=%s", (item_id,))

        later_items = _fetchall(conn,
            "SELECT id, start_time, end_time FROM timeline_items WHERE track_id=%s AND start_time > %s ORDER BY start_time",
            (track_id, cutoff))
        for it in later_items:
            _execute(conn,
                "UPDATE timeline_items SET start_time=start_time-%s, end_time=end_time-%s, updated_at=NOW() WHERE id=%s",
                (gap, gap, it["id"]))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback(); raise e
    finally:
        conn.close()


def add_track(project_id: int, track_type: str, label: str) -> dict:
    """Add a new track to a project (e.g. a second B-roll/overlay track)."""
    conn = get_db()
    try:
        existing = _fetchall(conn,
            "SELECT COALESCE(MAX(track_index),-1) as m FROM timeline_tracks WHERE project_id=%s",
            (project_id,))
        next_index = (existing[0]["m"] if existing else -1) + 1
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO timeline_tracks (project_id, track_type, track_index, label)
                   VALUES (%s,%s,%s,%s) RETURNING id""",
                (project_id, track_type, next_index, label)
            )
            track_id = cur.fetchone()[0]
        conn.commit()
        return {"id": track_id, "track_type": track_type, "track_index": next_index, "label": label}
    except Exception as e:
        conn.rollback(); raise e
    finally:
        conn.close()


def update_track(track_id: int, updates: dict) -> bool:
    """Update track properties: lock, mute, visibility, height, color, label."""
    allowed = ["is_locked", "is_muted", "is_visible", "height", "color", "label"]
    sets, vals = [], []
    for k, v in updates.items():
        if k in allowed:
            sets.append(f"{k} = %s")
            vals.append(v)
    if not sets:
        return False
    conn = get_db()
    try:
        vals.append(track_id)
        _execute(conn, f"UPDATE timeline_tracks SET {', '.join(sets)} WHERE id = %s", tuple(vals))
        conn.commit()
        return True
    finally:
        conn.close()


def delete_track(track_id: int) -> bool:
    """Remove a track and all its items (cascades via FK)."""
    conn = get_db()
    try:
        _execute(conn, "DELETE FROM timeline_tracks WHERE id=%s", (track_id,))
        conn.commit()
        return True
    finally:
        conn.close()
