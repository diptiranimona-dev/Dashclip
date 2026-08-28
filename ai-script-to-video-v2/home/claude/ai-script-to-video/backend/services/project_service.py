"""
project_service.py
Handles project creation, saving, loading, and full project state.
"""
from db import get_db, fetchone, fetchall, execute


def create_project(title: str = "Untitled Project", script: str = "") -> dict:
    conn = get_db()
    row = execute(conn,
        "INSERT INTO projects (title, script) VALUES (%s, %s) RETURNING *",
        (title, script)
    )
    conn.commit()
    conn.close()
    return row


def get_project(project_id: int) -> dict | None:
    conn = get_db()
    project = fetchone(conn, "SELECT * FROM projects WHERE id = %s", (project_id,))
    if not project:
        conn.close()
        return None

    scenes = fetchall(conn,
        "SELECT * FROM scenes WHERE project_id = %s ORDER BY scene_number",
        (project_id,)
    )
    for scene in scenes:
        scene["clips"] = fetchall(conn,
            "SELECT * FROM clips WHERE scene_id = %s ORDER BY relevance_score DESC",
            (scene["id"],)
        )

    project["scenes"] = scenes
    project["voiceovers"] = fetchall(conn,
        "SELECT * FROM voiceovers WHERE project_id = %s ORDER BY created_at DESC",
        (project_id,)
    )
    project["music_tracks"] = fetchall(conn,
        "SELECT * FROM music_tracks WHERE project_id = %s ORDER BY created_at DESC",
        (project_id,)
    )
    project["subtitles"] = fetchall(conn,
        "SELECT * FROM subtitles WHERE project_id = %s ORDER BY created_at DESC",
        (project_id,)
    )
    project["render_jobs"] = fetchall(conn,
        "SELECT * FROM render_jobs WHERE project_id = %s ORDER BY created_at DESC LIMIT 10",
        (project_id,)
    )
    conn.close()
    return project


def list_projects() -> list[dict]:
    conn = get_db()
    rows = fetchall(conn,
        "SELECT id, title, status, created_at, updated_at FROM projects ORDER BY updated_at DESC"
    )
    conn.close()
    return rows


def save_project(project_id: int, title: str = None, script: str = None) -> dict:
    conn = get_db()
    updates = []
    params = []
    if title is not None:
        updates.append("title = %s")
        params.append(title)
    if script is not None:
        updates.append("script = %s")
        params.append(script)
    updates.append("updated_at = NOW()")
    params.append(project_id)

    row = execute(conn,
        f"UPDATE projects SET {', '.join(updates)} WHERE id = %s RETURNING *",
        tuple(params)
    )
    conn.commit()
    conn.close()
    return row


def delete_project(project_id: int):
    conn = get_db()
    execute(conn, "DELETE FROM projects WHERE id = %s", (project_id,))
    conn.commit()
    conn.close()
