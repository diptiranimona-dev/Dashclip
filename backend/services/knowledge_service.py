"""
knowledge_service.py — DashClip V4
Knowledge Base per creator per topic.
Stores facts, research, sources, talking points for reuse across projects.
"""
import json, re
from datetime import datetime
from db import get_db, execute, fetchone, fetchall
import services.ai_provider_service as ai

def ensure_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS creator_knowledge (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) DEFAULT 'default',
            topic VARCHAR(500) NOT NULL,
            topic_slug VARCHAR(500) NOT NULL,
            entry_type VARCHAR(50) DEFAULT 'fact',
            title VARCHAR(500),
            content TEXT,
            source_url TEXT DEFAULT '',
            tags TEXT[] DEFAULT '{}',
            confidence FLOAT DEFAULT 0.8,
            used_in_projects INTEGER[] DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS research_cache (
            id SERIAL PRIMARY KEY,
            query VARCHAR(500) NOT NULL UNIQUE,
            results JSONB DEFAULT '[]',
            summary TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '7 days'
        );
        CREATE TABLE IF NOT EXISTS topic_outlines (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) DEFAULT 'default',
            topic VARCHAR(500) NOT NULL,
            outline JSONB DEFAULT '[]',
            talking_points TEXT[] DEFAULT '{}',
            key_facts TEXT[] DEFAULT '{}',
            sources TEXT[] DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit()
    conn.close()

def _slugify(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', text.lower().strip())[:200]

async def research_topic(topic: str, user_id: str = "default") -> dict:
    """Research a topic using AI and store findings in knowledge base."""
    slug = _slugify(topic)

    # Check cache first
    conn = get_db()
    cached = fetchone(conn, "SELECT * FROM research_cache WHERE query=%s AND expires_at > NOW()", (slug,))
    conn.close()
    if cached:
        return {"topic": topic, "cached": True, "summary": cached["summary"], "results": cached["results"]}

    system = (
        "You are a thorough research assistant for video content creators. "
        "You provide accurate, well-structured information suitable for video scripts."
    )
    prompt = (
        f"Research this topic for a video creator: {topic}\n\n"
        "Provide a JSON response with:\n"
        "{\n"
        '  "summary": "2-3 sentence overview",\n'
        '  "key_facts": ["fact1", "fact2", "fact3", "fact4", "fact5"],\n'
        '  "talking_points": ["point1", "point2", "point3"],\n'
        '  "visual_suggestions": ["what to show visually 1", "what to show visually 2"],\n'
        '  "hook_ideas": ["compelling hook 1", "compelling hook 2"],\n'
        '  "cta_ideas": ["call to action 1", "call to action 2"],\n'
        '  "related_topics": ["related1", "related2", "related3"],\n'
        '  "recommended_style": "cinematic/documentary/educational/etc",\n'
        '  "estimated_duration": "short/medium/long",\n'
        '  "difficulty_level": "beginner/intermediate/advanced"\n'
        "}\n\nReturn ONLY valid JSON."
    )

    result = await ai.ask_json(prompt, system, timeout=60)
    if not result:
        result = {
            "summary": f"Research on {topic}",
            "key_facts": [f"Key fact about {topic}"],
            "talking_points": [f"Main point about {topic}"],
            "visual_suggestions": ["Documentary-style footage"],
            "hook_ideas": [f"Did you know about {topic}?"],
            "cta_ideas": ["Like and subscribe for more"],
            "related_topics": [],
            "recommended_style": "documentary",
            "estimated_duration": "medium",
            "difficulty_level": "intermediate"
        }

    summary = result.get("summary", "")
    key_facts = result.get("key_facts", [])
    talking_points = result.get("talking_points", [])

    # Store in knowledge base
    conn = get_db()
    for fact in key_facts:
        execute(conn, """
            INSERT INTO creator_knowledge (user_id, topic, topic_slug, entry_type, title, content, tags)
            VALUES (%s,%s,%s,'fact',%s,%s,%s)
            ON CONFLICT DO NOTHING
        """, (user_id, topic, slug, fact[:200], fact, [slug]))

    # Store outline
    execute(conn, """
        INSERT INTO topic_outlines (user_id, topic, outline, talking_points, key_facts)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
    """, (user_id, topic, json.dumps(result), talking_points, key_facts))

    # Cache results
    execute(conn, """
        INSERT INTO research_cache (query, results, summary)
        VALUES (%s,%s,%s)
        ON CONFLICT (query) DO UPDATE SET results=%s, summary=%s, expires_at=NOW() + INTERVAL '7 days'
    """, (slug, json.dumps(result), summary, json.dumps(result), summary))
    conn.commit()
    conn.close()

    return {"topic": topic, "cached": False, "summary": summary, **result}

def add_knowledge(user_id: str, topic: str, entry_type: str, title: str, content: str,
                  source_url: str = "", tags: list = None) -> dict:
    slug = _slugify(topic)
    conn = get_db()
    row = execute(conn, """
        INSERT INTO creator_knowledge (user_id, topic, topic_slug, entry_type, title, content, source_url, tags)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (user_id, topic, slug, entry_type, title, content, source_url, tags or [slug]))
    conn.commit()
    conn.close()
    return {"id": row["id"], "topic": topic, "title": title}

def get_knowledge(user_id: str, topic: str = None, entry_type: str = None) -> list:
    conn = get_db()
    if topic and entry_type:
        slug = _slugify(topic)
        rows = fetchall(conn,
            "SELECT * FROM creator_knowledge WHERE user_id=%s AND topic_slug=%s AND entry_type=%s ORDER BY confidence DESC",
            (user_id, slug, entry_type))
    elif topic:
        slug = _slugify(topic)
        rows = fetchall(conn,
            "SELECT * FROM creator_knowledge WHERE user_id=%s AND topic_slug=%s ORDER BY confidence DESC",
            (user_id, slug))
    else:
        rows = fetchall(conn,
            "SELECT * FROM creator_knowledge WHERE user_id=%s ORDER BY created_at DESC LIMIT 50",
            (user_id,))
    conn.close()
    return rows

def get_topics(user_id: str) -> list:
    conn = get_db()
    rows = fetchall(conn,
        "SELECT DISTINCT topic, topic_slug, COUNT(*) as entry_count FROM creator_knowledge WHERE user_id=%s GROUP BY topic, topic_slug ORDER BY entry_count DESC",
        (user_id,))
    conn.close()
    return rows

def delete_knowledge(knowledge_id: int, user_id: str = "default"):
    conn = get_db()
    execute(conn, "DELETE FROM creator_knowledge WHERE id=%s AND user_id=%s", (knowledge_id, user_id))
    conn.commit()
    conn.close()

async def get_talking_points_for_script(user_id: str, topic: str, style: str = "cinematic") -> list:
    """Get relevant talking points from knowledge base to enhance script generation."""
    knowledge = get_knowledge(user_id, topic)
    if not knowledge:
        return []
    facts = [k["content"] for k in knowledge if k.get("entry_type") == "fact"][:5]
    points = [k["content"] for k in knowledge if k.get("entry_type") == "talking_point"][:5]
    return facts + points

def get_knowledge_summary(user_id: str = "default") -> dict:
    conn = get_db()
    total = fetchone(conn, "SELECT COUNT(*) as cnt FROM creator_knowledge WHERE user_id=%s", (user_id,))
    topics = fetchall(conn,
        "SELECT DISTINCT topic FROM creator_knowledge WHERE user_id=%s ORDER BY topic LIMIT 20",
        (user_id,))
    conn.close()
    return {
        "total_entries": total["cnt"] if total else 0,
        "topics": [t["topic"] for t in topics]
    }
