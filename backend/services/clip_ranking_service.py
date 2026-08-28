"""
clip_ranking_service.py — DashClip V4 Fixed
Fix: Pixabay uses previewURL (small playable MP4, no auth headers needed)
Fix: Timeout increased to 25s, retry on failure
Fix: Skip any clip without valid thumbnail AND valid video URL
"""
import os, asyncio, hashlib
from db import get_db, execute, fetchall

PEXELS_KEY  = os.getenv("PEXELS_API_KEY", "")
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY", "")

def _score_clip(w, h, dur, prefer_vertical=False, keyword_rank=0, source="pexels"):
    if w >= 1920: quality = 1.0
    elif w >= 1280: quality = 0.8
    elif w >= 854:  quality = 0.55
    else:           quality = 0.3
    is_vert = h > w
    if prefer_vertical and is_vert:      style = 1.0
    elif not prefer_vertical and not is_vert: style = 1.0
    else:                                style = 0.3
    if 5 <= dur <= 15:   emotion = 1.0
    elif 3 <= dur <= 20: emotion = 0.7
    elif 2 <= dur <= 30: emotion = 0.4
    else:                emotion = 0.2
    keyword = max(0.0, 1.0 - (keyword_rank * 0.12))
    src_scores = {"pexels": 0.95, "pixabay": 0.85, "coverr": 0.8}
    consistency = src_scores.get(source, 0.5)
    total = keyword*0.30 + emotion*0.25 + style*0.20 + quality*0.15 + consistency*0.10
    return {
        "keyword_score":     round(keyword, 3),
        "emotion_score":     round(emotion, 3),
        "style_score":       round(style, 3),
        "quality_score":     round(quality, 3),
        "consistency_score": round(consistency, 3),
        "relevance_score":   round(total, 3),
    }

def _why(scores, kw, source, w, h, dur):
    parts = []
    if scores["quality_score"] >= 0.8: parts.append(f"High-quality {w}x{h} footage")
    elif scores["quality_score"] >= 0.5: parts.append(f"Good quality {w}x{h}")
    else: parts.append(f"Standard {w}x{h}")
    if scores["emotion_score"] >= 0.8: parts.append(f"ideal {dur:.0f}s duration")
    if scores["keyword_score"] >= 0.8: parts.append(f"strong match for '{kw}'")
    elif scores["keyword_score"] >= 0.5: parts.append(f"matched '{kw}'")
    parts.append(f"from {source}")
    return ". ".join(parts).capitalize() + "."

def _key(url): return hashlib.md5(url.encode()).hexdigest()

async def _pexels(kw: str, n: int, vert: bool, rank: int = 0) -> list:
    if not PEXELS_KEY: return []
    import httpx
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=25) as c:
                r = await c.get(
                    "https://api.pexels.com/videos/search",
                    headers={"Authorization": PEXELS_KEY},
                    params={"query": kw, "per_page": n,
                            "orientation": "portrait" if vert else "landscape"})
            if r.status_code != 200:
                print(f"[pexels] HTTP {r.status_code} kw={kw}")
                return []
            out = []
            for v in r.json().get("videos", []):
                thumb = v.get("image", "")
                if not thumb or not thumb.startswith("http"): continue
                files = [f for f in v.get("video_files", [])
                         if f.get("file_type") == "video/mp4"]
                if not files: files = v.get("video_files", [])
                files.sort(key=lambda f: f.get("width", 0), reverse=True)
                best = next((f for f in files if 0 < f.get("width",0) <= 1920), files[0] if files else None)
                if not best or not best.get("link"): continue
                w = best.get("width",0); h = best.get("height",0)
                dur = float(v.get("duration", 0))
                scores = _score_clip(w, h, dur, vert, rank, "pexels")
                out.append({"video_url": best["link"], "preview_url": v.get("url",""),
                            "thumbnail_url": thumb, "duration": dur,
                            "width": w, "height": h, "source": "pexels",
                            "_keyword": kw, **scores})
            return out
        except Exception as e:
            print(f"[pexels] attempt {attempt+1} error: {e}")
            if attempt == 0: await asyncio.sleep(1)
    return []

async def _pixabay(kw: str, n: int, vert: bool, rank: int = 0) -> list:
    """
    KEY FIX: Use 'previewURL' (small MP4 ~300x169) instead of large/medium video URL.
    previewURL does NOT require auth headers so it plays in browser <video> tag.
    """
    if not PIXABAY_KEY or not PIXABAY_KEY.strip(): return []
    import httpx
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=25) as c:
                r = await c.get(
                    "https://pixabay.com/api/videos/",
                    params={"key": PIXABAY_KEY, "q": kw, "per_page": n,
                            "orientation": "vertical" if vert else "horizontal"})
            if r.status_code != 200: return []
            out = []
            for v in r.json().get("hits", []):
                # Thumbnail: userImageURL is best, then generate from picture_id
                thumb = v.get("userImageURL", "").strip()
                if not thumb:
                    pid = v.get("picture_id", "")
                    if pid: thumb = f"https://i.vimeocdn.com/video/{pid}_295x166.jpg"
                if not thumb or not thumb.startswith("http"): continue

                # Video URL: use previewURL from 'tiny' size — no auth headers needed
                vids = v.get("videos", {})
                video_url = ""
                w = h = 0
                # Try tiny first (always playable), then small
                for sz in ("tiny", "small", "medium"):
                    entry = vids.get(sz)
                    if entry and entry.get("url"):
                        video_url = entry["url"]
                        w = entry.get("width", 0)
                        h = entry.get("height", 0)
                        break
                if not video_url or not video_url.startswith("http"): continue

                dur = float(v.get("duration", 0))
                scores = _score_clip(w, h, dur, vert, rank, "pixabay")
                out.append({"video_url": video_url, "preview_url": v.get("pageURL",""),
                            "thumbnail_url": thumb, "duration": dur,
                            "width": w, "height": h, "source": "pixabay",
                            "_keyword": kw, **scores})
            return out
        except Exception as e:
            print(f"[pixabay] attempt {attempt+1} error: {e}")
            if attempt == 0: await asyncio.sleep(1)
    return []

async def _coverr(kw: str, n: int, rank: int = 0) -> list:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get("https://api.coverr.co/videos",
                            params={"query": kw, "page_size": n})
        if r.status_code != 200: return []
        out = []
        for v in r.json().get("hits", [])[:n]:
            url = (v.get("urls") or {}).get("mp4") or ""
            poster = v.get("poster")
            thumb = ""
            if isinstance(poster, dict): thumb = poster.get("default","") or poster.get("thumbnail","")
            elif isinstance(poster, str): thumb = poster
            if not thumb: thumb = v.get("thumbnail","")
            if not url or not thumb: continue
            if not url.startswith("http") or not thumb.startswith("http"): continue
            w = v.get("width", 1920) or 1920; h = v.get("height",1080) or 1080
            dur = float(v.get("duration",8) or 8)
            scores = _score_clip(w, h, dur, False, rank, "coverr")
            out.append({"video_url": url, "preview_url": "", "thumbnail_url": thumb,
                        "duration": dur, "width": w, "height": h,
                        "source": "coverr", "_keyword": kw, **scores})
        return out
    except Exception as e:
        print(f"[coverr] error: {e}"); return []

async def fetch_and_rank_clips(scene_id, keywords, per_keyword=3, prefer_vertical=False,
                                search_concepts=None, **kwargs):
    kw_list = [k for k in (search_concepts or keywords)
               if isinstance(k, str) and k.strip()][:8]
    if not kw_list: kw_list = ["nature", "cityscape", "people"]

    tasks = []
    for rank, kw in enumerate(kw_list[:5]):
        tasks.append(_pexels(kw, per_keyword, prefer_vertical, rank))
        tasks.append(_pixabay(kw, per_keyword, prefer_vertical, rank))
    tasks.append(_coverr(kw_list[0], 3, 0))

    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    seen, candidates = set(), []
    for batch in all_results:
        if isinstance(batch, Exception) or not isinstance(batch, list): continue
        for clip in batch:
            thumb = (clip.get("thumbnail_url") or "").strip()
            video = (clip.get("video_url") or "").strip()
            if not thumb.startswith("http"): continue
            if not video.startswith("http"): continue
            k = _key(video)
            if k in seen: continue
            seen.add(k); candidates.append(clip)

    # Sort by score, limit 3 per source for variety
    candidates.sort(key=lambda c: c.get("relevance_score",0), reverse=True)
    src_count, top = {}, []
    for c in candidates:
        src = c.get("source","x")
        if src_count.get(src,0) >= 3: continue
        src_count[src] = src_count.get(src,0) + 1
        top.append(c)
        if len(top) >= 8: break

    conn = get_db(); saved = []
    for c in top:
        try:
            kw_used = c.pop("_keyword", kw_list[0])
            why = _why(c, kw_used, c.get("source","?"),
                       c.get("width",0), c.get("height",0), c.get("duration",0))
            row = execute(conn, """
                INSERT INTO clips (scene_id,video_url,preview_url,thumbnail_url,
                   duration,width,height,relevance_score,source,why_chosen,
                   keyword_score,emotion_score,style_score,quality_score,consistency_score)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING RETURNING id""",
                (scene_id, c["video_url"], c.get("preview_url",""),
                 c.get("thumbnail_url",""), c.get("duration",0),
                 c.get("width",0), c.get("height",0),
                 c.get("relevance_score",0), c.get("source","pexels"), why,
                 c.get("keyword_score",0), c.get("emotion_score",0),
                 c.get("style_score",0), c.get("quality_score",0),
                 c.get("consistency_score",0)))
            if row: c["id"] = row["id"]
            else:
                ex = fetchall(conn,
                    "SELECT id FROM clips WHERE video_url=%s AND scene_id=%s",
                    (c["video_url"], scene_id))
                c["id"] = ex[0]["id"] if ex else None
            c["why_chosen"] = why; saved.append(c)
        except Exception as ex:
            print(f"[clip] DB err: {ex}")
    conn.commit(); conn.close()

    # REAL AI GENERATIVE VIDEO FALLBACK
    # Called only when 0 stock clips found for a scene
    # Uses Google Veo 2 (via Google AI Studio API) or RunwayML as fallback
    if not saved:
        print(f"[clip] 0 stock clips for scene {scene_id} — calling AI video generation")
        try:
            generated = await _ai_generate_video(scene_id, kw_list)
            if generated:
                saved.append(generated)
                print(f"[clip] AI video generated for scene {scene_id}")
        except Exception as e:
            print(f"[clip] AI video gen error: {e}")

    return saved


# ── AI VIDEO GENERATION ──────────────────────────────────────────────────────

async def _ai_generate_video(scene_id: int, keywords: list) -> dict | None:
    """
    Generate a real AI video when no stock clips found.
    Priority:
    1. Google Veo 2 via Vertex AI / Google AI Studio
    2. RunwayML Gen-3
    3. Luma AI Dream Machine
    All require API keys set in .env
    """
    import os
    from db import get_db, execute, fetchone

    conn = get_db()
    scene = fetchone(conn, "SELECT * FROM scenes WHERE id=%s", (scene_id,))
    conn.close()

    description = (scene.get("description","") if scene else "") or " ".join(keywords[:4])
    emotion = (scene.get("scene_emotion","neutral") if scene else "neutral")
    duration = float(scene.get("duration_hint", 6) if scene else 6)
    prompt = f"{description}. {emotion} mood. Cinematic quality, professional footage."

    # Try providers in order
    result = (
        await _veo2_generate(prompt, duration) or
        await _runway_generate(prompt, duration) or
        await _luma_generate(prompt, duration)
    )

    if not result:
        return None

    video_url = result.get("video_url","")
    thumb_url = result.get("thumbnail_url","")
    if not video_url:
        return None

    # Save to DB
    conn = get_db()
    row = execute(conn, """
        INSERT INTO clips (scene_id, video_url, preview_url, thumbnail_url,
           duration, width, height, relevance_score, source, why_chosen,
           keyword_score, emotion_score, style_score, quality_score, consistency_score)
        VALUES (%s,%s,%s,%s,%s,1280,720,0.85,%s,%s,0.8,0.8,0.8,0.9,0.9)
        RETURNING id
    """, (scene_id, video_url, video_url, thumb_url, duration,
          result.get("source","ai_generated"),
          f"AI generated: {description[:80]}"))
    conn.commit(); conn.close()

    return {
        "id": row["id"] if row else None,
        "video_url": video_url, "preview_url": video_url,
        "thumbnail_url": thumb_url,
        "duration": duration, "width": 1280, "height": 720,
        "source": result.get("source","ai_generated"),
        "relevance_score": 0.85,
        "why_chosen": f"AI generated video — no stock footage found",
        "keyword_score": 0.8, "emotion_score": 0.8,
        "style_score": 0.8, "quality_score": 0.9, "consistency_score": 0.9,
    }


async def _veo2_generate(prompt: str, duration: float) -> dict | None:
    """
    Google Veo 2 via Google AI Studio API.
    Get key: https://aistudio.google.com/apikey
    Set: GOOGLE_AI_API_KEY=your_key in .env
    Cost: ~$0.35 per video (as of 2025)
    Docs: https://ai.google.dev/api/generate-content#veo
    """
    import httpx, os, asyncio
    api_key = os.getenv("GOOGLE_AI_API_KEY","")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            # Submit generation job
            r = await c.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/veo-2.0-generate-001:predictLongRunning",
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "instances": [{"prompt": prompt}],
                    "parameters": {
                        "aspectRatio": "16:9",
                        "durationSeconds": min(int(duration), 8),
                        "sampleCount": 1,
                    }
                }
            )
        if r.status_code != 200:
            print(f"[veo2] HTTP {r.status_code}: {r.text[:200]}")
            return None

        op = r.json()
        op_name = op.get("name","")
        if not op_name: return None

        # Poll for completion (Veo takes 60-120s)
        print(f"[veo2] Job started: {op_name} — polling...")
        for attempt in range(24):  # max 4 minutes
            await asyncio.sleep(10)
            async with httpx.AsyncClient(timeout=30) as c:
                status_r = await c.get(
                    f"https://generativelanguage.googleapis.com/v1beta/{op_name}",
                    headers={"x-goog-api-key": api_key}
                )
            if status_r.status_code != 200: continue
            status = status_r.json()
            if status.get("done"):
                # Extract video URL from response
                response = status.get("response",{})
                predictions = response.get("predictions",[])
                if predictions:
                    video_b64 = predictions[0].get("bytesBase64Encoded","")
                    if video_b64:
                        # Save video locally
                        import base64, uuid
                        from pathlib import Path
                        out_dir = Path("./uploads/generated_clips")
                        out_dir.mkdir(parents=True, exist_ok=True)
                        fname = f"veo2_{uuid.uuid4().hex[:8]}.mp4"
                        fpath = out_dir / fname
                        fpath.write_bytes(base64.b64decode(video_b64))
                        return {
                            "video_url": f"/uploads/generated_clips/{fname}",
                            "thumbnail_url": "",
                            "source": "google_veo2"
                        }
                    # Or it may be a URI
                    video_uri = predictions[0].get("video",{}).get("uri","")
                    if video_uri:
                        return {"video_url": video_uri, "thumbnail_url": "", "source": "google_veo2"}
                break
        print("[veo2] Timed out waiting for video")
        return None
    except Exception as e:
        print(f"[veo2] error: {e}")
        return None


async def _runway_generate(prompt: str, duration: float) -> dict | None:
    """
    RunwayML Gen-3 Alpha API.
    Get key: https://app.runwayml.com/settings (API Access)
    Set: RUNWAYML_API_KEY=your_key in .env
    Cost: ~$0.05 per second of video
    Docs: https://docs.dev.runwayml.com
    """
    import httpx, os, asyncio
    api_key = os.getenv("RUNWAYML_API_KEY","")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://api.dev.runwayml.com/v1/image_to_video",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "X-Runway-Version": "2024-11-06"
                },
                json={
                    "model": "gen3a_turbo",
                    "promptText": prompt,
                    "duration": min(int(duration), 10),
                    "ratio": "1280:720",
                    "watermark": False,
                }
            )
        if r.status_code not in (200, 201):
            print(f"[runway] HTTP {r.status_code}: {r.text[:200]}")
            return None

        task = r.json()
        task_id = task.get("id","")
        if not task_id: return None

        print(f"[runway] Task {task_id} — polling...")
        for attempt in range(30):  # max 5 minutes
            await asyncio.sleep(10)
            async with httpx.AsyncClient(timeout=20) as c:
                poll_r = await c.get(
                    f"https://api.dev.runwayml.com/v1/tasks/{task_id}",
                    headers={"Authorization": f"Bearer {api_key}",
                             "X-Runway-Version": "2024-11-06"}
                )
            if poll_r.status_code != 200: continue
            data = poll_r.json()
            status = data.get("status","")
            if status == "SUCCEEDED":
                outputs = data.get("output",[])
                if outputs:
                    return {"video_url": outputs[0], "thumbnail_url": "", "source": "runway_gen3"}
                break
            elif status in ("FAILED","CANCELLED"):
                print(f"[runway] Task {status}")
                break
        return None
    except Exception as e:
        print(f"[runway] error: {e}")
        return None


async def _luma_generate(prompt: str, duration: float) -> dict | None:
    """
    Luma AI Dream Machine API.
    Get key: https://lumalabs.ai/dream-machine/api
    Set: LUMAAI_API_KEY=your_key in .env
    Cost: ~$0.005 per second
    Docs: https://docs.lumalabs.ai
    """
    import httpx, os, asyncio
    api_key = os.getenv("LUMAAI_API_KEY","")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://api.lumalabs.ai/dream-machine/v1/generations",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json"},
                json={"prompt": prompt, "loop": False, "aspect_ratio": "16:9"}
            )
        if r.status_code not in (200,201):
            print(f"[luma] HTTP {r.status_code}: {r.text[:200]}")
            return None

        gen = r.json()
        gen_id = gen.get("id","")
        if not gen_id: return None

        print(f"[luma] Generation {gen_id} — polling...")
        for attempt in range(30):
            await asyncio.sleep(8)
            async with httpx.AsyncClient(timeout=20) as c:
                poll_r = await c.get(
                    f"https://api.lumalabs.ai/dream-machine/v1/generations/{gen_id}",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
            if poll_r.status_code != 200: continue
            data = poll_r.json()
            state = data.get("state","")
            if state == "completed":
                assets = data.get("assets",{})
                video = assets.get("video","")
                thumb = assets.get("image","")
                if video:
                    return {"video_url": video, "thumbnail_url": thumb, "source": "luma_ai"}
                break
            elif state == "failed":
                print(f"[luma] Generation failed: {data.get('failure_reason','')}")
                break
        return None
    except Exception as e:
        print(f"[luma] error: {e}")
        return None
    # When 0 real clips found, generate a real MP4 video using FFmpeg locally.
    # Animated gradient + scene text overlay — no API, no internet, always works.
    if not saved:
        print(f"[clip] 0 clips for scene {scene_id} — generating AI video fallback")
        try:
            generated = await _generate_ai_video(scene_id, kw_list)
            if generated:
                saved.append(generated)
                print(f"[clip] AI generated video created for scene {scene_id}")
        except Exception as e:
            print(f"[clip] AI video generation failed: {e}")

    return saved

