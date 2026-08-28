"""
render_service.py — DEFINITIVE FINAL VERSION
THE ONLY FIX THAT MATTERS: json.dumps(clip_ids) at line where INSERT happens.
"""
import asyncio, json, os, subprocess, uuid, shutil
from pathlib import Path
import aiofiles, httpx
from db import get_db, execute, fetchone

TEMP_DIR   = Path(os.getenv("TEMP_DIR", "./tmp/render"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./outputs"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FORMAT_SIZES = {"landscape":("1280","720"), "portrait":("720","1280"), "square":("1080","1080")}

def _dims(fmt): return FORMAT_SIZES.get(fmt, FORMAT_SIZES["landscape"])
def _run(cmd): return subprocess.run(cmd, capture_output=True, text=True)

def _has_audio(path):
    r = _run(["ffprobe","-v","error","-select_streams","a","-show_entries","stream=codec_type","-of","json",str(path)])
    try: return bool(json.loads(r.stdout).get("streams"))
    except: return False

def _update(job_id, status, progress=0, error=None):
    conn = get_db()
    execute(conn, "UPDATE render_jobs SET status=%s,progress=%s,error_message=%s,updated_at=NOW() WHERE job_id=%s",
            (status, progress, error, job_id))
    conn.commit(); conn.close()

def create_job(project_id, clip_ids, voiceover_id=None, music_id=None, subtitle_id=None):
    """
    clip_ids MUST be stored as JSON string in PostgreSQL JSONB column.
    Whether clip_ids arrives as list or already-dumped string, we handle both.
    """
    job_id = str(uuid.uuid4())
    # Handle both cases: raw list OR already json string OR anything else
    if isinstance(clip_ids, str):
        try:
            # Validate it's valid JSON
            json.loads(clip_ids)
            clip_ids_str = clip_ids
        except Exception:
            clip_ids_str = json.dumps([])
    elif isinstance(clip_ids, (list, tuple)):
        clip_ids_str = json.dumps(list(clip_ids))
    else:
        clip_ids_str = json.dumps([])

    conn = get_db()
    execute(conn,
        "INSERT INTO render_jobs (job_id,project_id,clip_ids,voiceover_id,music_id,subtitle_id,status,progress) "
        "VALUES (%s,%s,%s,%s,%s,%s,'queued',0)",
        (job_id, project_id, clip_ids_str, voiceover_id, music_id, subtitle_id))
    conn.commit(); conn.close()
    return job_id

async def run_render(job_id, project_id, clip_urls, voiceover_path=None,
                     music_path=None, srt_content=None, subtitle_preset="minimal",
                     video_format="landscape", image_paths=None):
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    w, h = _dims(video_format)

    try:
        _update(job_id, "downloading", 5)
        local_clips = []

        # Pre-check: convert any local /uploads/ URLs to file paths
        resolved_clip_urls = []
        for curl in clip_urls:
            if curl.startswith("/uploads/") or curl.startswith("/outputs/"):
                # Local file — convert to absolute path
                local_p = Path(".") / curl.lstrip("/")
                if local_p.exists():
                    resolved_clip_urls.append(f"file:{local_p.absolute()}")
                else:
                    resolved_clip_urls.append(curl)
            else:
                resolved_clip_urls.append(curl)
        clip_urls = resolved_clip_urls

        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            for i, url in enumerate(clip_urls):
                _update(job_id, "downloading", 5 + int((i / max(len(clip_urls), 1)) * 25))
                dest = job_dir / f"clip_{i:03d}.mp4"
                try:
                    # Handle local file:// protocol (custom uploaded clips)
                    if url.startswith("file:"):
                        local_src = Path(url[5:])
                        if local_src.exists():
                            import shutil
                            shutil.copy2(str(local_src), str(dest))
                            local_clips.append(dest)
                        continue
                    # Handle http:// 127.0.0.1 local server clips
                    if "127.0.0.1:8000/uploads" in url:
                        rel = url.split("127.0.0.1:8000")[1]
                        local_src = Path(".") / rel.lstrip("/")
                        if local_src.exists():
                            import shutil
                            shutil.copy2(str(local_src), str(dest))
                            local_clips.append(dest)
                        continue
                    async with client.stream("GET", url) as resp:
                        if resp.status_code != 200: continue
                        async with aiofiles.open(dest, "wb") as f:
                            async for chunk in resp.aiter_bytes(65536): await f.write(chunk)
                    if dest.exists() and dest.stat().st_size > 1000:
                        local_clips.append(dest)
                except Exception as e:
                    print(f"[render] clip {i} skip: {e}")

        if image_paths:
            for j, img in enumerate(image_paths):
                img_path = Path(img)
                # Try absolute path, then relative to backend dir
                if not img_path.exists():
                    # Try relative from current working dir
                    alt = Path(".") / str(img).lstrip("/\\")
                    if alt.exists():
                        img_path = alt
                    else:
                        print(f"[render] image not found: {img}")
                        continue
                print(f"[render] adding image: {img_path}")
                out = job_dir / f"img_{j:03d}.mp4"
                r = _run(["ffmpeg","-y","-loop","1","-i",str(img_path),
                          "-c:v","libx264","-preset","fast","-t","4",
                          "-pix_fmt","yuv420p","-vf",
                          f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black",
                          "-r","30",str(out)])
                if r.returncode == 0 and out.exists():
                    local_clips.append(out)
                    print(f"[render] image clip created: {out}")
                else:
                    print(f"[render] image to video failed: {r.stderr[-200:] if hasattr(r,'stderr') else ''}")

        if not local_clips:
            raise RuntimeError("No clips downloaded. Check API keys and internet connection.")

        _update(job_id, "normalizing", 32)
        norm = []
        for i, clip in enumerate(local_clips):
            out = job_dir / f"norm_{i:03d}.mp4"
            r = _run(["ffmpeg","-y","-i",str(clip),
                      "-vf",f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black",
                      "-r","30","-c:v","libx264","-preset","fast","-crf","23",
                      "-c:a","aac","-ar","44100","-ac","2",str(out)])
            norm.append(out if r.returncode == 0 and out.exists() else clip)

        _update(job_id, "rendering", 50)
        listf = job_dir / "list.txt"
        listf.write_text("\n".join(f"file '{p}'" for p in norm))
        concat = job_dir / "concat.mp4"
        r = _run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(listf),
                  "-c:v","libx264","-preset","fast","-crf","23",
                  "-c:a","aac","-ar","44100","-ac","2",str(concat)])
        if r.returncode != 0: raise RuntimeError(f"Concat failed: {r.stderr[-400:]}")
        current = concat

        if voiceover_path and Path(voiceover_path).exists():
            _update(job_id, "mixing voiceover", 63)
            vo_out = job_dir / "with_vo.mp4"
            if _has_audio(str(current)):
                r = _run(["ffmpeg","-y","-i",str(current),"-i",voiceover_path,
                          "-filter_complex","[0:a][1:a]amix=inputs=2:duration=longest:weights=0.2 1[aout]",
                          "-map","0:v","-map","[aout]","-c:v","copy","-c:a","aac","-shortest",str(vo_out)])
            else:
                r = _run(["ffmpeg","-y","-i",str(current),"-i",voiceover_path,
                          "-map","0:v","-map","1:a","-c:v","copy","-c:a","aac","-shortest",str(vo_out)])
            if r.returncode == 0 and vo_out.exists(): current = vo_out

        # Music: resolve file_path OR URL — multiple strategies
        resolved_music = None

        if music_path:
            # Strategy 1: direct file path exists
            if Path(music_path).exists():
                resolved_music = music_path
                print(f"[render] music from file: {music_path}")

            # Strategy 2: HTTP/HTTPS URL — download with httpx (handles redirects)
            elif music_path.startswith("http://") or music_path.startswith("https://"):
                try:
                    import asyncio as _asyncio
                    music_dl = job_dir / "music_dl.mp3"
                    print(f"[render] downloading music: {music_path[:80]}")
                    # Use sync httpx since we are in sync context
                    import httpx as _httpx
                    with _httpx.Client(timeout=90, follow_redirects=True) as hc:
                        resp = hc.get(music_path, headers={"User-Agent": "DashClip/4.0"})
                        if resp.status_code == 200:
                            music_dl.write_bytes(resp.content)
                    if music_dl.exists() and music_dl.stat().st_size > 2000:
                        resolved_music = str(music_dl)
                        print(f"[render] music OK: {music_dl.stat().st_size:,} bytes")
                    else:
                        print(f"[render] music download failed or too small")
                except Exception as e:
                    print(f"[render] music download error: {e}")

            # Strategy 3: relative /uploads path
            elif music_path.startswith("/uploads/"):
                local = Path(".") / music_path.lstrip("/")
                if local.exists():
                    resolved_music = str(local)
                    print(f"[render] music from uploads: {local}")

        if not resolved_music:
            print(f"[render] WARNING: no music resolved from path={music_path} — video will have no background music")

        if resolved_music:
            _update(job_id, "mixing music", 73)
            mu_out = job_dir / "with_music.mp4"
            if _has_audio(str(current)):
                r = _run(["ffmpeg","-y","-i",str(current),"-i",resolved_music,
                          "-filter_complex","[1:a]aresample=44100,volume=0.25[bg];[0:a][bg]amix=inputs=2:duration=first[aout]",
                          "-map","0:v","-map","[aout]","-c:v","copy","-c:a","aac",str(mu_out)])
            else:
                r = _run(["ffmpeg","-y","-i",str(current),"-i",resolved_music,
                          "-map","0:v","-map","1:a","-c:v","copy","-c:a","aac",
                          "-af","volume=0.25","-shortest",str(mu_out)])
            if r.returncode == 0 and mu_out.exists(): current = mu_out

        if srt_content:
            _update(job_id, "burning subtitles", 82)
            srt_path = job_dir / "subs.srt"
            srt_path.write_text(srt_content, encoding="utf-8")
            sub_out = job_dir / "with_subs.mp4"
            styles = {
                "portrait":  "FontName=Arial,FontSize=18,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Alignment=2,MarginV=80",
                "square":    "FontName=Arial,FontSize=20,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Alignment=2,MarginV=50",
                "landscape": "FontName=Arial,FontSize=22,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2,Alignment=2,MarginV=40",
            }
            style = styles.get(video_format, styles["landscape"])
            srt_esc = str(srt_path).replace("\\", "/").replace(":", "\\:")
            r = _run(["ffmpeg","-y","-i",str(current),
                      "-vf",f"subtitles='{srt_esc}':force_style='{style}'",
                      "-c:v","libx264","-preset","fast","-crf","23","-c:a","copy",str(sub_out)])
            if r.returncode == 0 and sub_out.exists(): current = sub_out

        _update(job_id, "adding watermark", 93)
        wm = Path(__file__).parent.parent / "static" / "watermark.png"
        final_name = f"dashclip_{project_id}_{job_id[:8]}.mp4"
        final = OUTPUT_DIR / final_name
        if wm.exists():
            r = _run(["ffmpeg","-y","-i",str(current),"-i",str(wm),
                      "-filter_complex","[1:v]scale=120:-1,format=rgba,colorchannelmixer=aa=0.5[wm];[0:v][wm]overlay=W-w-10:H-h-10",
                      "-c:v","libx264","-preset","fast","-crf","23","-c:a","copy",str(final)])
            if r.returncode != 0 or not final.exists():
                shutil.copy(current, final)
        else:
            shutil.copy(current, final)

        conn = get_db()
        execute(conn,
            "UPDATE render_jobs SET status='completed',progress=100,output_path=%s,updated_at=NOW() WHERE job_id=%s",
            (str(final), job_id))
        conn.commit(); conn.close()

    except Exception as e:
        print(f"[render] FATAL: {e}")
        _update(job_id, "failed", 0, str(e))

async def get_render_status(job_id):
    conn = get_db()
    row = fetchone(conn, "SELECT * FROM render_jobs WHERE job_id=%s", (job_id,))
    conn.close()
    if not row: raise ValueError("Job not found")
    return {
        "status":   row["status"],
        "progress": row["progress"] or 0,
        "output":   f"/outputs/{Path(row['output_path']).name}" if row.get("output_path") else None,
        "error":    row.get("error_message"),
    }
