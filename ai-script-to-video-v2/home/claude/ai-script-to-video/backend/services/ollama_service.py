"""
ollama_service.py
All LLM calls go through here. Uses local Ollama (llama3.2).
"""
import json
import httpx

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2"


async def _ask(prompt: str, timeout: int = 120) -> str:
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            OLLAMA_URL,
            json={"model": MODEL, "prompt": prompt, "stream": False}
        )
        resp.raise_for_status()
        return resp.json()["response"].strip()


async def generate_script(topic: str) -> str:
    prompt = (
        f"Write a compelling short video script (4-6 scenes, 60-90 seconds) about: {topic}\n\n"
        "Rules:\n"
        "- Every scene must be VISUAL and filmable\n"
        "- Avoid abstract concepts like 'success' or 'happiness' — describe what the camera SEES\n"
        "- Each scene should feel like it lasts 5-8 seconds\n"
        "- Write in present tense\n"
        "- Return ONLY the script text, no preamble, no commentary"
    )
    return await _ask(prompt)


async def generate_scenes(script: str) -> list[dict]:
    prompt = (
        "You are a video editor breaking a script into scenes for stock footage search.\n\n"
        "Rules for GOOD scenes:\n"
        "- Each description must be a VISUAL scene (what the camera literally sees)\n"
        "- Descriptions should be 5-10 words, cinematic and searchable\n"
        "- Keywords must be concrete nouns/actions, never abstract\n"
        "- Avoid repeating keywords across scenes\n"
        "- Each scene should last 5-8 seconds\n\n"
        "BAD example: {\"description\": \"success is important\", \"keywords\": [\"success\"]}\n"
        "GOOD example: {\"description\": \"person typing on laptop late at night\", \"keywords\": [\"laptop night\", \"working late\", \"typing office\"]}\n\n"
        f"Script to break into scenes:\n{script}\n\n"
        "Respond ONLY with a valid JSON array. No markdown, no explanation, no backticks.\n"
        "Format: [{\"scene\": 1, \"description\": \"...\", \"keywords\": [\"kw1\", \"kw2\", \"kw3\"], \"duration_hint\": 6}]"
    )
    raw = await _ask(prompt, timeout=180)

    # Strip markdown fences if present
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("[") or part.startswith("json\n["):
                raw = part.replace("json\n", "").strip()
                break

    # Find JSON array in response
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON array found in LLM response: {raw[:300]}")

    return json.loads(raw[start:end])


async def generate_narration_text(script: str) -> str:
    """Generate clean voiceover narration from a script."""
    prompt = (
        "Convert this video script into clean voiceover narration.\n"
        "Rules:\n"
        "- Write in a warm, natural speaking voice\n"
        "- Remove scene directions and camera notes\n"
        "- Keep it concise and engaging\n"
        "- Return ONLY the narration text\n\n"
        f"Script:\n{script}"
    )
    return await _ask(prompt)


async def generate_subtitle_srt(narration: str, clip_durations: list[float]) -> str:
    """Generate SRT subtitle content timed to clip durations."""
    total = sum(clip_durations) if clip_durations else 30
    prompt = (
        f"Generate SRT subtitles for this narration. Total video duration: {total:.1f} seconds.\n"
        "Rules:\n"
        "- Max 7 words per subtitle line\n"
        "- Natural reading pace\n"
        "- Return ONLY valid SRT format, nothing else\n\n"
        f"Narration:\n{narration}"
    )
    return await _ask(prompt, timeout=60)
