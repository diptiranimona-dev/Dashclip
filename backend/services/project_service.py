"""
project_service.py  — DashClip V3 B4
Project CRUD + duplicate.
"""
from db import get_db, fetchone, fetchall, execute


def create_project(title: str = "Untitled Project", script: str = "") -> dict:
    conn = get_db()
    row = execute(conn,
        "INSERT INTO projects (title, script) VALUES (%s,%s) RETURNING *",
        (title, script)
    )
    conn.commit(); conn.close()
    return row


def get_project(project_id: int) -> dict | None:
    conn = get_db()
    project = fetchone(conn, "SELECT * FROM projects WHERE id=%s", (project_id,))
    if not project:
        conn.close(); return None

    scenes = fetchall(conn,
        "SELECT * FROM scenes WHERE project_id=%s ORDER BY scene_number",
        (project_id,))
    for scene in scenes:
        scene["clips"] = fetchall(conn,
            "SELECT * FROM clips WHERE scene_id=%s ORDER BY relevance_score DESC",
            (scene["id"],))

    project["scenes"]       = scenes
    project["voiceovers"]   = fetchall(conn,
        "SELECT * FROM voiceovers WHERE project_id=%s ORDER BY created_at DESC",
        (project_id,))
    project["music_tracks"] = fetchall(conn,
        "SELECT * FROM music_tracks WHERE project_id=%s ORDER BY created_at DESC",
        (project_id,))
    project["subtitles"]    = fetchall(conn,
        "SELECT * FROM subtitles WHERE project_id=%s ORDER BY created_at DESC",
        (project_id,))
    project["render_jobs"]  = fetchall(conn,
        "SELECT * FROM render_jobs WHERE project_id=%s ORDER BY created_at DESC LIMIT 10",
        (project_id,))
    conn.close()
    return project


def list_projects() -> list[dict]:
    conn = get_db()
    rows = fetchall(conn,
        "SELECT id, title, status, style_preset, video_format, created_at, updated_at "
        "FROM projects ORDER BY updated_at DESC NULLS LAST"
    )
    conn.close()
    return rows


def save_project(project_id: int, title: str = None, script: str = None,
                 style_preset: str = None, video_format: str = None) -> dict:
    conn = get_db()
    updates, params = ["updated_at=NOW()"], []
    if title is not None:        updates.append("title=%s");        params.append(title)
    if script is not None:       updates.append("script=%s");       params.append(script)
    if style_preset is not None: updates.append("style_preset=%s"); params.append(style_preset)
    if video_format is not None: updates.append("video_format=%s"); params.append(video_format)
    params.append(project_id)
    row = execute(conn,
        f"UPDATE projects SET {','.join(updates)} WHERE id=%s RETURNING *",
        tuple(params)
    )
    conn.commit(); conn.close()
    return row


def delete_project(project_id: int):
    conn = get_db()
    execute(conn, "DELETE FROM projects WHERE id=%s", (project_id,))
    conn.commit(); conn.close()


def duplicate_project(project_id: int) -> dict:
    """Deep copy: project + scenes + clips (not render jobs, not voiceovers)."""
    conn = get_db()
    orig = fetchone(conn, "SELECT * FROM projects WHERE id=%s", (project_id,))
    if not orig:
        conn.close()
        raise ValueError(f"Project {project_id} not found")

    new_title = f"{orig['title']} (Copy)"
    new_proj = execute(conn,
        """INSERT INTO projects (title, script, style_preset, video_format)
           VALUES (%s,%s,%s,%s) RETURNING *""",
        (new_title, orig.get("script",""),
         orig.get("style_preset","cinematic"),
         orig.get("video_format","landscape"))
    )
    new_id = new_proj["id"]

    # Copy scenes + their clips
    scenes = fetchall(conn,
        "SELECT * FROM scenes WHERE project_id=%s ORDER BY scene_number",
        (project_id,))
    for scene in scenes:
        new_scene = execute(conn,
            """INSERT INTO scenes (project_id, scene_number, description, keywords, duration_hint)
               VALUES (%s,%s,%s,%s,%s) RETURNING id""",
            (new_id, scene["scene_number"], scene["description"],
             scene["keywords"], scene["duration_hint"])
        )
        clips = fetchall(conn,
            "SELECT * FROM clips WHERE scene_id=%s ORDER BY relevance_score DESC",
            (scene["id"],))
        for clip in clips:
            execute(conn,
                """INSERT INTO clips
                   (scene_id, video_url, preview_url, thumbnail_url,
                    duration, width, height, relevance_score, source, selected)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (new_scene["id"], clip["video_url"], clip.get("preview_url"),
                 clip.get("thumbnail_url"), clip.get("duration"),
                 clip.get("width"), clip.get("height"),
                 clip.get("relevance_score", 0),
                 clip.get("source","pexels"),
                 clip.get("selected", False))
            )

    conn.commit(); conn.close()
    return {"new_project_id": new_id, "title": new_title}
