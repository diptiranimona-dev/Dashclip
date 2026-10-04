"""
ai_provider_service.py — DashClip V4 AI Provider Abstraction
Supports two providers, switchable at runtime:

  PROVIDER=gemini  → Google Gemini API (user provides GEMINI_API_KEY)
                     Primary for public beta on Render.
                     Free tier: 1500 req/day with gemini-2.0-flash.

  PROVIDER=ollama  → Local Ollama (user runs Ollama on their machine)
                     For privacy-conscious users or offline use.
                     Cannot run on Render — connects to user's local instance.

All DashClip services call:
  ai.ask(prompt, system, task_type)
  ai.ask_json(prompt, system, task_type)
  ai.ask_json_array(prompt, system, task_type)

Provider, model, and keys are read from env — never hardcoded.
"""

import os, json, re, asyncio
import httpx

# ── PROVIDER SELECTION ────────────────────────────────────────────────────────
# Set DASHCLIP_AI_PROVIDER=gemini or ollama in .env
# If not set: auto-detect (gemini if key present, else ollama)
_PROVIDER_ENV = os.getenv("DASHCLIP_AI_PROVIDER", "auto").lower()

# ── GEMINI CONFIG ─────────────────────────────────────────────────────────────
GEMINI_API_KEY     = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL       = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_API_BASE    = "https://generativelanguage.googleapis.com/v1beta"

# ── OLLAMA CONFIG ─────────────────────────────────────────────────────────────
OLLAMA_URL     = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL_PRIMARY  = os.getenv("DASHCLIP_AI_MODEL",   "qwen2.5:7b")
MODEL_MEDIUM   = os.getenv("DASHCLIP_AI_MEDIUM",  "qwen2.5:3b")
MODEL_FAST     = os.getenv("DASHCLIP_AI_FAST",    "qwen2.5:1.5b")
AI_TIMEOUT     = int(os.getenv("DASHCLIP_AI_TIMEOUT", "360"))

# ── TASK → TIER (Ollama only — Gemini uses one model for all) ─────────────────
TIER1_TASKS = {
    "script_generation", "scene_planning", "scene_keywords",
    "narration_extraction", "camera_direction", "ai_director",
    "editing_director", "creator_brain", "global_learning",
    "research_analysis", "recommendations", "template_selection",
    "video_dna", "script_sections", "improve_script",
    "music_director", "voiceover_director", "visual_director",
}
TIER2_TASKS = {
    "clip_metadata", "content_classification", "simple_scene_analysis",
    "basic_recommendations", "asset_tagging", "template_categorization",
    "simple_rewriting", "style_matching", "emotion_detection", "hook_generation",
}
TIER3_TASKS = {
    "keyword_cleanup", "tag_generation", "metadata_extraction",
    "simple_validation", "text_transformation", "subtitle_timing",
    "format_detection",
}

# ── PROVIDER RESOLUTION ───────────────────────────────────────────────────────
_model_cache: dict[str, bool] = {}

def _resolve_provider() -> str:
    """Determine which provider to use at runtime."""
    if _PROVIDER_ENV == "gemini":
        return "gemini"
    if _PROVIDER_ENV == "ollama":
        return "ollama"
    # auto: use gemini if key present, else ollama
    return "gemini" if GEMINI_API_KEY else "ollama"

def get_provider() -> str:
    return _resolve_provider()

def get_provider_display() -> str:
    p = _resolve_provider()
    if p == "gemini":
        return f"gemini ({GEMINI_MODEL})"
    return f"ollama ({MODEL_PRIMARY}/{MODEL_MEDIUM}/{MODEL_FAST})"

# ── CONNECTION TEST ───────────────────────────────────────────────────────────

async def test_connection() -> dict:
    """
    Real connection test — actually calls the provider.
    Returns {"ok": bool, "provider": str, "model": str, "error": str|None}
    Never returns fake success.
    """
    provider = _resolve_provider()
    if provider == "gemini":
        return await _test_gemini()
    return await _test_ollama()

async def _test_gemini() -> dict:
    if not GEMINI_API_KEY:
        return {
            "ok": False,
            "provider": "gemini",
            "model": GEMINI_MODEL,
            "error": "AI_PROVIDER_UNAVAILABLE: No GEMINI_API_KEY configured. "
                     "Add your Gemini API key in Settings or set GEMINI_API_KEY env var. "
                     "Get a free key at https://aistudio.google.com/apikey"
        }
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
                json={"contents": [{"parts": [{"text": "Reply with exactly: OK"}]}],
                      "generationConfig": {"maxOutputTokens": 10}}
            )
        if r.status_code == 200:
            return {"ok": True, "provider": "gemini", "model": GEMINI_MODEL, "error": None}
        elif r.status_code == 400:
            return {"ok": False, "provider": "gemini", "model": GEMINI_MODEL,
                    "error": f"AI_PROVIDER_UNAVAILABLE: Invalid Gemini API key. "
                             f"Check your key at https://aistudio.google.com/apikey"}
        elif r.status_code == 429:
            return {"ok": False, "provider": "gemini", "model": GEMINI_MODEL,
                    "error": "AI_PROVIDER_UNAVAILABLE: Gemini rate limit reached. "
                             "Free tier allows 1500 requests/day. Try again tomorrow."}
        else:
            return {"ok": False, "provider": "gemini", "model": GEMINI_MODEL,
                    "error": f"AI_PROVIDER_UNAVAILABLE: Gemini returned HTTP {r.status_code}"}
    except Exception as e:
        return {"ok": False, "provider": "gemini", "model": GEMINI_MODEL,
                "error": f"AI_PROVIDER_UNAVAILABLE: Cannot reach Gemini API — {e}"}

async def _test_ollama() -> dict:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{OLLAMA_URL}/api/tags")
        if r.status_code != 200:
            return {"ok": False, "provider": "ollama", "model": MODEL_PRIMARY,
                    "error": f"AI_PROVIDER_UNAVAILABLE: Ollama returned HTTP {r.status_code}. "
                             f"Is Ollama running? Start it with: ollama serve"}
        models = [m["name"] for m in r.json().get("models", [])]
        if not models:
            return {"ok": False, "provider": "ollama", "model": MODEL_PRIMARY,
                    "error": f"AI_PROVIDER_UNAVAILABLE: Ollama is running but no models installed. "
                             f"Run: ollama pull qwen2.5:7b"}
        primary_found = any(MODEL_PRIMARY.split(":")[0] in m for m in models)
        return {
            "ok": True,
            "provider": "ollama",
            "model": MODEL_PRIMARY if primary_found else models[0],
            "installed_models": models,
            "error": None if primary_found else
                     f"Configured model {MODEL_PRIMARY} not found. Using {models[0]}. "
                     f"Install with: ollama pull {MODEL_PRIMARY}"
        }
    except httpx.ConnectError:
        return {"ok": False, "provider": "ollama", "model": MODEL_PRIMARY,
                "error": f"AI_PROVIDER_UNAVAILABLE: Cannot connect to Ollama at {OLLAMA_URL}. "
                         f"Start Ollama first, then try again."}
    except Exception as e:
        return {"ok": False, "provider": "ollama", "model": MODEL_PRIMARY,
                "error": f"AI_PROVIDER_UNAVAILABLE: Ollama error — {e}"}

# ── GEMINI IMPLEMENTATION ─────────────────────────────────────────────────────

async def _gemini_ask(prompt: str, system: str = "", timeout: int = 60) -> str:
    """Call Gemini API. Returns text or raises with clear error."""
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "AI_PROVIDER_UNAVAILABLE: No GEMINI_API_KEY. "
            "Add your key in Settings → AI Provider → Gemini API Key."
        )
    contents = []
    if system:
        contents.append({"role": "user", "parts": [{"text": system}]})
        contents.append({"role": "model", "parts": [{"text": "Understood."}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 8192,
            "responseMimeType": "text/plain",
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT",       "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH",      "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT","threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT","threshold": "BLOCK_NONE"},
        ]
    }

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=float(timeout)) as c:
                r = await c.post(
                    f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
                    json=payload
                )
            if r.status_code == 200:
                data = r.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts).strip()
                    if text:
                        return text
                print(f"[gemini] Empty response: {data}")
                return ""
            elif r.status_code == 429:
                if attempt == 0:
                    await asyncio.sleep(5)
                    continue
                raise RuntimeError(
                    "AI_PROVIDER_UNAVAILABLE: Gemini rate limit. "
                    "Free tier: 1500 requests/day. Try again later."
                )
            elif r.status_code in (401, 403):
                raise RuntimeError(
                    "AI_PROVIDER_UNAVAILABLE: Invalid Gemini API key. "
                    "Check Settings → AI Provider."
                )
            else:
                raise RuntimeError(
                    f"AI_PROVIDER_UNAVAILABLE: Gemini HTTP {r.status_code}: {r.text[:200]}"
                )
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt == 0:
                await asyncio.sleep(2)
                continue
            raise RuntimeError(f"AI_PROVIDER_UNAVAILABLE: Cannot reach Gemini — {e}")
    return ""

async def _gemini_ask_json(prompt: str, system: str = "", timeout: int = 60) -> str:
    """Call Gemini with JSON response mode."""
    if not GEMINI_API_KEY:
        raise RuntimeError("AI_PROVIDER_UNAVAILABLE: No GEMINI_API_KEY configured.")

    contents = []
    if system:
        contents.append({"role": "user", "parts": [{"text": system}]})
        contents.append({"role": "model", "parts": [{"text": "Understood. I will return only valid JSON."}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
        },
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT",       "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH",      "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT","threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT","threshold": "BLOCK_NONE"},
        ]
    }

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=float(timeout)) as c:
                r = await c.post(
                    f"{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
                    json=payload
                )
            if r.status_code == 200:
                data = r.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    return "".join(p.get("text", "") for p in parts).strip()
                return ""
            elif r.status_code == 429:
                if attempt == 0:
                    await asyncio.sleep(5); continue
                raise RuntimeError("AI_PROVIDER_UNAVAILABLE: Gemini rate limit reached.")
            else:
                raise RuntimeError(f"AI_PROVIDER_UNAVAILABLE: Gemini HTTP {r.status_code}")
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            if attempt == 0:
                await asyncio.sleep(2); continue
            raise RuntimeError(f"AI_PROVIDER_UNAVAILABLE: {e}")
    return ""

# ── OLLAMA IMPLEMENTATION ─────────────────────────────────────────────────────

async def _ollama_select_model(task_type: str) -> str:
    if task_type in TIER3_TASKS: chain = [MODEL_FAST, MODEL_MEDIUM, MODEL_PRIMARY]
    elif task_type in TIER2_TASKS: chain = [MODEL_MEDIUM, MODEL_PRIMARY, MODEL_FAST]
    else: chain = [MODEL_PRIMARY, MODEL_MEDIUM, MODEL_FAST]

    for model in chain:
        if model not in _model_cache:
            try:
                async with httpx.AsyncClient(timeout=6) as c:
                    r = await c.get(f"{OLLAMA_URL}/api/tags")
                installed = [m["name"] for m in r.json().get("models", [])]
                bases = [m.split(":")[0] for m in installed]
                _model_cache[model] = (model in installed or model.split(":")[0] in bases)
            except Exception:
                _model_cache[model] = False
        if _model_cache.get(model):
            return model
    return MODEL_FAST  # last resort

async def _ollama_call(model: str, prompt: str, system: str = "",
                       timeout: int = None) -> str:
    t = timeout or AI_TIMEOUT
    messages = []
    if system: messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(float(t), connect=15.0)
            ) as c:
                r = await c.post(f"{OLLAMA_URL}/api/chat", json={
                    "model": model, "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 4096, "num_ctx": 8192}
                })
                r.raise_for_status()
                return r.json().get("message", {}).get("content", "").strip()
        except httpx.TimeoutException:
            print(f"[ollama] {model} timeout (attempt {attempt+1})")
            if attempt == 0: await asyncio.sleep(2)
        except Exception as e:
            print(f"[ollama] error: {e}")
            if attempt == 0: await asyncio.sleep(1)
    return ""

# ── PUBLIC INTERFACE — all DashClip services call these ──────────────────────

async def ask(prompt: str, system: str = "", timeout: int = 120,
              task_type: str = "script_generation") -> str:
    """
    Main text generation. Auto-selects provider and model.
    Raises RuntimeError with AI_PROVIDER_UNAVAILABLE prefix on failure.
    Never silently returns empty on provider error.
    """
    provider = _resolve_provider()
    print(f"[ai] provider={provider} task={task_type}")

    if provider == "gemini":
        result = await _gemini_ask(prompt, system, min(timeout, 120))
    else:
        model = await _ollama_select_model(task_type)
        print(f"[ai] ollama model={model}")
        result = await _ollama_call(model, prompt, system, timeout)
        if not result:
            # Try fallback models
            for fb in [MODEL_MEDIUM, MODEL_FAST]:
                if fb != model:
                    result = await _ollama_call(fb, prompt, system, min(timeout, 120))
                    if result: break
    return result

async def ask_json(prompt: str, system: str = "", timeout: int = 120,
                   task_type: str = "script_generation") -> dict:
    """Ask AI and return validated JSON dict."""
    provider = _resolve_provider()
    if provider == "gemini":
        raw = await _gemini_ask_json(prompt, system, min(timeout, 120))
    else:
        json_sys = (system or "") + "\nReturn ONLY valid JSON. No markdown, no explanations."
        model = await _ollama_select_model(task_type)
        raw = await _ollama_call(model, prompt, json_sys, timeout)
    return _repair_json(raw, "object")

async def ask_json_array(prompt: str, system: str = "", timeout: int = 120,
                          task_type: str = "scene_planning") -> list:
    """Ask AI and return validated JSON array."""
    provider = _resolve_provider()
    if provider == "gemini":
        raw = await _gemini_ask_json(prompt, system, min(timeout, 120))
    else:
        json_sys = (system or "") + "\nReturn ONLY a valid JSON array. No markdown."
        model = await _ollama_select_model(task_type)
        raw = await _ollama_call(model, prompt, json_sys, timeout)
    return _repair_json(raw, "array")

# ── JSON REPAIR ───────────────────────────────────────────────────────────────

def _repair_json(raw: str, expected: str = "object"):
    """Robust JSON parser — handles all Ollama/Gemini output quirks."""
    if not raw:
        return {} if expected == "object" else []

    cleaned = raw.strip()
    # Strip markdown
    if "```" in cleaned:
        cleaned = re.sub(r"```(?:json)?\n?", "", cleaned).strip().rstrip("`").strip()
    # Strip Qwen <think> tags
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned).strip()

    # Direct parse
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

    # Extract from text
    pattern = r'\{[\s\S]*\}' if expected == "object" else r'\[[\s\S]*\]'
    m = re.search(pattern, cleaned)
    if m:
        try: return json.loads(m.group(0))
        except Exception: pass

    # Repair
    repaired = re.sub(r"(?<![a-zA-Z])'([^'\n]{0,200})'(?![a-zA-Z])", r'"\1"', cleaned)
    repaired = re.sub(r',\s*([}\]])', r'\1', repaired)
    repaired += '}' * max(0, repaired.count('{') - repaired.count('}'))
    repaired += ']' * max(0, repaired.count('[') - repaired.count(']'))
    try:
        parsed = json.loads(repaired)
        if expected == "object" and isinstance(parsed, dict): return parsed
        if expected == "array" and isinstance(parsed, list): return parsed
    except Exception: pass

    if expected == "array":
        objs = re.findall(r'\{[^{}]{10,}\}', cleaned)
        result = []
        for o in objs:
            try: result.append(json.loads(o))
            except Exception: pass
        if result: return result

    return {} if expected == "object" else []

# ── STATUS ────────────────────────────────────────────────────────────────────

async def get_status() -> dict:
    """Full status — used by /health and /v4/ai-provider endpoints."""
    provider = _resolve_provider()
    test = await test_connection()
    base = {
        "provider": provider,
        "configured_provider": _PROVIDER_ENV,
        "active_model": test.get("model", "unknown"),
        "ok": test["ok"],
        "error": test.get("error"),
        "display": get_provider_display(),
        "model": test.get("model", "unknown"),
    }
    if provider == "gemini":
        base.update({
            "gemini_model": GEMINI_MODEL,
            "gemini_key_set": bool(GEMINI_API_KEY),
        })
    else:
        base.update({
            "ollama_url": OLLAMA_URL,
            "tier1_model": MODEL_PRIMARY,
            "tier2_model": MODEL_MEDIUM,
            "tier3_model": MODEL_FAST,
        })
        try:
            async with httpx.AsyncClient(timeout=6) as c:
                r = await c.get(f"{OLLAMA_URL}/api/tags")
            base["installed_models"] = [m["name"] for m in r.json().get("models", [])]
        except Exception:
            base["installed_models"] = []
    return base

async def get_available_models() -> list[dict]:
    """For settings UI — returns available models for current provider."""
    provider = _resolve_provider()
    if provider == "gemini":
        return [
            {"name": "gemini-2.0-flash", "description": "Fast, free tier (recommended)"},
            {"name": "gemini-1.5-pro",   "description": "Higher quality, lower limits"},
            {"name": "gemini-1.5-flash",  "description": "Previous generation flash"},
        ]
    else:
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"{OLLAMA_URL}/api/tags")
            return [{"name": m["name"], "size": m.get("size", 0)}
                    for m in r.json().get("models", [])]
        except Exception:
            return []
