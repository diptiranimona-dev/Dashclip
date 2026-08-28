"""
analytics_service.py — DashClip V4
Creator analytics — project quality scores, performance tracking, insights.
"""
import json
from db import get_db, execute, fetchone, fetchall
import services.ai_provider_service as ai

def ensure_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS project_quality_scores (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            user_id VARCHAR(100) DEFAULT 'default',
            script_quality FLOAT DEFAULT 0,
            visual_quality FLOAT DEFAULT 0,
            audio_quality FLOAT DEFAULT 0,
            pacing_score FLOAT DEFAULT 0,
            keyword_relevance FLOAT DEFAULT 0,
            overall_score FLOAT DEFAULT 0,
            ai_feedback TEXT DEFAULT '',
            improvement_tips JSONB DEFAULT '[]',
            scored_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS render_history (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            user_id VARCHAR(100) DEFAULT 'default',
            render_duration_seconds FLOAT DEFAULT 0,
            output_file_size_mb FLOAT DEFAULT 0,
            clip_count INTEGER DEFAULT 0,
            has_voiceover BOOLEAN DEFAULT FALSE,
            has_music BOOLEAN DEFAULT FALSE,
            has_subtitles BOOLEAN DEFAULT FALSE,
            video_format VARCHAR(20) DEFAULT 'landscape',
            success BOOLEAN DEFAULT FALSE,
            error_message TEXT DEFAULT '',
            rendered_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    conn.close()

async def score_project(project_id: int, user_id: str = "default") -> dict:
    """AI-powered project quality scoring."""
    conn = get_db()
    project = fetchone(conn, "SELECT * FROM projects WHERE id=%s", (project_id,))
    scenes = fetchall(conn, "SELECT * FROM scenes WHERE project_id=%s", (project_id,))
    clips_selected = fetchall(conn, """
        SELECT c.* FROM clips c JOIN scenes s ON c.scene_id=s.id
        WHERE s.project_id=%s AND c.selected=TRUE
    """, (project_id,))
    voiceovers = fetchall(conn, "SELECT * FROM voiceovers WHERE project_id=%s", (project_id,))
    music = fetchall(conn, "SELECT * FROM music_tracks WHERE project_id=%s AND selected=TRUE", (project_id,))
    conn.close()

    if not project: return {}

    script = project.get("script","")
    scene_count = len(scenes)
    clip_count = len(clips_selected)
    has_voice = len(voiceovers) > 0
    has_music = len(music) > 0

    # Score components
    script_quality = min(100, len(script.split()) / 5) if script else 0
    visual_quality = (clip_count / max(scene_count,1)) * 100 if scene_count else 0
    audio_quality = (50 if has_voice else 0) + (50 if has_music else 0)

    # Pacing score
    if scenes:
        durations = [s.get("duration_hint",6) for s in scenes]
        avg_dur = sum(durations) / len(durations)
        pacing_score = 100 - abs(avg_dur - 6) * 10
        pacing_score = max(0, min(100, pacing_score))
    else:
        pacing_score = 0

    # Keyword relevance
    all_kw = []
    for s in scenes:
        kw = s.get("keywords") or []
        all_kw.extend(kw)
    unique_ratio = len(set(all_kw)) / max(len(all_kw),1)
    keyword_relevance = unique_ratio * 100

    overall = (script_quality * 0.25 + visual_quality * 0.30 + audio_quality * 0.20 +
               pacing_score * 0.15 + keyword_relevance * 0.10)
    overall = round(overall, 1)

    tips = []
    if script_quality < 50: tips.append("Add more detail to your script for better scene generation")
    if visual_quality < 80: tips.append("Select clips for all scenes before rendering")
    if not has_voice: tips.append("Add voiceover narration to increase engagement")
    if not has_music: tips.append("Background music significantly improves viewer retention")
    if keyword_relevance < 60: tips.append("Diversify keywords across scenes for better clip variety")

    # Store score
    conn = get_db()
    execute(conn, """
        INSERT INTO project_quality_scores
        (project_id, user_id, script_quality, visual_quality, audio_quality,
         pacing_score, keyword_relevance, overall_score, improvement_tips)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, (project_id, user_id, script_quality, visual_quality, audio_quality,
          pacing_score, keyword_relevance, overall, json.dumps(tips)))
    conn.commit()
    conn.close()

    return {
        "project_id": project_id,
        "scores": {
            "script_quality": round(script_quality, 1),
            "visual_quality": round(visual_quality, 1),
            "audio_quality": round(audio_quality, 1),
            "pacing_score": round(pacing_score, 1),
            "keyword_relevance": round(keyword_relevance, 1),
            "overall": overall
        },
        "tips": tips,
        "grade": "A" if overall >= 85 else "B" if overall >= 70 else "C" if overall >= 55 else "D"
    }

def get_creator_stats(user_id: str = "default") -> dict:
    conn = get_db()
    analytics = fetchall(conn, "SELECT * FROM creator_analytics WHERE user_id=%s ORDER BY created_at DESC LIMIT 50", (user_id,))
    render_hist = fetchall(conn, "SELECT * FROM render_history WHERE user_id=%s ORDER BY rendered_at DESC LIMIT 20", (user_id,))
    quality_scores = fetchall(conn, "SELECT * FROM project_quality_scores WHERE user_id=%s ORDER BY scored_at DESC LIMIT 20", (user_id,))
    conn.close()

    total_videos = len(analytics)
    if not total_videos:
        return {"total_videos": 0, "message": "No videos yet. Create your first video to see analytics."}

    avg_scenes = sum(a.get("scene_count",0) for a in analytics) / total_videos
    styles_used = {}
    for a in analytics:
        s = a.get("video_style","cinematic")
        styles_used[s] = styles_used.get(s,0) + 1
    dominant_style = max(styles_used, key=styles_used.get) if styles_used else "cinematic"

    avg_quality = sum(q.get("overall_score",0) for q in quality_scores) / max(len(quality_scores),1)
    successful_renders = sum(1 for r in render_hist if r.get("success"))

    return {
        "total_videos": total_videos,
        "avg_scenes_per_video": round(avg_scenes, 1),
        "dominant_style": dominant_style,
        "styles_breakdown": styles_used,
        "avg_quality_score": round(avg_quality, 1),
        "successful_renders": successful_renders,
        "total_renders": len(render_hist),
        "render_success_rate": round(successful_renders / max(len(render_hist),1) * 100, 1)
    }

def log_render(project_id: int, user_id: str, duration: float, file_size_mb: float,
               clip_count: int, has_voice: bool, has_music: bool, has_subs: bool,
               video_format: str, success: bool, error: str = ""):
    conn = get_db()
    execute(conn, """
        INSERT INTO render_history
        (project_id, user_id, render_duration_seconds, output_file_size_mb,
         clip_count, has_voiceover, has_music, has_subtitles, video_format, success, error_message)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (project_id, user_id, duration, file_size_mb, clip_count,
          has_voice, has_music, has_subs, video_format, success, error))
    conn.commit()
    conn.close()
