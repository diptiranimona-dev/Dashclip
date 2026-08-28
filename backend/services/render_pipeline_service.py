"""
render_pipeline_service.py — DashClip V3 Phase C
Converts a full timeline (tracks + items + effects) into an FFmpeg command.
This is additive — render_service.py (the original concat-based pipeline)
stays operational. This service is used when a project has Phase C
effects/transitions/speed/color applied; otherwise the original simple
pipeline is used. Nothing existing is removed or broken.
"""
import subprocess
from pathlib import Path
from db import get_db, fetchall, fetchone
import services.effect_service as effect_service


def _run(cmd: list[str]):
    return subprocess.run(cmd, capture_output=True, text=True)


def project_has_advanced_edits(project_id: int) -> bool:
    """
    Decide whether a project needs the advanced filter-graph pipeline or can
    just use the original simple concat pipeline. Keeps old projects fast
    and avoids unnecessary complexity when no Phase C features were used.
    """
    conn = get_db()
    rows = fetchall(conn,
        """SELECT ti.id FROM timeline_items ti
           JOIN timeline_tracks tt ON ti.track_id = tt.id
           WHERE tt.project_id=%s AND (
                 ti.speed != 1.0 OR ti.opacity != 1.0 OR
                 ti.color_grade != '{}' OR ti.transform != '{}' OR
                 ti.transition_in != '{}' OR ti.transition_out != '{}'
           )""", (project_id,))
    conn.close()
    has_effects = fetchall(get_db(), """SELECT id FROM effects WHERE item_id IN
        (SELECT ti.id FROM timeline_items ti JOIN timeline_tracks tt ON ti.track_id=tt.id WHERE tt.project_id=%s)
        AND enabled=TRUE""", (project_id,))
    return bool(rows) or bool(has_effects)


def build_clip_filter_chain(item: dict, w: int, h: int) -> str:
    """
    Build the per-clip FFmpeg filter chain: speed, color grade, transform,
    then any custom effects stacked on top — in that order, matching how a
    real editor applies adjustments (timing first, then color, then stylistic effects).
    """
    filters = []

    speed = float(item.get("speed") or 1.0)
    if speed != 1.0:
        filters.append(f"setpts=PTS/{speed:.3f}")

    color_grade = item.get("color_grade") or {}
    if color_grade and any(color_grade.values()):
        cg_filter = effect_service.build_filter("color_grade", color_grade)
        if cg_filter:
            filters.append(cg_filter)

    transform = item.get("transform") or {}
    if transform.get("rotation"):
        rot_filter = effect_service.build_filter("rotate", {"degrees": transform["rotation"]})
        if rot_filter:
            filters.append(rot_filter)

    # Scale/pad to target resolution (always applied, matches existing render_service behavior)
    filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease")
    filters.append(f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black")

    # Custom effect stack (blur, vignette, chroma key, etc.)
    conn = get_db()
    custom_effects = fetchall(conn, "SELECT * FROM effects WHERE item_id=%s AND enabled=TRUE ORDER BY stack_order", (item.get("id"),))
    conn.close()
    for eff in custom_effects:
        f = effect_service.build_filter(eff["effect_type"], eff.get("parameters") or {})
        if f:
            filters.append(f)

    return ",".join(filters)


def build_audio_filter(item: dict) -> str | None:
    """Audio-side filter for speed changes (atempo only supports 0.5-2.0 per instance, chained for outside that range)."""
    speed = float(item.get("speed") or 1.0)
    if speed == 1.0:
        return None
    # atempo chaining for extreme speed values outside its native 0.5-2.0 range
    parts = []
    remaining = speed
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.3f}")
    return ",".join(parts)


def get_transition_xfade_args(item: dict) -> dict | None:
    """Returns xfade parameters if this item has a real (non-cut) transition_in set."""
    trans = item.get("transition_in") or {}
    trans_type = trans.get("type", "cut")
    if trans_type == "cut" or not trans_type:
        return None
    ffmpeg_type = effect_service.get_transition_filter_type(trans_type)
    if not ffmpeg_type:
        return None
    return {
        "transition": ffmpeg_type,
        "duration": float(trans.get("duration", 0.5)),
    }


def get_timeline_for_render(project_id: int) -> dict:
    """
    Pulls the full timeline state needed for an advanced render: tracks,
    items, their effects, in render order.
    """
    conn = get_db()
    tracks = fetchall(conn,
        "SELECT * FROM timeline_tracks WHERE project_id=%s ORDER BY track_index",
        (project_id,))
    for track in tracks:
        items = fetchall(conn,
            "SELECT * FROM timeline_items WHERE track_id=%s ORDER BY start_time",
            (track["id"],))
        for item in items:
            item["effects"] = fetchall(conn,
                "SELECT * FROM effects WHERE item_id=%s AND enabled=TRUE ORDER BY stack_order",
                (item["id"],))
        track["items"] = items
    conn.close()
    return {"project_id": project_id, "tracks": tracks}
