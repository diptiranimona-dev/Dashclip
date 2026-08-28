"""
effect_service.py — DashClip V3 Phase C
Effect library + FFmpeg filter mapping.

This service is the single source of truth for what effects exist, what
parameters they take, and how each one translates into an FFmpeg filter
string. render_pipeline_service.py calls build_filter() to turn a stored
effect (from the `effects` table) into something FFmpeg can actually run.

No effect exists here unless it has a real, working FFmpeg filter behind it —
per the project's zero-placeholder rule.
"""
from db import get_db, execute, fetchall, fetchone


# ─── EFFECT DEFINITIONS ───────────────────────────────────────────────────────
# Each entry defines: default parameters, and a function that builds the
# actual FFmpeg filter string from those parameters.

def _f(v, default=0.0):
    """Safe float coercion for filter params."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


EFFECT_DEFINITIONS = {
    "color_grade": {
        "label": "Color Grade",
        "default_params": {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0, "gamma": 1.0},
        "build": lambda p: (
            f"eq=brightness={_f(p.get('brightness'),0.0):.3f}:"
            f"contrast={_f(p.get('contrast'),1.0):.3f}:"
            f"saturation={_f(p.get('saturation'),1.0):.3f}:"
            f"gamma={_f(p.get('gamma'),1.0):.3f}"
        ),
    },
    "speed": {
        "label": "Speed",
        "default_params": {"factor": 1.0},
        # Speed is handled specially in render_pipeline (affects both video setpts and audio atempo)
        "build": lambda p: f"setpts=PTS/{max(0.1,_f(p.get('factor'),1.0)):.3f}",
    },
    "blur": {
        "label": "Blur",
        "default_params": {"radius": 2},
        "build": lambda p: f"boxblur={int(_f(p.get('radius'),2))}:1",
    },
    "sharpen": {
        "label": "Sharpen",
        "default_params": {"amount": 1.0},
        "build": lambda p: f"unsharp=5:5:{_f(p.get('amount'),1.0):.2f}:5:5:0.0",
    },
    "vignette": {
        "label": "Vignette",
        "default_params": {"angle": 1.2},
        "build": lambda p: f"vignette=angle={_f(p.get('angle'),1.2):.2f}",
    },
    "chroma_key": {
        "label": "Chroma Key (Green Screen)",
        "default_params": {"color": "0x00FF00", "similarity": 0.3, "blend": 0.1},
        "build": lambda p: (
            f"chromakey={p.get('color','0x00FF00')}:"
            f"{_f(p.get('similarity'),0.3):.2f}:{_f(p.get('blend'),0.1):.2f}"
        ),
    },
    "crop": {
        "label": "Crop",
        "default_params": {"w": 1920, "h": 1080, "x": 0, "y": 0},
        "build": lambda p: f"crop={int(_f(p.get('w'),1920))}:{int(_f(p.get('h'),1080))}:{int(_f(p.get('x'),0))}:{int(_f(p.get('y'),0))}",
    },
    "rotate": {
        "label": "Rotate",
        "default_params": {"degrees": 0},
        "build": lambda p: f"rotate={_f(p.get('degrees'),0)*3.14159/180:.4f}:fillcolor=black",
    },
    "zoom_pan": {
        "label": "Ken Burns / Zoom & Pan",
        "default_params": {"zoom_start": 1.0, "zoom_end": 1.2, "duration": 5.0, "fps": 30},
        # zoompan needs frame count, computed at render time when actual duration is known
        "build": lambda p: (
            f"zoompan=z='min(zoom+0.0015,{_f(p.get('zoom_end'),1.2):.3f})':"
            f"d={int(_f(p.get('duration'),5.0)*_f(p.get('fps'),30))}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        ),
    },
    "grayscale": {
        "label": "Grayscale / Monochrome",
        "default_params": {},
        "build": lambda p: "hue=s=0",
    },
    "sepia": {
        "label": "Vintage Sepia",
        "default_params": {},
        "build": lambda p: "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    },
}

TRANSITION_DEFINITIONS = {
    "cut":       {"label": "Cut",         "ffmpeg_type": None},      # no filter — hard cut
    "fade":      {"label": "Fade",        "ffmpeg_type": "fade"},
    "crossfade": {"label": "Crossfade",   "ffmpeg_type": "fade"},
    "wipeleft":  {"label": "Wipe Left",   "ffmpeg_type": "wipeleft"},
    "wiperight": {"label": "Wipe Right",  "ffmpeg_type": "wiperight"},
    "slideup":   {"label": "Slide Up",    "ffmpeg_type": "slideup"},
    "zoom":      {"label": "Zoom",        "ffmpeg_type": "zoomin"},
    "dissolve":  {"label": "Dissolve",    "ffmpeg_type": "dissolve"},
}

COLOR_PRESETS = {
    "cinematic_warm":  {"brightness": 0.02, "contrast": 1.15, "saturation": 0.9,  "gamma": 1.05},
    "cinematic_cool":  {"brightness": -0.02,"contrast": 1.15, "saturation": 0.85, "gamma": 0.95},
    "documentary":     {"brightness": 0.0,  "contrast": 1.05, "saturation": 0.95, "gamma": 1.0},
    "vintage":         {"brightness": 0.05, "contrast": 0.9,  "saturation": 0.7,  "gamma": 1.1},
    "vibrant":         {"brightness": 0.03, "contrast": 1.2,  "saturation": 1.4,  "gamma": 1.0},
    "monochrome":      {"brightness": 0.0,  "contrast": 1.1,  "saturation": 0.0,  "gamma": 1.0},
}

MOTION_PRESETS = {
    "slow_zoom_in":  {"zoom_start": 1.0, "zoom_end": 1.15},
    "fast_zoom_in":  {"zoom_start": 1.0, "zoom_end": 1.4},
    "push_in":       {"zoom_start": 1.0, "zoom_end": 1.1},
    "pull_out":      {"zoom_start": 1.15,"zoom_end": 1.0},
}


# ─── PUBLIC API ───────────────────────────────────────────────────────────────

def get_effect_library() -> dict:
    """Returns the full catalog for the frontend effects panel."""
    return {
        "effects": {k: {"label": v["label"], "default_params": v["default_params"]}
                    for k, v in EFFECT_DEFINITIONS.items()},
        "transitions": {k: v["label"] for k, v in TRANSITION_DEFINITIONS.items()},
        "color_presets": COLOR_PRESETS,
        "motion_presets": MOTION_PRESETS,
    }


def build_filter(effect_type: str, parameters: dict) -> str | None:
    """
    Turns a stored effect into an actual FFmpeg filter string.
    Returns None if the effect type isn't recognized (caller should skip it,
    never crash the render over an unknown effect).
    """
    definition = EFFECT_DEFINITIONS.get(effect_type)
    if not definition:
        print(f"[effect_service] Unknown effect_type '{effect_type}' — skipped")
        return None
    try:
        return definition["build"](parameters or {})
    except Exception as e:
        print(f"[effect_service] Failed to build filter for '{effect_type}': {e}")
        return None


def get_transition_filter_type(transition_name: str) -> str | None:
    """Returns the FFmpeg xfade transition type string, or None for a hard cut."""
    t = TRANSITION_DEFINITIONS.get(transition_name, {})
    return t.get("ffmpeg_type")


def apply_color_preset(preset_name: str) -> dict:
    """Returns the color_grade parameter dict for a named preset."""
    return COLOR_PRESETS.get(preset_name, {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0, "gamma": 1.0})


def apply_motion_preset(preset_name: str) -> dict:
    """Returns the zoom_pan parameter dict for a named motion preset."""
    return MOTION_PRESETS.get(preset_name, {"zoom_start": 1.0, "zoom_end": 1.0})


# ─── DATABASE OPERATIONS ──────────────────────────────────────────────────────

def get_item_effects(item_id: int) -> list[dict]:
    conn = get_db()
    rows = fetchall(conn,
        "SELECT * FROM effects WHERE item_id=%s AND enabled=TRUE ORDER BY stack_order",
        (item_id,))
    conn.close()
    return rows


def add_effect(item_id: int, effect_type: str, parameters: dict | None = None) -> dict:
    if effect_type not in EFFECT_DEFINITIONS:
        raise ValueError(f"Unknown effect type: {effect_type}")
    params = parameters if parameters is not None else EFFECT_DEFINITIONS[effect_type]["default_params"]
    conn = get_db()
    # New effects stack on top — order by current max + 1
    existing = fetchall(conn, "SELECT COALESCE(MAX(stack_order),-1) as m FROM effects WHERE item_id=%s", (item_id,))
    next_order = (existing[0]["m"] if existing else -1) + 1
    row = execute(conn,
        """INSERT INTO effects (item_id, effect_type, parameters, stack_order, enabled)
           VALUES (%s,%s,%s,%s,TRUE) RETURNING *""",
        (item_id, effect_type, params, next_order)
    )
    conn.commit(); conn.close()
    return row


def update_effect(effect_id: int, parameters: dict | None = None, enabled: bool | None = None) -> dict:
    conn = get_db()
    updates, params = [], []
    if parameters is not None:
        updates.append("parameters=%s"); params.append(parameters)
    if enabled is not None:
        updates.append("enabled=%s"); params.append(enabled)
    if not updates:
        existing = fetchone(conn, "SELECT * FROM effects WHERE id=%s", (effect_id,))
        conn.close()
        return existing
    params.append(effect_id)
    row = execute(conn, f"UPDATE effects SET {','.join(updates)} WHERE id=%s RETURNING *", tuple(params))
    conn.commit(); conn.close()
    return row


def delete_effect(effect_id: int):
    conn = get_db()
    execute(conn, "DELETE FROM effects WHERE id=%s", (effect_id,))
    conn.commit(); conn.close()
