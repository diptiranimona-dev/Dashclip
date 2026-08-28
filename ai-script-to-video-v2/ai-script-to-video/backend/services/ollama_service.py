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
        "You are a video editor. Break this script into scenes for stock footage search.\n\n"
        "STRICT RULES:\n"
        "- Respond with ONLY a JSON array\n"
        "- No text before or after the array\n"
        "- No markdown, no backticks, no explanation\n"
        "- Each item must have: scene (number), description (string), keywords (array of 2-3 strings), duration_hint (number)\n"
        "- Keywords must be simple concrete words like 'ocean waves' or 'city traffic'\n\n"
        "EXAMPLE OUTPUT (copy this exact format):\n"
        '[{"scene":1,"description":"person walking on beach at sunset","keywords":["beach sunset","ocean waves"],"duration_hint":6},{"scene":2,"description":"coffee being poured into a white cup","keywords":["coffee pouring","morning drink"],"duration_hint":5}]\n\n'
        f"Script:\n{script}\n\n"
        "Now output the JSON array only:"
    )

    raw = await _ask(prompt, timeout=180)

    raw = raw.strip()
    for fence in ["```json", "```JSON", "```"]:
        raw = raw.replace(fence, "")
    raw = raw.strip()

    start = raw.find("[")
    end = raw.rfind("]") + 1

    if start == -1 or end == 0:
        raise ValueError(f"Ollama did not return a JSON array. Response was: {raw[:300]}")

    json_str = raw[start:end]

    import re
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
    json_str = re.sub(r'(?<!\\)\n', ' ', json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        scenes = []
        matches = re.findall(r'\{[^{}]+\}', json_str)
        for i, m in enumerate(matches):
            try:
                obj = json.loads(m)
                if "description" in obj:
                    scenes.append({
                        "scene": obj.get("scene", i+1),
                        "description": obj.get("description", ""),
                        "keywords": obj.get("keywords", [obj.get("description","").split()[0]]),
                        "duration_hint": obj.get("duration_hint", 6)
                    })
            except Exception:
                continue
        if scenes:
            return scenes
        raise ValueError(f"Could not parse scenes from Ollama response: {json_str[:300]}")
    




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
