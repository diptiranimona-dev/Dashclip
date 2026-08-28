"""
recommendation_service.py — DashClip V4
AI-powered recommendations based on Creator DNA and project history.
Recommends styles, clips, music, scripts, and improvements.
"""
import json
from db import get_db, execute, fetchone, fetchall
import services.ai_provider_service as ai
import services.creator_brain_service as brain

def ensure_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) DEFAULT 'default',
            project_id INTEGER,
            rec_type VARCHAR(50) NOT NULL,
            title VARCHAR(500),
            description TEXT,
            data JSONB DEFAULT '{}',
            priority INTEGER DEFAULT 5,
            applied BOOLEAN DEFAULT FALSE,
            dismissed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    conn.close()

async def generate_project_recommendations(project_id: int, user_id: str = "default") -> list:
    """Generate AI recommendations for a specific project based on creator history."""
    conn = get_db()
    project = fetchone(conn, "SELECT * FROM projects WHERE id=%s", (project_id,))
    scenes = fetchall(conn, "SELECT * FROM scenes WHERE project_id=%s ORDER BY scene_number", (project_id,))
    conn.close()
    if not project: return []

    dna = brain.get_dna(user_id)
    style_rec = await brain.get_style_recommendation(user_id, project.get("title",""))
    recs = []

    # Recommendation 1: Style match
    current_style = project.get("style_preset","cinematic")
    preferred_style = style_rec.get("recommended_style","cinematic")
    if current_style != preferred_style and style_rec.get("confidence") == "high":
        recs.append({
            "rec_type": "style_suggestion",
            "title": f"Switch to {preferred_style.title()} style",
            "description": f"Based on your {dna.get('total_videos_analyzed',0)} previous videos, you tend to prefer {preferred_style} style.",
            "data": {"suggested_style": preferred_style, "current_style": current_style},
            "priority": 7
        })

    # Recommendation 2: Scene count
    current_count = len(scenes)
    recommended_count = style_rec.get("recommended_scene_count", 10)
    if abs(current_count - recommended_count) > 3:
        recs.append({
            "rec_type": "scene_count",
            "title": f"Adjust to {recommended_count} scenes",
            "description": f"Your videos typically perform best with around {recommended_count} scenes based on your history.",
            "data": {"suggested_count": recommended_count, "current_count": current_count},
            "priority": 5
        })

    # Recommendation 3: Music style
    music_profile = dna.get("music_profile", {})
    preferred_sources = music_profile.get("preferred_sources", [])
    if preferred_sources:
        recs.append({
            "rec_type": "music_suggestion",
            "title": f"Try {preferred_sources[0].title()} for music",
            "description": f"You've had great results using {preferred_sources[0]} for music in past projects.",
            "data": {"suggested_source": preferred_sources[0]},
            "priority": 4
        })

    # Recommendation 4: AI script improvement
    if project.get("script") and len(project.get("script","")) > 100:
        recs.append({
            "rec_type": "script_improvement",
            "title": "Improve script hook",
            "description": "AI can strengthen your opening hook to boost viewer retention.",
            "data": {"action": "improve_hook"},
            "priority": 6
        })

    # Store recommendations
    conn = get_db()
    for rec in recs:
        execute(conn, """
            INSERT INTO recommendations (user_id, project_id, rec_type, title, description, data, priority)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (user_id, project_id, rec["rec_type"], rec["title"],
              rec["description"], json.dumps(rec["data"]), rec["priority"]))
    conn.commit()
    conn.close()
    return recs

def get_recommendations(user_id: str, project_id: int = None) -> list:
    conn = get_db()
    if project_id:
        rows = fetchall(conn, """
            SELECT * FROM recommendations
            WHERE user_id=%s AND project_id=%s AND dismissed=FALSE
            ORDER BY priority DESC, created_at DESC LIMIT 10
        """, (user_id, project_id))
    else:
        rows = fetchall(conn, """
            SELECT * FROM recommendations
            WHERE user_id=%s AND dismissed=FALSE
            ORDER BY priority DESC, created_at DESC LIMIT 20
        """, (user_id,))
    conn.close()
    return rows

def dismiss_recommendation(rec_id: int, user_id: str = "default"):
    conn = get_db()
    execute(conn, "UPDATE recommendations SET dismissed=TRUE WHERE id=%s AND user_id=%s", (rec_id, user_id))
    conn.commit()
    conn.close()

def apply_recommendation(rec_id: int, user_id: str = "default"):
    conn = get_db()
    execute(conn, "UPDATE recommendations SET applied=TRUE WHERE id=%s AND user_id=%s", (rec_id, user_id))
    conn.commit()
    conn.close()

async def get_script_improvement(script: str, style: str = "cinematic", improvement_type: str = "hook") -> str:
    """Use AI to improve a specific part of the script."""
    prompts = {
        "hook": f"Improve only the opening hook of this script to be more compelling and attention-grabbing. Keep everything else the same. Style: {style}\n\nScript:\n{script[:1000]}",
        "cta": f"Improve the call-to-action at the end of this script. Make it more engaging. Style: {style}\n\nScript:\n{script[-500:]}",
        "pacing": f"Suggest 3 specific edits to improve the pacing of this script for {style} style. Be specific about which lines to change.\n\nScript:\n{script[:1500]}",
        "emotion": f"Rewrite this script to be more emotionally engaging while keeping the core information. Style: {style}\n\nScript:\n{script[:1500]}"
    }
    prompt = prompts.get(improvement_type, prompts["hook"])
    return await ai.ask(prompt, timeout=90)

async def suggest_next_video(user_id: str = "default") -> dict:
    """Suggest the next video topic based on creator history."""
    from services.knowledge_service import get_topics
    topics = get_topics(user_id)
    memories = brain.recall_all(user_id)
    topic_prefs = [m["key"] for m in memories.get("topic_preference", [])[:5]]
    style_prefs = [m["key"] for m in memories.get("style_preference", [])[:3]]

    prompt = (
        f"Based on this creator's history:\n"
        f"Previous topics: {', '.join(topic_prefs) if topic_prefs else 'general content'}\n"
        f"Preferred styles: {', '.join(style_prefs) if style_prefs else 'cinematic'}\n\n"
        "Suggest 3 compelling next video topics. Return JSON:\n"
        '{"suggestions": [{"topic": "...", "angle": "...", "style": "...", "why": "..."}, ...]}'
    )
    result = await ai.ask_json(prompt, timeout=60)
    return result if result else {"suggestions": [
        {"topic": "Your next video idea", "angle": "Fresh perspective", "style": "cinematic", "why": "Based on your style"}
    ]}
