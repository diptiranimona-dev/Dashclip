"""
template_service.py — DashClip V4
Per-user templates + public system templates.
Global template performance tracking — app learns which templates produce best videos.
"""
import json
from db import get_db, execute, fetchall, fetchone

def ensure_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS video_templates (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) DEFAULT 'system',
            name VARCHAR(255) NOT NULL,
            description TEXT DEFAULT '',
            category VARCHAR(50) DEFAULT 'general',
            is_public BOOLEAN DEFAULT FALSE,
            is_system BOOLEAN DEFAULT FALSE,
            style VARCHAR(50) DEFAULT 'cinematic',
            format VARCHAR(50) DEFAULT 'landscape',
            content_format VARCHAR(20) DEFAULT 'longform',
            content_type VARCHAR(50) DEFAULT 'storytelling',
            default_scene_count INTEGER DEFAULT 10,
            default_duration_hint FLOAT DEFAULT 6.0,
            script_template TEXT DEFAULT '',
            voiceover_tone VARCHAR(50) DEFAULT 'professional',
            music_mood VARCHAR(100) DEFAULT 'ambient',
            tags TEXT[] DEFAULT '{}',
            use_count INTEGER DEFAULT 0,
            success_rate FLOAT DEFAULT 0.0,
            avg_quality_score FLOAT DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS template_usage (
            id SERIAL PRIMARY KEY,
            template_id INTEGER REFERENCES video_templates(id) ON DELETE CASCADE,
            user_id VARCHAR(100),
            project_id INTEGER,
            quality_score FLOAT DEFAULT 0,
            render_success BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit(); conn.close()

# 20 built-in system templates — diverse, high quality
SYSTEM_TEMPLATES = [
    # Documentary
    {"name": "Dark Documentary", "category": "documentary", "style": "dark",
     "content_type": "documentary", "content_format": "longform",
     "default_scene_count": 12, "default_duration_hint": 7.0,
     "description": "Moody, high-contrast documentary style. Perfect for true crime, history, mysteries.",
     "voiceover_tone": "authoritative", "music_mood": "dark ambient tension",
     "tags": ["documentary","dark","cinematic","history"]},
    {"name": "YouTube Documentary", "category": "documentary", "style": "youtube",
     "content_type": "documentary", "content_format": "longform",
     "default_scene_count": 10, "default_duration_hint": 6.0,
     "description": "Energetic documentary for YouTube. Fast cuts, engaging narration.",
     "voiceover_tone": "engaging", "music_mood": "upbeat documentary",
     "tags": ["youtube","documentary","engaging"]},
    # Educational
    {"name": "Educational Explainer", "category": "educational", "style": "educational",
     "content_type": "educational", "content_format": "longform",
     "default_scene_count": 8, "default_duration_hint": 5.0,
     "description": "Clear step-by-step educational content. Great for tutorials and how-tos.",
     "voiceover_tone": "friendly teacher", "music_mood": "calm focus",
     "tags": ["educational","tutorial","explainer"]},
    {"name": "Science Deep Dive", "category": "educational", "style": "science",
     "content_type": "science", "content_format": "longform",
     "default_scene_count": 10, "default_duration_hint": 7.0,
     "description": "Scientific explanations with wonder and accuracy.",
     "voiceover_tone": "curious", "music_mood": "ambient electronic",
     "tags": ["science","educational","discovery"]},
    # Short Form
    {"name": "TikTok Viral Short", "category": "shortform", "style": "energetic",
     "content_type": "storytelling", "content_format": "shortform",
     "default_scene_count": 8, "default_duration_hint": 3.0,
     "description": "Fast-paced viral short for TikTok and Reels. Hook in first 2 seconds.",
     "voiceover_tone": "energetic fast", "music_mood": "trending upbeat",
     "tags": ["tiktok","viral","shortform","reels"]},
    {"name": "Instagram Reel", "category": "shortform", "style": "minimal",
     "content_type": "storytelling", "content_format": "shortform",
     "default_scene_count": 6, "default_duration_hint": 3.0,
     "description": "Clean aesthetic reel for Instagram. Minimal text, strong visuals.",
     "voiceover_tone": "calm", "music_mood": "aesthetic chill",
     "tags": ["instagram","reel","aesthetic","shortform"]},
    # Storytelling
    {"name": "Cinematic Story", "category": "storytelling", "style": "cinematic",
     "content_type": "storytelling", "content_format": "longform",
     "default_scene_count": 12, "default_duration_hint": 7.0,
     "description": "Hollywood-style cinematic storytelling with dramatic pacing.",
     "voiceover_tone": "dramatic", "music_mood": "cinematic orchestral",
     "tags": ["cinematic","story","dramatic"]},
    {"name": "Mini Documentary Story", "category": "storytelling", "style": "documentary",
     "content_type": "storytelling", "content_format": "longform",
     "default_scene_count": 10, "default_duration_hint": 6.0,
     "description": "Real story told in documentary style. Rise and fall narratives.",
     "voiceover_tone": "journalist", "music_mood": "documentary atmospheric",
     "tags": ["documentary","story","biography"]},
    # Business
    {"name": "Corporate Brand Video", "category": "business", "style": "business",
     "content_type": "business", "content_format": "longform",
     "default_scene_count": 8, "default_duration_hint": 5.0,
     "description": "Professional brand video for LinkedIn and corporate use.",
     "voiceover_tone": "professional confident", "music_mood": "corporate motivational",
     "tags": ["business","corporate","brand","linkedin"]},
    {"name": "Product Launch", "category": "business", "style": "luxury",
     "content_type": "business", "content_format": "longform",
     "default_scene_count": 8, "default_duration_hint": 5.0,
     "description": "Sleek product showcase with luxury aesthetic.",
     "voiceover_tone": "premium", "music_mood": "luxury ambient",
     "tags": ["product","launch","luxury","marketing"]},
    # Technology
    {"name": "Tech Review", "category": "technology", "style": "technology",
     "content_type": "technology", "content_format": "longform",
     "default_scene_count": 10, "default_duration_hint": 6.0,
     "description": "Modern tech review format with specs, demos and verdict.",
     "voiceover_tone": "tech expert", "music_mood": "electronic modern",
     "tags": ["tech","review","gadget","modern"]},
    {"name": "AI & Future Tech", "category": "technology", "style": "science",
     "content_type": "technology", "content_format": "longform",
     "default_scene_count": 10, "default_duration_hint": 7.0,
     "description": "Futuristic tech content about AI, robotics, and innovation.",
     "voiceover_tone": "futuristic", "music_mood": "futuristic electronic",
     "tags": ["ai","future","technology","innovation"]},
    # History
    {"name": "History Deep Dive", "category": "history", "style": "history",
     "content_type": "history", "content_format": "longform",
     "default_scene_count": 12, "default_duration_hint": 7.0,
     "description": "Chronological historical content with period-appropriate visuals.",
     "voiceover_tone": "historian", "music_mood": "orchestral period",
     "tags": ["history","documentary","chronological"]},
    {"name": "Rise and Fall", "category": "history", "style": "documentary",
     "content_type": "documentary", "content_format": "longform",
     "default_scene_count": 12, "default_duration_hint": 8.0,
     "description": "The classic rise-and-fall narrative. Empires, companies, celebrities.",
     "voiceover_tone": "dramatic journalist", "music_mood": "epic dramatic",
     "tags": ["rise","fall","documentary","epic"]},
    # Travel
    {"name": "Travel Vlog", "category": "travel", "style": "travel",
     "content_type": "travel", "content_format": "longform",
     "default_scene_count": 10, "default_duration_hint": 6.0,
     "description": "Immersive travel content that transports viewers.",
     "voiceover_tone": "adventurous", "music_mood": "world music adventure",
     "tags": ["travel","vlog","adventure","explore"]},
    # Motivational
    {"name": "Motivational Speech", "category": "motivational", "style": "cinematic",
     "content_type": "storytelling", "content_format": "longform",
     "default_scene_count": 8, "default_duration_hint": 6.0,
     "description": "Inspiring motivational content with powerful visuals.",
     "voiceover_tone": "inspiring passionate", "music_mood": "epic inspiring",
     "tags": ["motivational","inspiring","speech"]},
    {"name": "Success Story", "category": "motivational", "style": "youtube",
     "content_type": "storytelling", "content_format": "longform",
     "default_scene_count": 10, "default_duration_hint": 6.0,
     "description": "Real success stories told with energy and inspiration.",
     "voiceover_tone": "energetic inspiring", "music_mood": "uplifting motivational",
     "tags": ["success","story","motivational","youtube"]},
    # News/Current
    {"name": "News Explainer", "category": "news", "style": "documentary",
     "content_type": "educational", "content_format": "longform",
     "default_scene_count": 8, "default_duration_hint": 5.0,
     "description": "Breaking down complex news and current events clearly.",
     "voiceover_tone": "journalist neutral", "music_mood": "news background",
     "tags": ["news","explainer","current events"]},
    # Luxury
    {"name": "Luxury Lifestyle", "category": "lifestyle", "style": "luxury",
     "content_type": "storytelling", "content_format": "longform",
     "default_scene_count": 8, "default_duration_hint": 6.0,
     "description": "Premium lifestyle content with elegant pacing.",
     "voiceover_tone": "premium smooth", "music_mood": "luxury jazz lounge",
     "tags": ["luxury","lifestyle","premium","elegant"]},
    # Tutorial
    {"name": "Step-by-Step Tutorial", "category": "tutorial", "style": "educational",
     "content_type": "educational", "content_format": "longform",
     "default_scene_count": 8, "default_duration_hint": 5.0,
     "description": "Clear numbered steps for any how-to topic.",
     "voiceover_tone": "clear instructional", "music_mood": "calm background",
     "tags": ["tutorial","howto","educational","steps"]},
]

def seed_builtin_templates():
    """Seed system templates once — skip if already exist."""
    conn = get_db()
    existing = fetchone(conn, "SELECT COUNT(*) as c FROM video_templates WHERE is_system=TRUE", ())
    if existing and existing.get("c", 0) >= len(SYSTEM_TEMPLATES):
        conn.close()
        return
    for t in SYSTEM_TEMPLATES:
        try:
            execute(conn, """
                INSERT INTO video_templates
                (user_id, name, description, category, is_public, is_system,
                 style, format, content_format, content_type,
                 default_scene_count, default_duration_hint,
                 voiceover_tone, music_mood, tags)
                VALUES ('system',%s,%s,%s,TRUE,TRUE,%s,'landscape',%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING
            """, (t["name"], t.get("description",""), t.get("category","general"),
                  t.get("style","cinematic"), t.get("content_format","longform"),
                  t.get("content_type","storytelling"),
                  t.get("default_scene_count",10), t.get("default_duration_hint",6.0),
                  t.get("voiceover_tone","professional"), t.get("music_mood","ambient"),
                  t.get("tags",[])))
        except Exception as e:
            print(f"[templates] seed error for {t['name']}: {e}")
    conn.commit(); conn.close()
    print(f"[templates] Seeded {len(SYSTEM_TEMPLATES)} system templates")

def get_templates(user_id: str = "default", category: str = None) -> list:
    """Get templates: user's own + system templates. Per-user view."""
    conn = get_db()
    if category:
        rows = fetchall(conn, """
            SELECT * FROM video_templates
            WHERE (user_id=%s OR is_system=TRUE)
            AND category=%s
            ORDER BY is_system ASC, use_count DESC, created_at DESC
        """, (user_id, category))
    else:
        rows = fetchall(conn, """
            SELECT * FROM video_templates
            WHERE user_id=%s OR is_system=TRUE
            ORDER BY is_system ASC, use_count DESC, created_at DESC
        """, (user_id,))
    conn.close()
    return rows

def get_template(template_id: int) -> dict | None:
    conn = get_db()
    t = fetchone(conn, "SELECT * FROM video_templates WHERE id=%s", (template_id,))
    conn.close()
    return t

def create_template(user_id: str, data: dict) -> dict:
    conn = get_db()
    row = execute(conn, """
        INSERT INTO video_templates
        (user_id, name, description, category, is_public, style, format,
         content_format, content_type, default_scene_count, default_duration_hint,
         script_template, voiceover_tone, music_mood, tags)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (user_id, data.get("name","My Template"), data.get("description",""),
          data.get("category","general"), data.get("is_public", False),
          data.get("style","cinematic"), data.get("format","landscape"),
          data.get("content_format","longform"), data.get("content_type","storytelling"),
          data.get("default_scene_count",10), data.get("default_duration_hint",6.0),
          data.get("script_template",""), data.get("voiceover_tone","professional"),
          data.get("music_mood","ambient"), data.get("tags",[])))
    conn.commit(); conn.close()
    return {"id": row["id"], **data}

def apply_template_to_project(template_id: int, project_id: int) -> bool:
    conn = get_db()
    t = fetchone(conn, "SELECT * FROM video_templates WHERE id=%s", (template_id,))
    if not t: conn.close(); return False
    execute(conn, """
        UPDATE projects SET
            style_preset=%s, video_format=%s, content_format=%s,
            updated_at=NOW()
        WHERE id=%s
    """, (t.get("style","cinematic"), t.get("format","landscape"),
          t.get("content_format","longform"), project_id))
    # Track usage
    execute(conn, """
        UPDATE video_templates SET use_count=use_count+1, updated_at=NOW()
        WHERE id=%s
    """, (template_id,))
    conn.commit(); conn.close()
    return True

def save_project_as_template(project_id: int, user_id: str,
                              name: str, description: str = "") -> dict:
    conn = get_db()
    p = fetchone(conn, "SELECT * FROM projects WHERE id=%s", (project_id,))
    if not p: conn.close(); return {}
    row = execute(conn, """
        INSERT INTO video_templates
        (user_id, name, description, category, is_public, style, format,
         content_format, default_scene_count)
        VALUES (%s,%s,%s,'custom',FALSE,%s,%s,%s,10) RETURNING id
    """, (user_id, name, description,
          p.get("style_preset","cinematic"), p.get("video_format","landscape"),
          p.get("content_format","longform")))
    conn.commit(); conn.close()
    return {"id": row["id"], "name": name}

def delete_template(template_id: int, user_id: str):
    conn = get_db()
    # Only delete user's own templates, not system ones
    execute(conn, """
        DELETE FROM video_templates
        WHERE id=%s AND user_id=%s AND is_system=FALSE
    """, (template_id, user_id))
    conn.commit(); conn.close()

def record_template_result(template_id: int, user_id: str,
                            project_id: int, quality_score: float,
                            render_success: bool):
    """Global learning: track which templates produce best results."""
    conn = get_db()
    execute(conn, """
        INSERT INTO template_usage (template_id, user_id, project_id, quality_score, render_success)
        VALUES (%s,%s,%s,%s,%s)
    """, (template_id, user_id, project_id, quality_score, render_success))
    # Update template aggregate stats
    stats = fetchone(conn, """
        SELECT AVG(quality_score) as avg_q, 
               SUM(CASE WHEN render_success THEN 1 ELSE 0 END)::float/COUNT(*) as sr
        FROM template_usage WHERE template_id=%s
    """, (template_id,))
    if stats:
        execute(conn, """
            UPDATE video_templates SET
                avg_quality_score=%s, success_rate=%s, updated_at=NOW()
            WHERE id=%s
        """, (stats.get("avg_q",0), stats.get("sr",0), template_id))
    conn.commit(); conn.close()

def get_best_templates(category: str = None, limit: int = 5) -> list:
    """Global learning: return templates ranked by real user success rate."""
    conn = get_db()
    if category:
        rows = fetchall(conn, """
            SELECT * FROM video_templates
            WHERE (is_system=TRUE OR is_public=TRUE)
            AND category=%s AND use_count > 0
            ORDER BY success_rate DESC, avg_quality_score DESC, use_count DESC
            LIMIT %s
        """, (category, limit))
    else:
        rows = fetchall(conn, """
            SELECT * FROM video_templates
            WHERE (is_system=TRUE OR is_public=TRUE) AND use_count > 0
            ORDER BY success_rate DESC, avg_quality_score DESC, use_count DESC
            LIMIT %s
        """, (limit,))
    conn.close()
    return rows
