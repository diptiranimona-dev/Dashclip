"""
ollama_service.py — DashClip V4 Fixed
Fix 1: Voiceover extraction detects all patterns Ollama 1b uses
Fix 2: Content-type specific script prompts — no more forced storytelling
Fix 3: Better scene keyword uniqueness
"""
import json, re
import services.ai_provider_service as ai

def _clean_desc(text: str) -> str:
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'\[[\w\s\-:/\d]+\]', '', text, flags=re.I)
    text = re.sub(r'(Script|Scene|VoiceOVER|VOICEOVER|Intro|Outro|Camera)\s*[:\d]*', '', text, flags=re.I)
    text = re.sub(r'\d+[-\s]*\d*\s*seconds?', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip().strip('.,- "\'')
    return text if len(text) > 5 else ""

def _clean_kw(kw_list: list, topic: str = "") -> list:
    """Clean keywords: split long sentences, remove garbage, ensure searchable stock terms."""
    BAD = {
        'scene','intro','outro','voiceover','script','seconds','make','about',
        'tik','tok','video','footage','shot','here','this','narrator','camera',
        'close','wide','aerial','medium','modern','historical','dramatic',
        'cinematic','documentary','authentic','vintage','contemporary'
    }
    BAD_PHRASES = ['make a tik tok','here is the','shot of','this is','the script',
                   'close up shot','wide shot of','aerial shot','here is a']

    out = []
    for raw_kw in kw_list:
        kw = str(raw_kw).strip()
        # Strip markdown/brackets
        kw = kw.strip('*[]"\'\' ').replace('*','').replace('[','').replace(']','').strip()
        if not kw or len(kw) < 3: continue

        # Skip if contains bad phrases
        kw_lower = kw.lower()
        if any(bp in kw_lower for bp in BAD_PHRASES): continue

        words = kw.split()
        if len(words) > 4:
            # Too long — extract the 2 most meaningful words
            good = [w for w in words if len(w) > 3 and w.lower() not in BAD]
            if len(good) >= 2:
                kw = good[0] + ' ' + good[1]
            elif good:
                kw = good[0]
            else:
                continue
        elif len(words) == 1 and words[0].lower() in BAD:
            continue

        if len(kw) < 3: continue
        out.append(kw)

    # Case-insensitive dedup
    seen, deduped = set(), []
    for k in out:
        if k.lower() not in seen:
            seen.add(k.lower())
            deduped.append(k)

    # Fallback if nothing left
    if not deduped and topic:
        topic_words = [w for w in topic.split() if len(w) > 3]
        for i in range(0, min(len(topic_words), 5)):
            if i+1 < len(topic_words):
                deduped.append(f"{topic_words[i]} {topic_words[i+1]}")
            else:
                deduped.append(topic_words[i])

    return list(dict.fromkeys(deduped))[:10]

# Content-type specific prompt structures
CONTENT_STRUCTURES = {
    "educational": (
        "EDUCATIONAL FORMAT — numbered steps, clear explanations, no story arc.\n"
        "Structure: Introduction → Key Concept 1 → Key Concept 2 → ... → Summary\n"
        "DO NOT write a story. Write factual explanations with examples."
    ),
    "tutorial": (
        "TUTORIAL FORMAT — step-by-step instructions, practical and clear.\n"
        "Structure: What you will learn → Step 1 → Step 2 → Step 3 → ... → Result\n"
        "DO NOT write a story. Write actionable steps the viewer can follow."
    ),
    "documentary": (
        "DOCUMENTARY FORMAT — factual, evidence-based, objective.\n"
        "Structure: Historical context → Evidence → Expert perspective → Conclusion\n"
        "Write facts and real information, not fictional narrative."
    ),
    "storytelling": (
        "STORYTELLING FORMAT — compelling narrative arc.\n"
        "Structure: Hook → Setup → Rising tension → Climax → Resolution\n"
        "Write an engaging story with emotional beats."
    ),
    "business": (
        "BUSINESS FORMAT — professional, ROI-focused, data-driven.\n"
        "Structure: Problem → Solution → Benefits → Call to action\n"
        "Write professionally with clear value propositions."
    ),
    "technology": (
        "TECHNOLOGY FORMAT — innovation-focused, clear explanation of how things work.\n"
        "Structure: The problem → The technology → How it works → Impact → Future\n"
        "Write clearly about technical concepts without jargon."
    ),
    "history": (
        "HISTORY FORMAT — chronological, factual, engaging.\n"
        "Structure: Historical context → Key events in order → Impact → Legacy\n"
        "Write accurate historical facts in chronological order."
    ),
    "science": (
        "SCIENCE FORMAT — accurate, wonder-inspiring, evidence-based.\n"
        "Structure: The phenomenon → The science behind it → Discovery → Implications\n"
        "Write accurate science that inspires curiosity."
    ),
    "travel": (
        "TRAVEL FORMAT — immersive, descriptive, inspiring.\n"
        "Structure: Destination intro → Highlights → Culture → Tips → Why go\n"
        "Write vivid descriptions that make viewers want to visit."
    ),
}

STYLE_NOTES = {
    "cinematic":    "dramatic wide shots, golden hour lighting, slow motion, shallow depth of field",
    "documentary":  "factual observational style, real locations, steady camera, archival footage",
    "youtube":      "energetic fast-paced, close-ups, bright lighting, quick cuts, dynamic",
    "educational":  "clear simple visuals, clean backgrounds, focused single-subject, diagrams",
    "minimal":      "sparse negative space, single subjects, muted tones, clean composition",
    "dark":         "moody high-contrast, deep shadows, night scenes, desaturated colors",
    "luxury":       "polished slow camera moves, reflective surfaces, elegant settings",
    "energetic":    "vibrant dynamic motion, bright bold colors, action and movement",
    "storytelling": "narrative arc visuals, emotional close-ups, atmospheric establishing shots",
    "history":      "period-appropriate visuals, archival style, sepia tones, historical locations",
    "science":      "laboratory settings, data visualization, natural phenomena, microscopic",
    "travel":       "wide landscape shots, cultural moments, movement through spaces",
    "business":     "professional office environments, meetings, growth charts, cityscapes",
    "technology":   "modern devices, code on screens, futuristic environments, digital interfaces",
}

async def generate_video_dna_from_idea(idea: str, video_style: str = "cinematic", content_type: str = "storytelling") -> dict:
    system = "You are an expert creative director. Return precise JSON creative briefs."
    prompt = (
        f"Analyze this video idea: {idea}\nStyle: {video_style}\nContent type: {content_type}\n\n"
        "Return ONLY this exact JSON:\n"
        '{"video_dna":{"overall_emotion":"engaging","overall_energy":"medium","overall_pace":"medium",'
        '"story_arc":"one sentence","visual_style":"one sentence","music_mood":"two words",'
        '"voiceover_tone":"two words","key_themes":["theme1","theme2"]},'
        '"music_brief":{"emotion":"neutral","energy":"medium","search_keywords":["word1","word2","word3"],"mood_description":"sentence"},'
        '"voiceover_brief":{"tone":"professional","speaking_speed":"normal","narration_style":"sentence"},'
        '"suggested_style":"documentary","suggested_content_type":"educational",'
        '"suggested_format":"longform",'
        '"camera_direction":"Two sentences describing camera work.",'
        '"narration_preview":"Two sentences of actual narration about this specific topic."}'
    )
    result = await ai.ask_json(prompt, system, timeout=90, task_type="video_dna")
    if not result or "video_dna" not in result:
        topic_words = idea.split()[:3]
        return {
            "video_dna": {
                "overall_emotion": "engaging", "overall_energy": "medium", "overall_pace": "medium",
                "story_arc": f"A compelling video about {' '.join(topic_words)}",
                "visual_style": STYLE_NOTES.get(video_style, video_style),
                "music_mood": "atmospheric calm", "voiceover_tone": "warm professional",
                "key_themes": topic_words or ["information", "clarity", "impact"]
            },
            "music_brief": {"emotion": "neutral", "energy": "medium",
                            "search_keywords": [video_style, "background", "instrumental"],
                            "mood_description": f"{video_style} background music"},
            "voiceover_brief": {"tone": "professional", "speaking_speed": "normal",
                                "narration_style": "Clear, direct narration"},
            "suggested_style": video_style, "suggested_content_type": content_type,
            "suggested_format": "longform",
            "camera_direction": "Wide establishing shots mixed with close-up details.",
            "narration_preview": f"Today we explore {idea[:80]}. Here is what you need to know."
        }
    return result

async def generate_script(topic: str, video_style: str = "cinematic", content_type: str = "storytelling",
                           content_format: str = "longform", scene_count: int = 0,
                           voiceover_hint: str = "", camera_hint: str = "",
                           talking_points: list = None) -> str:
    style_note = STYLE_NOTES.get(video_style, "")
    content_structure = CONTENT_STRUCTURES.get(content_type, CONTENT_STRUCTURES["storytelling"])
    target = scene_count or (8 if content_format == "shortform" else 10)
    length_note = (
        "SHORT-FORM: max 40 seconds total, 8-10 scenes, 3-4 seconds each."
        if content_format == "shortform" else
        f"LONG-FORM: {target} scenes, 6-8 seconds each."
    )
    tp_note = f"\nKey points to include: {', '.join(talking_points[:5])}" if talking_points else ""
    system = "You are a professional video scriptwriter. Write scripts that match the exact content type requested."
    prompt = (
        f"Write a {video_style} video script about: {topic}\n\n"
        f"CONTENT TYPE: {content_type.upper()}\n"
        f"{content_structure}\n\n"
        f"FORMAT: {length_note}\n"
        f"VISUAL STYLE: {style_note}{tp_note}\n\n"
        f"Write exactly {target} scenes using this format for EVERY scene:\n"
        "[SCENE N]\n"
        "Description: (5-8 words of what camera shows — NO script text here)\n"
        "[VOICEOVER] narrator words only here — NO camera directions, NO scene numbers\n\n"
        "CRITICAL RULES:\n"
        "1. Description line = ONLY what camera shows visually\n"
        "2. [VOICEOVER] line = ONLY what narrator says out loud\n"
        "3. NEVER mix camera directions into voiceover\n"
        "4. NEVER put scene numbers or 'Scene X' in the voiceover\n"
        f"5. The voiceover must sound like a {content_type} video, NOT a story\n\n"
        "Return ONLY the script. No intro text, no explanations."
    )
    result = await ai.ask(prompt, system)
    return result

async def generate_script_sections(script: str) -> dict:
    """
    Extract voiceover from script. Detects all patterns Ollama 1b uses:
    - [VOICEOVER] text
    - Voiceover: text
    - VO: text
    - Narration: text
    - "In a world..." (lines that sound like narration after scene description)
    """
    lines = script.split('\n')
    vo_lines = []
    cam_lines = []
    in_vo = False

    # Pattern matchers for all voiceover formats Ollama uses
    VO_PATTERNS = re.compile(
        r'^\[?(?:VOICEOVER|Voiceover|Voice Over|VO|Narration|NARRATION|'
        r'Voice-Over|voiceover|narrator|NARRATOR)\]?:?\s*', re.I)
    SCENE_PATTERN = re.compile(r'^\[?SCENE\s*\d+\]?', re.I)
    DESC_PATTERN = re.compile(r'^Description:', re.I)
    CAM_PATTERN = re.compile(r'^\[?(?:CAMERA|Camera|Shot|CUT TO|FADE|INT\.|EXT\.)', re.I)

    for line in lines:
        line = line.strip()
        if not line: in_vo = False; continue

        if SCENE_PATTERN.match(line):
            in_vo = False
            continue

        if DESC_PATTERN.match(line):
            in_vo = False
            rest = DESC_PATTERN.sub('', line).strip()
            if rest: cam_lines.append(rest)
            continue

        if CAM_PATTERN.match(line):
            in_vo = False
            continue

        if VO_PATTERNS.match(line):
            in_vo = True
            rest = VO_PATTERNS.sub('', line).strip()
            if rest: vo_lines.append(rest)
            continue

        if in_vo:
            # Stop if line looks like a new directive
            if re.match(r'^\[', line) or DESC_PATTERN.match(line):
                in_vo = False
            else:
                vo_lines.append(line)

    vo = ' '.join(vo_lines).strip()

    # If no voiceover found via tags, extract quoted speech or lines after scene descriptions
    if not vo or len(vo) < 20:
        # Try to find quoted text as narration
        quotes = re.findall(r'"([^"]{20,})"', script)
        if quotes:
            vo = ' '.join(quotes)

    # Last resort: strip ALL tags and directives
    if not vo or len(vo) < 20:
        clean = script
        clean = re.sub(r'\[SCENE\s*\d+\][^\n]*\n?', '', clean, flags=re.I)
        clean = re.sub(r'\[VOICEOVER\]\s*', '', clean, flags=re.I)
        clean = re.sub(r'(?:Voiceover|VO|Narration|Description):\s*', '', clean, flags=re.I)
        clean = re.sub(r'Scene\s*\d+[^\n]*\n?', '', clean, flags=re.I)
        clean = re.sub(r'^\s*\d+\.\s*', '', clean, flags=re.M)
        clean = re.sub(r'\[[\w\s\d]+\]', '', clean, flags=re.I)
        clean = re.sub(r'\*+', '', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        # Remove lines that are clearly camera directions (very short, start with action words)
        words_to_remove = ['cut to','fade in','fade out','close up','wide shot',
                           'aerial shot','establishing shot','zoom in','zoom out']
        for w in words_to_remove:
            clean = re.sub(rf'\b{w}\b[^.]*\.?', '', clean, flags=re.I)
        vo = re.sub(r'\s+', ' ', clean).strip()

    # Remove any remaining "Scene N" artifacts from voiceover
    vo = re.sub(r'\bScene\s*\d+\b', '', vo, flags=re.I)
    vo = re.sub(r'\bHere is the script:?\b', '', vo, flags=re.I)
    vo = re.sub(r'\s+', ' ', vo).strip()

    camera = ' '.join(cam_lines).strip()
    return {"main_script": script, "voiceover": vo, "camera_direction": camera}

async def generate_scenes(script: str, target_count: int = 0, video_style: str = "cinematic",
                           content_type: str = "storytelling", content_format: str = "longform",
                           topic: str = "") -> list[dict]:
    if target_count <= 0:
        tags = len(re.findall(r'\[SCENE', script, re.I))
        target_count = tags if tags >= 3 else (8 if content_format == "shortform" else 10)

    dur = "3" if content_format == "shortform" else "6"
    topic_hint = topic or "this video topic"
    style_note = STYLE_NOTES.get(video_style, "")

    system = "You are a video editor. Break scripts into scenes with specific stock footage search keywords."
    prompt = (
        f"Break this script into exactly {target_count} scenes for stock footage search.\n"
        f"Video topic: {topic_hint}\n"
        f"Style: {video_style}. {style_note}\n"
        f"Content type: {content_type}\n\n"
        "RULES:\n"
        "1. 'description' = 5-8 words of what camera SHOWS (no script text, no asterisks, no brackets)\n"
        f"2. 'keywords' = 6 SPECIFIC stock footage terms about '{topic_hint}'\n"
        "3. Each scene MUST have COMPLETELY DIFFERENT keywords from all other scenes\n"
        "4. FORBIDDEN keywords: 'make footage', 'a video', 'tik tok', 'shot of', 'here is'\n"
        "5. GOOD keywords: specific searchable terms like 'physics equation whiteboard close up'\n"
        "6. 'voiceover_text' = ONLY narrator words, NO camera directions, NO scene numbers\n\n"
        "Return ONLY a JSON array:\n"
        f'[{{"scene":1,"scene_title":"Title","description":"5-8 word visual",'
        f'"keywords":["specific term 1","specific term 2","specific term 3","term 4","term 5","term 6"],'
        f'"voiceover_text":"only narrator words here","camera_direction":"shot type",'
        f'"duration_hint":{dur},"emotion":"curious"}}]\n\n'
        f"Script:\n{script[:2000]}\n\nJSON array ONLY:"
    )

    raw = await ai.ask(prompt, system, timeout=180, task_type="scene_planning")
    scenes = _parse_scenes(raw, topic)
    if target_count > 0 and len(scenes) != target_count:
        scenes = _enforce_count(scenes, target_count, script, topic)

    used_kw = set()
    ADJS = ["historical","modern","detailed","aerial","close-up","wide","dramatic",
            "documentary","authentic","vintage","contemporary","action","emotional","scientific"]
    SUBJS = ["footage","scene","shot","moment","visual","image","clip","view","detail","overview"]

    for i, s in enumerate(scenes):
        # Clean description
        desc = _clean_desc(s.get("description", ""))
        if not desc or len(desc) < 5:
            vo = s.get("voiceover_text", "")
            # Remove any scene/camera artifacts from voiceover_text too
            vo = re.sub(r'\bScene\s*\d+\b', '', vo, flags=re.I)
            vo = re.sub(r'\[[\w\s\d]+\]', '', vo, flags=re.I)
            words = [w for w in vo.split() if len(w) > 3][:6]
            desc = " ".join(words) if words else f"Scene {i+1} visual"
        s["description"] = desc

        # Clean voiceover_text — remove camera artifacts
        vo_text = s.get("voiceover_text", "")
        vo_text = re.sub(r'\bScene\s*\d+\b', '', vo_text, flags=re.I)
        vo_text = re.sub(r'\[[\w\s\d]+\]', '', vo_text, flags=re.I)
        vo_text = re.sub(r'(?:cut to|fade in|fade out|close.?up|wide shot|aerial)', '', vo_text, flags=re.I)
        s["voiceover_text"] = re.sub(r'\s+', ' ', vo_text).strip()

        # Ensure unique keywords per scene
        kw_raw = s.get("keywords", [])
        kw_clean = _clean_kw(kw_raw, topic_hint)
        unique = [k for k in kw_clean if k.lower().strip() not in used_kw]

        if len(unique) < 4:
            adj = ADJS[i % len(ADJS)]
            subj = SUBJS[i % len(SUBJS)]
            variants = [
                f"{topic_hint} {adj}",
                f"{adj} {topic_hint} {subj}",
                f"{topic_hint} {['origin','development','impact','result','process','detail','overview','example'][i%8]}",
                f"{['documentary','cinematic','authentic','dramatic','scientific'][i%5]} {topic_hint}",
                f"{topic_hint} {subj} {i+1}",
                f"{topic_hint} {'people location event action emotion object step concept'.split()[i%8]}",
            ]
            unique = (unique + [v for v in variants if v.lower() not in used_kw])[:6]

        used_kw.update(k.lower().strip() for k in unique[:2])
        s["keywords"] = unique[:6]

    return scenes

def _enforce_count(scenes, target, script, topic=""):
    topic_hint = topic or "footage"
    ADJS = ["historical","modern","dramatic","cinematic","authentic","aerial","close-up","detailed","emotional","vintage"]
    if not scenes:
        return [{
            "scene": i+1, "scene_title": f"Scene {i+1}",
            "description": f"{topic_hint} visual {i+1}",
            "keywords": [f"{topic_hint} {ADJS[i%len(ADJS)]}", f"{ADJS[(i+1)%len(ADJS)]} {topic_hint}",
                         f"{topic_hint} footage {i+1}", f"documentary {topic_hint}",
                         f"{topic_hint} detail", f"{topic_hint} scene"],
            "duration_hint": 6.0, "camera_direction": "Steady shot",
            "voiceover_text": f"Scene {i+1} content.", "emotion": "neutral"
        } for i in range(target)]
    while len(scenes) > target:
        merged = scenes[target-1].copy()
        extras = scenes[target-1:]
        all_kw = []
        for s in extras: all_kw.extend(s.get("keywords", []))
        merged["keywords"] = list(dict.fromkeys(all_kw))[:6]
        scenes = scenes[:target-1] + [merged]
    while len(scenes) < target:
        idx = max(range(len(scenes)), key=lambda i: len(scenes[i].get("description","")))
        orig = scenes[idx]
        clone = orig.copy()
        clone["scene_title"] = f"{orig.get('scene_title','')} (continued)"
        clone["keywords"] = [
            f"{topic_hint} continued {len(scenes)+1}",
            f"{ADJS[len(scenes)%len(ADJS)]} {topic_hint}",
            f"{topic_hint} detail {len(scenes)}",
            f"documentary {topic_hint} {len(scenes)}",
        ]
        scenes.insert(idx+1, clone)
    for i, s in enumerate(scenes): s["scene"] = i+1
    return scenes

def _parse_scenes(raw, topic=""):
    raw = raw.strip()
    if "```" in raw:
        raw = re.sub(r"```[a-z]*\n?", "", raw).strip().rstrip("`").strip()
    def norm(lst):
        out = []
        for i, item in enumerate(lst):
            if not isinstance(item, dict): continue
            out.append({
                "scene":            item.get("scene", i+1),
                "scene_title":      item.get("scene_title", f"Scene {i+1}"),
                "description":      item.get("description", ""),
                "keywords":         item.get("keywords", [])[:10],
                "duration_hint":    float(item.get("duration_hint", 6)),
                "camera_direction": item.get("camera_direction", ""),
                "voiceover_text":   item.get("voiceover_text", ""),
                "emotion":          item.get("emotion", "neutral"),
            })
        return out
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list): return norm(parsed)
        if isinstance(parsed, dict):
            for k in ("scenes","data","result","items"):
                if isinstance(parsed.get(k), list): return norm(parsed[k])
            if "description" in parsed: return norm([parsed])
    except Exception: pass
    m = re.search(r"\[[\s\S]*\]", raw)
    if m:
        try: return norm(json.loads(m.group(0)))
        except Exception: pass
    objs = re.findall(r'\{[^{}]+\}', raw)
    result = []
    for o in objs:
        try: result.append(json.loads(o))
        except Exception: pass
    return norm(result) if result else []

async def generate_narration(script: str) -> str:
    sections = await generate_script_sections(script)
    vo = sections.get("voiceover", "").strip()
    if vo and len(vo) > 30 and "Here is the script" not in vo and "Scene 1" not in vo[:30]:
        return vo
    # Try again with just the script cleaned
    clean = re.sub(r'\[SCENE\s*\d+\][^\n]*\n?', '', script, flags=re.I)
    clean = re.sub(r'\[VOICEOVER\]\s*', '', clean, flags=re.I)
    clean = re.sub(r'(?:Voiceover|VO|Narration|Description):\s*', '', clean, flags=re.I)
    clean = re.sub(r'Scene\s*\d+[^\n]*\n?', '', clean, flags=re.I)
    clean = re.sub(r'\[[\w\s\d]+\]', '', clean, flags=re.I)
    clean = re.sub(r'\*+', '', clean)
    clean = re.sub(r'\bHere is the script:?\b', '', clean, flags=re.I)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

async def generate_subtitle_srt(narration: str, total_duration: float) -> str:
    if not narration or total_duration <= 0: return ""
    words = narration.split()
    if not words: return ""
    words_per = 6
    chunks = [words[i:i+words_per] for i in range(0, len(words), words_per)]
    time_per = total_duration / max(len(chunks), 1)
    lines = []
    for i, chunk in enumerate(chunks):
        s = i * time_per; e = s + time_per - 0.1
        def t(x):
            h=int(x//3600); m=int((x%3600)//60); sc=int(x%60); ms=int((x%1)*1000)
            return f"{h:02d}:{m:02d}:{sc:02d},{ms:03d}"
        lines.append(f"{i+1}\n{t(s)} --> {t(e)}\n{' '.join(chunk)}\n")
    return "\n".join(lines)
