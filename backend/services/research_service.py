"""
research_service.py — DashClip V4
Topic research and script intelligence using AI provider.
"""
import json, re
from db import get_db, execute, fetchone, fetchall
import services.ai_provider_service as ai

async def research_and_outline(topic: str, style: str = "documentary", content_type: str = "educational", scene_count: int = 10) -> dict:
    system = "You are an expert video researcher and script consultant. Provide detailed, accurate research for video creators."
    prompt = (
        f"Research this video topic thoroughly: {topic}\n"
        f"Video style: {style}, Content type: {content_type}, Target scenes: {scene_count}\n\n"
        "Return JSON:\n"
        "{\n"
        '  "title_suggestions": ["Title 1", "Title 2", "Title 3"],\n'
        '  "hook": "The most compelling opening line for this video",\n'
        '  "key_facts": ["fact1", "fact2", "fact3", "fact4", "fact5"],\n'
        '  "scene_outline": [{"scene": 1, "focus": "what this scene covers", "visual_idea": "what to show", "duration": 6}],\n'
        '  "talking_points": ["point1", "point2", "point3"],\n'
        '  "visual_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],\n'
        '  "music_mood": "one word",\n'
        '  "estimated_total_duration": 60,\n'
        '  "target_audience": "description",\n'
        '  "cta": "call to action"\n'
        "}\nReturn ONLY valid JSON."
    )
    result = await ai.ask_json(prompt, system, timeout=90)
    if not result:
        return {
            "title_suggestions": [f"The Complete Guide to {topic}"],
            "hook": f"Everything you need to know about {topic}",
            "key_facts": [f"Key information about {topic}"],
            "scene_outline": [{"scene": i+1, "focus": f"Part {i+1}", "visual_idea": topic, "duration": 6} for i in range(scene_count)],
            "talking_points": [f"Main point about {topic}"],
            "visual_keywords": [topic, f"{topic} footage", f"{topic} documentary"],
            "music_mood": "atmospheric",
            "estimated_total_duration": scene_count * 6,
            "target_audience": "general audience",
            "cta": "Like and subscribe for more content"
        }
    return result

async def generate_hook_variations(topic: str, style: str = "cinematic", count: int = 5) -> list:
    prompt = (
        f"Generate {count} different compelling opening hooks for a {style} video about: {topic}\n"
        f"Each hook should be 1-2 sentences, attention-grabbing, and suit the {style} style.\n"
        "Return JSON array: [\"hook1\", \"hook2\", ...]"
    )
    result = await ai.ask_json_array(prompt, timeout=60)
    return result if result else [f"The untold story of {topic}..."]

async def improve_script_section(section: str, section_type: str = "intro", style: str = "cinematic") -> str:
    prompt = (
        f"Improve this {section_type} section of a {style} video script.\n"
        f"Make it more compelling, natural, and suited to the {style} style.\n"
        f"Keep the same length and core message. Return ONLY the improved text.\n\n"
        f"Original:\n{section}"
    )
    return await ai.ask(prompt, timeout=60)

async def extract_visual_keywords(script: str, topic: str = "", count: int = 50) -> list:
    prompt = (
        f"Extract {count} highly specific stock footage search keywords from this video script.\n"
        f"Topic context: {topic}\n"
        "Rules:\n"
        "- Each keyword must be searchable in stock footage libraries\n"
        "- Be specific (not just 'people' but 'business people meeting office')\n"
        "- Include variety: establishing shots, close-ups, action, emotion\n"
        "- NO script tags, stage directions, or meta-instructions\n"
        "- Focus on VISUAL CONTENT that would appear on screen\n\n"
        f"Script:\n{script[:2000]}\n\n"
        "Return JSON array of keywords only."
    )
    result = await ai.ask_json_array(prompt, timeout=90)
    return [k for k in result if isinstance(k, str) and len(k) > 3][:count]

async def suggest_b_roll(scene_description: str, topic: str, style: str = "cinematic") -> list:
    prompt = (
        f"Suggest 8 specific B-roll shots for this scene in a {style} video about {topic}:\n"
        f"Scene: {scene_description}\n\n"
        "Return JSON array of specific, searchable stock footage descriptions.\n"
        "Example: ['close-up hands typing keyboard', 'aerial city skyline sunset', ...]"
    )
    result = await ai.ask_json_array(prompt, timeout=60)
    return result[:8] if result else [scene_description]

def get_cached_research(query: str) -> dict:
    slug = re.sub(r'[^a-z0-9]+', '-', query.lower().strip())[:200]
    conn = get_db()
    row = fetchone(conn, "SELECT * FROM research_cache WHERE query=%s AND expires_at > NOW()", (slug,))
    conn.close()
    return dict(row) if row else {}

def cache_research(query: str, results: dict, summary: str = ""):
    slug = re.sub(r'[^a-z0-9]+', '-', query.lower().strip())[:200]
    conn = get_db()
    execute(conn, """
        INSERT INTO research_cache (query, results, summary)
        VALUES (%s,%s,%s)
        ON CONFLICT (query) DO UPDATE
        SET results=%s, summary=%s, expires_at=NOW() + INTERVAL '7 days'
    """, (slug, json.dumps(results), summary, json.dumps(results), summary))
    conn.commit()
    conn.close()
