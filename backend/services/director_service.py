"""
director_service.py — DashClip V3 Phase C
Fixed: all functions wrapped in try/except so 500s don't crash the app.
"""
import json, re
from db import get_db, execute, fetchone, fetchall
import services.ollama_service as ollama_service

async def generate_video_dna(project_id: int, script: str, video_style: str = "cinematic", content_type: str = "storytelling") -> dict:
    try:
        idea = script[:200] if script else ""
        result = await ollama_service.generate_video_dna_from_idea(idea, video_style, content_type)
        dna = result.get("video_dna", {})
        if project_id and dna:
            conn = get_db()
            execute(conn, "UPDATE projects SET video_dna=%s,updated_at=NOW() WHERE id=%s",
                    (json.dumps(dna), project_id))
            conn.commit(); conn.close()
        return {"video_dna": dna, "project_id": project_id}
    except Exception as e:
        print(f"[director] generate_video_dna error: {e}")
        return {"video_dna": {}, "project_id": project_id, "error": str(e)}

async def analyse_scene(project_id: int, scene_id: int, video_style: str = "cinematic", content_type: str = "storytelling") -> dict:
    """Analyse a single scene — never crashes, returns empty dict on error."""
    try:
        conn = get_db()
        scene = fetchone(conn, "SELECT * FROM scenes WHERE id=%s", (scene_id,))
        conn.close()
        if not scene:
            return {"scene_id": scene_id, "search_concepts": [], "emotion": "neutral"}

        description = scene.get("description", "")
        keywords = list(scene.get("keywords") or [])
        emotion = scene.get("scene_emotion", "neutral") or "neutral"

        # Generate better search concepts from existing keywords
        # For 1b model — don't call Ollama here, just use what we have
        search_concepts = [k for k in keywords if k and len(k) > 2][:8]

        # Update scene with search concepts
        conn = get_db()
        execute(conn, "UPDATE scenes SET search_concepts=%s WHERE id=%s",
                (json.dumps(search_concepts), scene_id))
        conn.commit(); conn.close()

        return {
            "scene_id": scene_id,
            "search_concepts": search_concepts,
            "emotion": emotion,
            "description": description,
        }
    except Exception as e:
        print(f"[director] analyse_scene error: {e}")
        return {"scene_id": scene_id, "search_concepts": [], "emotion": "neutral"}

async def generate_music_brief(project_id: int, script: str, video_style: str = "cinematic", content_type: str = "storytelling") -> dict:
    try:
        style_queries = {
            "cinematic": ["cinematic orchestral", "dramatic film score", "epic instrumental"],
            "documentary": ["documentary ambient", "atmospheric minimal", "world music"],
            "youtube": ["upbeat positive", "energetic pop", "motivational"],
            "educational": ["calm piano", "focus study music", "soft instrumental"],
            "dark": ["dark ambient", "ominous tension", "thriller soundtrack"],
            "luxury": ["elegant jazz", "smooth lounge", "luxury ambient"],
        }
        keywords = style_queries.get(video_style, [f"{video_style} background music"])
        return {
            "music_brief": {
                "emotion": "engaging",
                "energy": "medium",
                "search_keywords": keywords,
                "mood_description": f"{video_style.title()} style background music matching the video's tone"
            }
        }
    except Exception as e:
        print(f"[director] generate_music_brief error: {e}")
        return {"music_brief": {"emotion": "neutral", "energy": "medium", "search_keywords": [video_style], "mood_description": ""}}

async def generate_voiceover_brief(project_id: int, script: str, video_style: str = "cinematic", content_type: str = "storytelling") -> dict:
    try:
        style_voices = {
            "cinematic": {"tone": "dramatic", "speaking_speed": "slow", "narration_style": "Deep, resonant voice with dramatic pauses"},
            "documentary": {"tone": "authoritative", "speaking_speed": "normal", "narration_style": "Clear, factual delivery"},
            "youtube": {"tone": "energetic", "speaking_speed": "fast", "narration_style": "Enthusiastic and engaging"},
            "educational": {"tone": "warm", "speaking_speed": "normal", "narration_style": "Clear and approachable"},
            "dark": {"tone": "ominous", "speaking_speed": "slow", "narration_style": "Low, measured delivery"},
        }
        brief = style_voices.get(video_style, {"tone": "professional", "speaking_speed": "normal", "narration_style": "Clear and engaging"})
        return {"voiceover_brief": brief}
    except Exception as e:
        print(f"[director] generate_voiceover_brief error: {e}")
        return {"voiceover_brief": {"tone": "professional", "speaking_speed": "normal", "narration_style": "Clear narration"}}

async def score_clip(clip_id: int, scene_id: int, video_style: str = "cinematic") -> dict:
    try:
        conn = get_db()
        clip = fetchone(conn, "SELECT * FROM clips WHERE id=%s", (clip_id,))
        conn.close()
        if not clip:
            return {"clip_id": clip_id, "scores": {}}
        return {
            "clip_id": clip_id,
            "scores": {
                "keyword_score": clip.get("keyword_score", 0),
                "emotion_score": clip.get("emotion_score", 0),
                "style_score": clip.get("style_score", 0),
                "quality_score": clip.get("quality_score", 0),
                "consistency_score": clip.get("consistency_score", 0),
            }
        }
    except Exception as e:
        print(f"[director] score_clip error: {e}")
        return {"clip_id": clip_id, "scores": {}}
