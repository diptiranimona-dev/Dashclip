"""
creator_brain_service.py — DashClip V4
Improved Creator Brain with real global learning.
Personal: learns YOUR style after every render.
Global: aggregates patterns from all users to improve default suggestions.
"""
import json, os
from db import get_db, execute, fetchall, fetchone
import services.ai_provider_service as ai

def ensure_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS creator_memories (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) DEFAULT 'default',
            memory_type VARCHAR(50),
            memory_key VARCHAR(255),
            memory_value JSONB DEFAULT '{}',
            confidence FLOAT DEFAULT 0.5,
            use_count INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, memory_type, memory_key)
        );
        CREATE TABLE IF NOT EXISTS creator_dna (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) UNIQUE DEFAULT 'default',
            overall_style VARCHAR(50) DEFAULT 'unknown',
            visual_profile JSONB DEFAULT '{}',
            pacing_profile JSONB DEFAULT '{}',
            music_profile JSONB DEFAULT '{}',
            topic_profile JSONB DEFAULT '{}',
            editing_profile JSONB DEFAULT '{}',
            total_videos_analyzed INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS global_learning (
            id SERIAL PRIMARY KEY,
            signal_type VARCHAR(50),
            signal_key VARCHAR(255),
            signal_value JSONB DEFAULT '{}',
            total_users INTEGER DEFAULT 0,
            total_occurrences INTEGER DEFAULT 0,
            avg_quality_score FLOAT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(signal_type, signal_key)
        );
        CREATE TABLE IF NOT EXISTS project_learning_events (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100),
            project_id INTEGER,
            style VARCHAR(50),
            content_type VARCHAR(50),
            scene_count INTEGER,
            total_duration FLOAT,
            music_source VARCHAR(50),
            render_success BOOLEAN,
            quality_score FLOAT DEFAULT 0,
            topic_keywords TEXT[] DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    # Safe alters
    for stmt in [
        "ALTER TABLE creator_memories ADD COLUMN IF NOT EXISTS use_count INTEGER DEFAULT 1",
        "ALTER TABLE creator_dna ADD COLUMN IF NOT EXISTS editing_profile JSONB DEFAULT '{}'",
        "ALTER TABLE creator_dna ADD COLUMN IF NOT EXISTS topic_profile JSONB DEFAULT '{}'",
    ]:
        try: cur.execute(stmt)
        except Exception: pass
    conn.commit(); conn.close()

# ── PERSONAL MEMORY ───────────────────────────────────────────────────────────

def remember(user_id: str, memory_type: str, memory_key: str,
             memory_value: dict, confidence: float = 0.7):
    conn = get_db()
    execute(conn, """
        INSERT INTO creator_memories (user_id, memory_type, memory_key, memory_value, confidence)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (user_id, memory_type, memory_key)
        DO UPDATE SET memory_value=%s, confidence=%s,
                      use_count=creator_memories.use_count+1,
                      updated_at=NOW()
    """, (user_id, memory_type, memory_key,
          json.dumps(memory_value), confidence,
          json.dumps(memory_value), confidence))
    conn.commit(); conn.close()

def recall(user_id: str, memory_type: str) -> list:
    conn = get_db()
    rows = fetchall(conn, """
        SELECT * FROM creator_memories
        WHERE user_id=%s AND memory_type=%s
        ORDER BY confidence DESC, use_count DESC
    """, (user_id, memory_type))
    conn.close()
    return rows

def recall_all(user_id: str) -> dict:
    conn = get_db()
    rows = fetchall(conn,
        "SELECT * FROM creator_memories WHERE user_id=%s ORDER BY memory_type, confidence DESC",
        (user_id,))
    conn.close()
    grouped = {}
    for r in rows:
        mt = r.get("memory_type","unknown")
        if mt not in grouped: grouped[mt] = []
        grouped[mt].append(r)
    return grouped

def forget(user_id: str, memory_type: str, memory_key: str):
    conn = get_db()
    execute(conn, """
        DELETE FROM creator_memories
        WHERE user_id=%s AND memory_type=%s AND memory_key=%s
    """, (user_id, memory_type, memory_key))
    conn.commit(); conn.close()

def track_clip_accepted(user_id: str, project_id: int, clip: dict):
    remember(user_id, "clip_preference", clip.get("source","?"),
             {"source": clip.get("source"), "width": clip.get("width"),
              "height": clip.get("height"), "accepted": True}, 0.8)

def track_clip_rejected(user_id: str, project_id: int, clip: dict):
    conn = get_db()
    execute(conn, """
        INSERT INTO creator_memories (user_id, memory_type, memory_key, memory_value, confidence)
        VALUES (%s,'clip_rejection',%s,%s,0.6)
        ON CONFLICT (user_id, memory_type, memory_key)
        DO UPDATE SET use_count=creator_memories.use_count+1, updated_at=NOW()
    """, (user_id, clip.get("source","?"), json.dumps({"rejected": True})))
    conn.commit(); conn.close()

# ── LEARN FROM PROJECT ────────────────────────────────────────────────────────

async def learn_from_project(project_id: int, user_id: str = "default"):
    """Called after every render. Learns style, pacing, music, topics."""
    conn = get_db()
    proj = fetchone(conn, "SELECT * FROM projects WHERE id=%s", (project_id,))
    if not proj: conn.close(); return

    scenes = fetchall(conn, "SELECT * FROM scenes WHERE project_id=%s ORDER BY scene_number", (project_id,))
    selected_clips = fetchall(conn, """
        SELECT c.* FROM clips c
        JOIN scenes s ON c.scene_id = s.id
        WHERE s.project_id=%s AND c.selected=TRUE
    """, (project_id,))
    music = fetchone(conn, "SELECT * FROM music_tracks WHERE project_id=%s AND selected=TRUE", (project_id,))
    render = fetchone(conn, "SELECT * FROM render_jobs WHERE project_id=%s ORDER BY created_at DESC LIMIT 1", (project_id,))
    conn.close()

    style = proj.get("style_preset","cinematic")
    content_format = proj.get("content_format","longform")
    scene_count = len(scenes)
    avg_dur = sum(s.get("duration_hint",6) for s in scenes) / max(scene_count,1)
    render_success = (render.get("status") == "completed") if render else False

    # Extract topic keywords from script
    script = proj.get("script","") or ""
    import re
    words = re.findall(r'\b[A-Za-z]{5,}\b', script)
    stop = {"the","and","that","this","with","from","have","been","will","they",
            "their","your","what","when","where","which","scene","video","narrator"}
    topic_kw = list(dict.fromkeys(
        w.lower() for w in words if w.lower() not in stop
    ))[:10]

    # Save learning event
    conn = get_db()
    execute(conn, """
        INSERT INTO project_learning_events
        (user_id, project_id, style, content_type, scene_count,
         total_duration, music_source, render_success, topic_keywords)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (user_id, project_id, style,
          proj.get("content_format","longform"), scene_count,
          avg_dur * scene_count,
          music.get("source","none") if music else "none",
          render_success, topic_kw))
    conn.commit(); conn.close()

    # Personal memories
    remember(user_id, "style_preference", style,
             {"style": style, "count": 1, "format": content_format}, 0.8)
    remember(user_id, "pacing_preference", f"scenes_{scene_count}",
             {"scene_count": scene_count, "avg_duration": round(avg_dur,2)}, 0.7)
    if music:
        remember(user_id, "music_preference", music.get("source","unknown"),
                 {"source": music.get("source"), "title": music.get("title","")}, 0.75)
    for kw in topic_kw[:5]:
        remember(user_id, "topic_interest", kw, {"topic": kw, "style": style}, 0.6)

    # Clip source preferences
    clip_sources = {}
    for c in selected_clips:
        src = c.get("source","?")
        clip_sources[src] = clip_sources.get(src,0) + 1
    for src, count in clip_sources.items():
        remember(user_id, "clip_source_preference", src,
                 {"source": src, "selection_count": count}, 0.7)

    # Update global learning
    await _update_global_learning(style, content_format, scene_count,
                                   music.get("source","none") if music else "none",
                                   render_success, topic_kw)

    # Rebuild DNA
    await rebuild_dna(user_id)
    print(f"[brain] Learned from project {project_id} for user {user_id}")

# ── GLOBAL LEARNING ───────────────────────────────────────────────────────────

async def _update_global_learning(style: str, content_format: str,
                                   scene_count: int, music_source: str,
                                   render_success: bool, topic_keywords: list):
    """
    Global learning: aggregate patterns from all users.
    Tracks which styles, scene counts, music sources produce successful renders.
    This data improves DEFAULT suggestions for ALL users.
    """
    conn = get_db()
    signals = [
        ("style_success", style, {"style": style, "render_success": render_success}),
        ("scene_count_pattern", f"{style}_{content_format}",
         {"avg_scene_count": scene_count, "format": content_format}),
        ("music_source_success", music_source,
         {"source": music_source, "render_success": render_success}),
    ]
    for kw in topic_keywords[:3]:
        signals.append(("popular_topic", kw, {"topic": kw, "style": style}))

    for sig_type, sig_key, sig_val in signals:
        execute(conn, """
            INSERT INTO global_learning (signal_type, signal_key, signal_value,
                total_users, total_occurrences)
            VALUES (%s,%s,%s,1,1)
            ON CONFLICT (signal_type, signal_key)
            DO UPDATE SET
                total_occurrences = global_learning.total_occurrences + 1,
                signal_value = %s,
                updated_at = NOW()
        """, (sig_type, sig_key, json.dumps(sig_val), json.dumps(sig_val)))
    conn.commit(); conn.close()

def get_global_insights() -> dict:
    """Return global learning insights — used for app-wide default improvements."""
    conn = get_db()
    # Most successful styles globally
    top_styles = fetchall(conn, """
        SELECT signal_key, total_occurrences
        FROM global_learning
        WHERE signal_type='style_success'
        ORDER BY total_occurrences DESC LIMIT 5
    """, ())
    # Most popular topics globally
    top_topics = fetchall(conn, """
        SELECT signal_key, total_occurrences
        FROM global_learning
        WHERE signal_type='popular_topic'
        ORDER BY total_occurrences DESC LIMIT 10
    """, ())
    # Best music sources globally
    best_music = fetchall(conn, """
        SELECT signal_key, total_occurrences
        FROM global_learning
        WHERE signal_type='music_source_success'
        ORDER BY total_occurrences DESC LIMIT 5
    """, ())
    conn.close()
    return {
        "top_styles": [r["signal_key"] for r in top_styles],
        "trending_topics": [r["signal_key"] for r in top_topics],
        "best_music_sources": [r["signal_key"] for r in best_music],
    }

# ── DNA BUILDER ───────────────────────────────────────────────────────────────

async def rebuild_dna(user_id: str = "default"):
    """Rebuild Creator DNA from all memories."""
    conn = get_db()
    events = fetchall(conn, """
        SELECT * FROM project_learning_events
        WHERE user_id=%s ORDER BY created_at DESC LIMIT 20
    """, (user_id,))
    conn.close()

    if not events: return

    # Visual profile — most used style
    styles = [e.get("style","cinematic") for e in events if e.get("style")]
    style_counts = {}
    for s in styles: style_counts[s] = style_counts.get(s,0) + 1
    dominant_style = max(style_counts, key=style_counts.get) if style_counts else "cinematic"

    # Pacing profile
    scene_counts = [e.get("scene_count",10) for e in events if e.get("scene_count")]
    durations = [e.get("total_duration",60) for e in events if e.get("total_duration")]
    avg_scenes = sum(scene_counts)/len(scene_counts) if scene_counts else 10
    avg_dur = sum(durations)/len(durations) if durations else 60
    avg_scene_dur = avg_dur / avg_scenes if avg_scenes > 0 else 6
    pacing = "fast" if avg_scene_dur < 4 else "medium" if avg_scene_dur < 7 else "slow"

    # Music profile
    music_sources = [e.get("music_source","none") for e in events if e.get("music_source")]
    music_counts = {}
    for m in music_sources: music_counts[m] = music_counts.get(m,0) + 1
    fav_music = max(music_counts, key=music_counts.get) if music_counts else "fma"

    # Topic profile — all keywords across events
    all_topics = []
    for e in events:
        kws = e.get("topic_keywords",[]) or []
        all_topics.extend(kws)
    topic_counts = {}
    for t in all_topics: topic_counts[t] = topic_counts.get(t,0)+1
    top_topics = sorted(topic_counts, key=topic_counts.get, reverse=True)[:8]

    # Render success rate
    successes = [e for e in events if e.get("render_success")]
    success_rate = len(successes)/len(events) if events else 0

    conn = get_db()
    execute(conn, """
        INSERT INTO creator_dna (user_id, overall_style, visual_profile, pacing_profile,
            music_profile, topic_profile, total_videos_analyzed, last_updated)
        VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            overall_style=%s, visual_profile=%s, pacing_profile=%s,
            music_profile=%s, topic_profile=%s,
            total_videos_analyzed=%s, last_updated=NOW()
    """, (user_id, dominant_style,
          json.dumps({"dominant_style": dominant_style, "style_counts": style_counts}),
          json.dumps({"dominant_pace": pacing, "avg_scene_duration": round(avg_scene_dur,2),
                      "avg_scenes": round(avg_scenes,1)}),
          json.dumps({"favorite_source": fav_music, "source_counts": music_counts}),
          json.dumps({"top_topics": top_topics, "total_topics": len(all_topics)}),
          len(events),
          dominant_style,
          json.dumps({"dominant_style": dominant_style, "style_counts": style_counts}),
          json.dumps({"dominant_pace": pacing, "avg_scene_duration": round(avg_scene_dur,2),
                      "avg_scenes": round(avg_scenes,1)}),
          json.dumps({"favorite_source": fav_music, "source_counts": music_counts}),
          json.dumps({"top_topics": top_topics, "total_topics": len(all_topics)}),
          len(events)))
    conn.commit(); conn.close()

def get_dna(user_id: str = "default") -> dict:
    conn = get_db()
    dna = fetchone(conn, "SELECT * FROM creator_dna WHERE user_id=%s", (user_id,))
    conn.close()
    if not dna: return {"total_videos_analyzed": 0}
    # Parse JSON fields
    for field in ["visual_profile","pacing_profile","music_profile","topic_profile","editing_profile"]:
        val = dna.get(field,"{}")
        if isinstance(val, str):
            try: dna[field] = json.loads(val)
            except Exception: dna[field] = {}
    return dna

def get_memory_summary(user_id: str = "default") -> dict:
    conn = get_db()
    memories = fetchall(conn,
        "SELECT memory_type, COUNT(*) as cnt FROM creator_memories WHERE user_id=%s GROUP BY memory_type",
        (user_id,))
    events = fetchall(conn,
        "SELECT COUNT(*) as c FROM project_learning_events WHERE user_id=%s", (user_id,))
    dna = fetchone(conn, "SELECT * FROM creator_dna WHERE user_id=%s", (user_id,))
    conn.close()

    total_memories = sum(m.get("cnt",0) for m in memories)
    total_videos = events[0].get("c",0) if events else 0

    # Style prefs
    conn2 = get_db()
    style_mems = fetchall(conn2, """
        SELECT memory_key, use_count FROM creator_memories
        WHERE user_id=%s AND memory_type='style_preference'
        ORDER BY use_count DESC LIMIT 3
    """, (user_id,))
    music_mems = fetchall(conn2, """
        SELECT memory_key FROM creator_memories
        WHERE user_id=%s AND memory_type='music_preference'
        ORDER BY use_count DESC LIMIT 3
    """, (user_id,))
    topic_mems = fetchall(conn2, """
        SELECT memory_key FROM creator_memories
        WHERE user_id=%s AND memory_type='topic_interest'
        ORDER BY use_count DESC LIMIT 8
    """, (user_id,))
    conn2.close()

    pacing_info = {}
    if dna:
        pp = dna.get("pacing_profile",{})
        if isinstance(pp, str):
            try: pp = json.loads(pp)
            except Exception: pp = {}
        pacing_info = pp

    return {
        "total_videos": total_videos,
        "total_memories": total_memories,
        "dna_version": dna.get("total_videos_analyzed",0) if dna else 0,
        "style_preferences": [m["memory_key"] for m in style_mems],
        "music_preferences": [m["memory_key"] for m in music_mems],
        "favorite_topics": [m["memory_key"] for m in topic_mems],
        "pacing": pacing_info.get("dominant_pace","unknown"),
    }

async def get_style_recommendation(user_id: str, topic: str = "") -> dict:
    """Return personalized style recommendation based on creator DNA."""
    dna = get_dna(user_id)
    if dna.get("total_videos_analyzed",0) < 2:
        return {"confidence":"low","recommended_style":"cinematic",
                "recommended_format":"landscape","recommended_scene_count":10,
                "avg_scene_duration":6.0,"based_on":"defaults"}

    vp = dna.get("visual_profile",{})
    pp = dna.get("pacing_profile",{})
    style = vp.get("dominant_style","cinematic")
    pace = pp.get("dominant_pace","medium")
    avg_dur = pp.get("avg_scene_duration",6)
    avg_scenes = int(pp.get("avg_scenes",10))

    return {
        "confidence": "high" if dna.get("total_videos_analyzed",0) >= 3 else "medium",
        "recommended_style": style,
        "recommended_format": "landscape",
        "recommended_scene_count": avg_scenes,
        "avg_scene_duration": avg_dur,
        "based_on": f"{dna.get('total_videos_analyzed',0)} videos analyzed",
        "pacing": pace,
    }
