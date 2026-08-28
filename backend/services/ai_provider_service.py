"""
ai_provider_service.py — DashClip V4 AI Router
Three-tier Qwen routing via Ollama only. Zero paid API dependency.

TIER 1 — PRIMARY (complex intelligence):
  Default: qwen2.5:7b  (set DASHCLIP_AI_MODEL in .env)
  Tasks: script, scenes, director, brain, research, recommendations

TIER 2 — MEDIUM (lightweight tasks):
  Default: qwen2.5:3b  (set DASHCLIP_AI_MEDIUM in .env)
  Tasks: classification, simple analysis, asset tagging, basic rewriting

TIER 3 — FAST (repetitive/simple):
  Default: qwen2.5:1.5b  (set DASHCLIP_AI_FAST in .env)
  Tasks: keyword cleanup, tag generation, metadata, validation

DETERMINISTIC — never uses AI:
  Score calculations, durations, timestamps, DB ops, timeline math, file ops
"""

import os, json, re, asyncio
import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")

# ── MODEL CONFIGURATION (all from .env — never hardcoded in services) ─────────
MODEL_PRIMARY  = os.getenv("DASHCLIP_AI_MODEL",   "qwen2.5:7b")    # Tier 1
MODEL_MEDIUM   = os.getenv("DASHCLIP_AI_MEDIUM",  "qwen2.5:3b")    # Tier 2
MODEL_FAST     = os.getenv("DASHCLIP_AI_FAST",    "qwen2.5:1.5b")  # Tier 3

# Legacy env vars mapped to tiers
_legacy_fallback = os.getenv("DASHCLIP_AI_FALLBACK", "")
if _legacy_fallback and not os.getenv("DASHCLIP_AI_MEDIUM"):
    MODEL_MEDIUM = _legacy_fallback

# ── TASK → TIER ROUTING TABLE ─────────────────────────────────────────────────

# Tier 1: Complex intelligence tasks — use PRIMARY model
TIER1_TASKS = {
    "script_generation",      # Full script writing
    "scene_planning",         # Break script into scenes
    "scene_keywords",         # 10 unique keywords per scene
    "narration_extraction",   # Extract clean narration from script
    "camera_direction",       # Visual/camera direction generation
    "ai_director",            # AI Director scoring/analysis
    "editing_director",       # Editing decisions
    "creator_brain",          # Creator DNA building
    "global_learning",        # Global pattern analysis
    "research_analysis",      # Topic research and outline
    "recommendations",        # Project recommendations
    "template_selection",     # Smart template matching
    "video_dna",              # Video DNA from idea
    "script_sections",        # Extract script sections
    "improve_script",         # Script improvement
    "music_director",         # Music brief generation
    "voiceover_director",     # Voiceover brief generation
    "visual_director",        # Visual concept generation
}

# Tier 2: Medium intelligence tasks — use MEDIUM model
TIER2_TASKS = {
    "clip_metadata",          # Clip metadata analysis
    "content_classification", # Classify content type
    "simple_scene_analysis",  # Basic scene analysis
    "basic_recommendations",  # Simple suggestions
    "asset_tagging",          # Tag images/clips
    "template_categorization",# Categorize templates
    "simple_rewriting",       # Minor text edits
    "style_matching",         # Match style to content
    "emotion_detection",      # Detect scene emotion
    "hook_generation",        # Generate video hooks
}

# Tier 3: Fast repetitive tasks — use FAST model
TIER3_TASKS = {
    "keyword_cleanup",        # Clean/normalize keywords
    "tag_generation",         # Generate tags from text
    "metadata_extraction",    # Extract basic metadata
    "simple_validation",      # Validate text/JSON
    "text_transformation",    # Small text transforms
    "subtitle_timing",        # Simple timing calc
    "format_detection",       # Detect content format
}

# Purely deterministic — NEVER call AI for these
DETERMINISTIC_TASKS = {
    "score_calculation",      # Use Python math
    "duration_calculation",   # Use Python math
    "timestamp_generation",   # Use datetime
    "file_validation",        # Use pathlib
    "database_operations",    # Use psycopg2
    "timeline_arithmetic",    # Use Python math
    "format_calculation",     # Use Python math
}

# ── MODEL AVAILABILITY CACHE ──────────────────────────────────────────────────
_model_cache: dict[str, bool] = {}
_cache_lock = asyncio.Lock()

async def _is_available(model: str) -> bool:
    """Check if model is installed in Ollama. Cached per session."""
    if model in _model_cache:
        return _model_cache[model]
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
        if r.status_code != 200:
            _model_cache[model] = False
            return False
        installed = r.json().get("models", [])
        installed_names = [m["name"] for m in installed]
        installed_bases = [m["name"].split(":")[0] for m in installed]
        model_base = model.split(":")[0]
        available = model in installed_names or model_base in installed_bases
        _model_cache[model] = available
        return available
    except Exception:
        _model_cache[model] = False
        return False

def _get_tier(task_type: str) -> int:
    """Return 1, 2, or 3 based on task complexity."""
    if task_type in TIER1_TASKS: return 1
    if task_type in TIER2_TASKS: return 2
    if task_type in TIER3_TASKS: return 3
    if task_type in DETERMINISTIC_TASKS:
        raise ValueError(f"Task '{task_type}' is deterministic — use Python, not AI")
    # Default to tier 1 for unknown tasks (safe default)
    return 1

async def _select_model(task_type: str) -> str:
    """
    Select appropriate model with automatic fallback chain.
    Tier 1 fails → try Tier 2 → try Tier 3
    All fail → use any available model
    """
    tier = _get_tier(task_type)

    # Build fallback chain based on tier
    if tier == 1:
        chain = [MODEL_PRIMARY, MODEL_MEDIUM, MODEL_FAST]
    elif tier == 2:
        chain = [MODEL_MEDIUM, MODEL_PRIMARY, MODEL_FAST]
    else:
        chain = [MODEL_FAST, MODEL_MEDIUM, MODEL_PRIMARY]

    # Try each model in chain
    for model in chain:
        if await _is_available(model):
            return model

    # Last resort: ask Ollama what's installed and use anything
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
        installed = r.json().get("models", [])
        if installed:
            picked = installed[0]["name"]
            print(f"[ai] All configured models unavailable. Using: {picked}")
            return picked
    except Exception:
        pass

    # Absolute last resort
    return MODEL_FAST

# ── CORE AI CALL ──────────────────────────────────────────────────────────────

# Read timeout from env — increase if qwen2.5:7b times out on your machine
_DEFAULT_TIMEOUT = int(os.getenv("DASHCLIP_AI_TIMEOUT", "360"))

async def _call_ollama(model: str, prompt: str, system: str = "",
                       timeout: int = None) -> str:
    """
    Raw Ollama API call with retry.
    Returns empty string on failure — never raises.
    Timeout defaults to DASHCLIP_AI_TIMEOUT env var (default 360s).
    """
    if timeout is None:
        timeout = _DEFAULT_TIMEOUT

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(2):  # 2 attempts — qwen is slow, don't waste time on 3
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(float(timeout), connect=20.0)
            ) as c:
                r = await c.post(
                    f"{OLLAMA_URL}/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,
                            "num_predict": 4096,
                            "num_ctx": 8192,
                        }
                    }
                )
                r.raise_for_status()
                result = r.json().get("message", {}).get("content", "").strip()
                if result:
                    return result
                print(f"[ai] {model} returned empty response")
                return ""
        except httpx.TimeoutException:
            print(f"[ai] {model} timeout after {timeout}s (attempt {attempt+1}/2)")
            if attempt == 0:
                await asyncio.sleep(2)
        except httpx.HTTPStatusError as e:
            print(f"[ai] {model} HTTP {e.response.status_code}: {e.response.text[:100]}")
            if attempt == 0:
                await asyncio.sleep(1)
        except Exception as e:
            print(f"[ai] {model} error attempt {attempt+1}: {e}")
            if attempt == 0:
                await asyncio.sleep(1)
    return ""

# ── PUBLIC API — all services use these ──────────────────────────────────────

async def ask(prompt: str, system: str = "", timeout: int = 180,
              task_type: str = "script_generation") -> str:
    """
    Main AI text generation. Auto-selects model based on task_type.
    All DashClip services call this — NEVER call Ollama directly.
    """
    try:
        model = await _select_model(task_type)
    except ValueError as e:
        # Deterministic task — caller should not be using AI
        print(f"[ai] WARNING: {e}")
        return ""

    print(f"[ai] task={task_type} tier={_get_tier(task_type)} model={model}")
    result = await _call_ollama(model, prompt, system, timeout)

    # Fallback cascade if result is empty
    if not result:
        fallback_chain = [MODEL_MEDIUM, MODEL_FAST, MODEL_PRIMARY]
        for fb_model in fallback_chain:
            if fb_model != model and await _is_available(fb_model):
                print(f"[ai] Falling back to {fb_model}")
                result = await _call_ollama(
                    fb_model, prompt, system, min(timeout, 120))
                if result:
                    break

    return result

async def ask_json(prompt: str, system: str = "", timeout: int = 180,
                   task_type: str = "script_generation") -> dict:
    """Ask AI and return validated JSON dict. Never crashes."""
    # Add JSON instruction to system prompt
    json_system = (system or "") + "\nReturn ONLY valid JSON. No markdown, no explanations."
    raw = await ask(prompt, json_system, timeout, task_type)
    return _repair_json(raw, "object")

async def ask_json_array(prompt: str, system: str = "", timeout: int = 180,
                          task_type: str = "scene_planning") -> list:
    """Ask AI and return validated JSON array. Never crashes."""
    json_system = (system or "") + "\nReturn ONLY a valid JSON array. No markdown."
    raw = await ask(prompt, json_system, timeout, task_type)
    return _repair_json(raw, "array")

# ── JSON REPAIR ───────────────────────────────────────────────────────────────

def _repair_json(raw: str, expected: str = "object"):
    """
    Robust JSON parser. Handles all Ollama output quirks:
    - Markdown code blocks
    - Truncated JSON
    - Single quotes
    - Missing brackets
    - Trailing text after JSON
    """
    if not raw:
        return {} if expected == "object" else []

    cleaned = raw.strip()

    # Strip markdown code blocks
    if "```" in cleaned:
        cleaned = re.sub(r"```(?:json)?\n?", "", cleaned).strip().rstrip("`").strip()

    # Strip <think> tags (Qwen reasoning traces)
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned).strip()

    # Try direct parse
    try:
        parsed = json.loads(cleaned)
        if expected == "object":
            if isinstance(parsed, dict): return parsed
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                return parsed[0]
        if expected == "array":
            if isinstance(parsed, list): return parsed
            if isinstance(parsed, dict):
                for k in ("scenes","data","result","items","keywords","suggestions","options"):
                    if isinstance(parsed.get(k), list): return parsed[k]
                return [parsed]
    except json.JSONDecodeError:
        pass

    # Extract JSON from surrounding text
    if expected == "object":
        m = re.search(r'\{[\s\S]*\}', cleaned)
        if m:
            try: return json.loads(m.group(0))
            except Exception: pass
    else:
        m = re.search(r'\[[\s\S]*\]', cleaned)
        if m:
            try: return json.loads(m.group(0))
            except Exception: pass

    # Repair common issues
    repaired = cleaned
    # Fix single quotes → double quotes (smart — avoid contractions)
    repaired = re.sub(r"(?<![a-zA-Z])'([^'\n]{0,100})'(?![a-zA-Z])", r'"\1"', repaired)
    # Remove trailing commas
    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
    # Balance brackets
    opens_curly  = repaired.count('{') - repaired.count('}')
    opens_square = repaired.count('[') - repaired.count(']')
    if opens_curly > 0:  repaired += '}' * opens_curly
    if opens_square > 0: repaired += ']' * opens_square

    try:
        parsed = json.loads(repaired)
        if expected == "object" and isinstance(parsed, dict): return parsed
        if expected == "array" and isinstance(parsed, list): return parsed
    except Exception:
        pass

    # Last resort: extract individual objects for arrays
    if expected == "array":
        objs = re.findall(r'\{[^{}]{10,}\}', cleaned)
        result = []
        for o in objs:
            try: result.append(json.loads(o))
            except Exception: pass
        if result: return result

    return {} if expected == "object" else []

# ── STATUS & HEALTH ───────────────────────────────────────────────────────────

async def get_status() -> dict:
    """Health check — shows which models are available."""
    global _model_cache
    _model_cache.clear()  # Force fresh check

    p = await _is_available(MODEL_PRIMARY)
    m = await _is_available(MODEL_MEDIUM)
    f = await _is_available(MODEL_FAST)

    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
        all_models = [x["name"] for x in r.json().get("models", [])]
    except Exception:
        all_models = []

    active = (MODEL_PRIMARY if p else MODEL_MEDIUM if m else MODEL_FAST)

    return {
        "provider": "ollama",
        "ollama_url": OLLAMA_URL,
        "tier1_model": MODEL_PRIMARY,
        "tier1_available": p,
        "tier2_model": MODEL_MEDIUM,
        "tier2_available": m,
        "tier3_model": MODEL_FAST,
        "tier3_available": f,
        "active_model": active,
        "installed_models": all_models,
        "model": active,  # Legacy compat
    }

def get_provider() -> str:
    """Sync helper for startup banner."""
    return f"ollama ({MODEL_PRIMARY}/{MODEL_MEDIUM}/{MODEL_FAST})"

async def get_available_models() -> list[dict]:
    """Get all installed Ollama models."""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
        return [{"name": m["name"], "size": m.get("size", 0)}
                for m in r.json().get("models", [])]
    except Exception:
        return []

# ── .ENV DOCUMENTATION ────────────────────────────────────────────────────────
# Add to your .env file:
#
# DASHCLIP_AI_MODEL=qwen2.5:7b      # Tier 1 — complex tasks
# DASHCLIP_AI_MEDIUM=qwen2.5:3b     # Tier 2 — medium tasks
# DASHCLIP_AI_FAST=qwen2.5:1.5b    # Tier 3 — fast tasks
# OLLAMA_URL=http://127.0.0.1:11434  # Ollama server
#
# Install models:
# ollama pull qwen2.5:7b
# ollama pull qwen2.5:3b
# ollama pull qwen2.5:1.5b
#
# Alternatives (if RAM is limited):
# DASHCLIP_AI_MODEL=llama3.1:8b
# DASHCLIP_AI_MEDIUM=llama3.2:3b
# DASHCLIP_AI_FAST=llama3.2:1b
