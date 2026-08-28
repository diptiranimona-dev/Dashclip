"""
brand_kit_service.py — DashClip V4
Brand Kit — store creator's visual identity: colors, fonts, tone, logo, intro/outro.
Applied automatically to every new project.
"""
import json
from db import get_db, execute, fetchone, fetchall

def ensure_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS brand_kits (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) DEFAULT 'default',
            kit_name VARCHAR(255) DEFAULT 'My Brand',
            is_active BOOLEAN DEFAULT TRUE,
            primary_color VARCHAR(20) DEFAULT '#f5a623',
            secondary_color VARCHAR(20) DEFAULT '#ffffff',
            background_color VARCHAR(20) DEFAULT '#000000',
            accent_color VARCHAR(20) DEFAULT '#60a5fa',
            font_primary VARCHAR(100) DEFAULT 'Syne',
            font_secondary VARCHAR(100) DEFAULT 'Space Mono',
            logo_url TEXT DEFAULT '',
            watermark_url TEXT DEFAULT '',
            intro_clip_url TEXT DEFAULT '',
            outro_clip_url TEXT DEFAULT '',
            brand_voice VARCHAR(50) DEFAULT 'professional',
            brand_tone VARCHAR(50) DEFAULT 'authoritative',
            default_style VARCHAR(50) DEFAULT 'cinematic',
            default_format VARCHAR(20) DEFAULT 'landscape',
            default_subtitle_style VARCHAR(20) DEFAULT 'minimal',
            subtitle_font_color VARCHAR(20) DEFAULT '#ffffff',
            subtitle_bg_color VARCHAR(20) DEFAULT 'transparent',
            subtitle_font_size INTEGER DEFAULT 22,
            lower_third_style VARCHAR(50) DEFAULT 'minimal',
            channel_name VARCHAR(255) DEFAULT '',
            channel_tagline TEXT DEFAULT '',
            target_audience TEXT DEFAULT '',
            content_pillars TEXT[] DEFAULT '{}',
            banned_topics TEXT[] DEFAULT '{}',
            preferred_music_genres TEXT[] DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    conn.close()

def get_active_kit(user_id: str = "default") -> dict:
    conn = get_db()
    kit = fetchone(conn, "SELECT * FROM brand_kits WHERE user_id=%s AND is_active=TRUE ORDER BY updated_at DESC LIMIT 1", (user_id,))
    conn.close()
    if not kit:
        return _default_kit(user_id)
    return dict(kit)

def _default_kit(user_id: str) -> dict:
    return {
        "user_id": user_id, "kit_name": "Default Brand",
        "primary_color": "#f5a623", "secondary_color": "#ffffff",
        "background_color": "#000000", "accent_color": "#60a5fa",
        "font_primary": "Syne", "font_secondary": "Space Mono",
        "logo_url": "", "watermark_url": "", "intro_clip_url": "", "outro_clip_url": "",
        "brand_voice": "professional", "brand_tone": "authoritative",
        "default_style": "cinematic", "default_format": "landscape",
        "default_subtitle_style": "minimal",
        "subtitle_font_color": "#ffffff", "subtitle_bg_color": "transparent",
        "subtitle_font_size": 22, "lower_third_style": "minimal",
        "channel_name": "", "channel_tagline": "", "target_audience": "",
        "content_pillars": [], "banned_topics": [], "preferred_music_genres": []
    }

def create_or_update_kit(user_id: str, kit_data: dict) -> dict:
    conn = get_db()
    existing = fetchone(conn, "SELECT id FROM brand_kits WHERE user_id=%s AND is_active=TRUE", (user_id,))
    fields = [
        "kit_name", "primary_color", "secondary_color", "background_color", "accent_color",
        "font_primary", "font_secondary", "logo_url", "watermark_url",
        "intro_clip_url", "outro_clip_url", "brand_voice", "brand_tone",
        "default_style", "default_format", "default_subtitle_style",
        "subtitle_font_color", "subtitle_bg_color", "subtitle_font_size",
        "lower_third_style", "channel_name", "channel_tagline", "target_audience",
        "content_pillars", "banned_topics", "preferred_music_genres"
    ]
    if existing:
        sets = []
        vals = []
        for f in fields:
            if f in kit_data:
                sets.append(f"{f}=%s")
                vals.append(kit_data[f])
        if sets:
            vals.append(existing["id"])
            execute(conn, f"UPDATE brand_kits SET {','.join(sets)}, updated_at=NOW() WHERE id=%s", tuple(vals))
        conn.commit()
        conn.close()
        return get_active_kit(user_id)
    else:
        vals = {f: kit_data.get(f) for f in fields if f in kit_data}
        vals["user_id"] = user_id
        cols = list(vals.keys())
        placeholders = ",".join(["%s"] * len(cols))
        execute(conn, f"INSERT INTO brand_kits ({','.join(cols)}) VALUES ({placeholders})", tuple(vals.values()))
        conn.commit()
        conn.close()
        return get_active_kit(user_id)

def apply_brand_to_project(user_id: str, project_id: int):
    """Apply active brand kit settings to a project."""
    kit = get_active_kit(user_id)
    if not kit or kit.get("kit_name") == "Default Brand": return
    conn = get_db()
    execute(conn, """
        UPDATE projects SET
            style_preset=COALESCE(NULLIF(style_preset,'cinematic'), %s),
            video_format=COALESCE(NULLIF(video_format,'landscape'), %s),
            updated_at=NOW()
        WHERE id=%s
    """, (kit.get("default_style","cinematic"), kit.get("default_format","landscape"), project_id))
    conn.commit()
    conn.close()

def get_all_kits(user_id: str = "default") -> list:
    conn = get_db()
    kits = fetchall(conn, "SELECT * FROM brand_kits WHERE user_id=%s ORDER BY updated_at DESC", (user_id,))
    conn.close()
    return kits
