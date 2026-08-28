"""
render_service.py
Full async render pipeline:
  1. Download clips
  2. Normalize to 1280x720 H264
  3. Concatenate
  4. Mix voiceover (optional)
  5. Mix background music at low volume (optional)
  6. Burn subtitles (optional)
  7. Cleanup temp files
"""
import os
import uuid
import asyncio
import subprocess
import shutil
from pathlib import Path

import httpx
import aiofiles

from db import get_db, execute, fetchone

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./outputs"))
TEMP_DIR   = Path(os.getenv("TEMP_DIR",   str(Path.home() / "ai_script_video_clips")))

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# In-memory job status store (sufficient for V1 single-server)
render_jobs: dict[str, dict] = {}


def create_job(project_id: int, clip_ids: list[int],
               voiceover_id: int | None = None,
               music_id: int | None = None,
               subtitle_id: int | None = None) -> str:
    job_id = str(uuid.uuid4())
    render_jobs[job_id] = {
        "status": "queued", "progress": 0,
        "output": None, "error": None
    }

    conn = get_db()
    execute(conn,
        """INSERT INTO render_jobs
           (project_id, job_id, status, clip_ids, voiceover_id, music_id, subtitle_id)
           VALUES (%s,%s,'queued',%s,%s,%s,%s)""",
        (project_id, job_id, clip_ids, voiceover_id, music_id, subtitle_id)
    )
    conn.commit()
    conn.close()
    return job_id


def get_job_status(job_id: str) -> dict | None:
    return render_jobs.get(job_id)


def _update(job_id: str, **kwargs):
    if job_id in render_jobs:
        render_jobs[job_id].update(kwargs)

    # Also persist to DB
    conn = get_db()
    sets = [f"{k} = %s" for k in kwargs if k in ("status", "progress", "output_path", "error_message")]
    vals = [kwargs[k] for k in kwargs if k in ("status", "progress", "output_path", "error_message")]
    if sets:
        vals.append(job_id)
        execute(conn, f"UPDATE render_jobs SET {', '.join(sets)} WHERE job_id = %s", tuple(vals))
        conn.commit()
    conn.close()


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


async def run_render(job_id: str, project_id: int, clip_urls: list[str],
                     voiceover_path: str | None = None,
                     music_path: str | None = None,
                     srt_content: str | None = None,
                     subtitle_preset: str = "minimal"):
    """Main async render function — called as a background task."""
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        # ── 1. Download clips ──────────────────────────────────────────────
        _update(job_id, status="downloading", progress=5)
        local_clips = []

        async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
            for i, url in enumerate(clip_urls):
                pct = 5 + int((i / len(clip_urls)) * 30)
                _update(job_id, progress=pct)
                clip_path = job_dir / f"clip_{i:03d}.mp4"

                async with client.stream("GET", url) as resp:
                    if resp.status_code != 200:
                        raise RuntimeError(f"Download failed for clip {i}: HTTP {resp.status_code}")
                    async with aiofiles.open(clip_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(65536):
                            await f.write(chunk)
                local_clips.append(clip_path)

        # ── 2. Normalize each clip ─────────────────────────────────────────
        _update(job_id, status="normalizing", progress=35)
        norm_clips = []

        for i, clip in enumerate(local_clips):
            norm = job_dir / f"norm_{i:03d}.mp4"
            r = _run([
                "ffmpeg", "-y", "-i", str(clip),
                "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,"
                       "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "-r", "30",
                str(norm)
            ])
            if r.returncode != 0:
                raise RuntimeError(f"Normalize clip {i} failed: {r.stderr[-400:]}")
            norm_clips.append(norm)
            _update(job_id, progress=35 + int((i / len(norm_clips)) * 20))

        # ── 3. Concatenate ─────────────────────────────────────────────────
        _update(job_id, status="rendering", progress=55)

        concat_txt = job_dir / "concat.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for clip in norm_clips:
                safe = str(clip.resolve()).replace("\\", "/")
                f.write(f"file '{safe}'\n")

        concat_out = job_dir / "concat.mp4"
        r = _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_txt), "-c", "copy", str(concat_out)
        ])
        if r.returncode != 0:
            raise RuntimeError(f"Concat failed: {r.stderr[-400:]}")

        current = concat_out
        _update(job_id, progress=65)

        # ── 4. Mix voiceover ───────────────────────────────────────────────
        if voiceover_path and Path(voiceover_path).exists():
            _update(job_id, status="mixing voiceover", progress=70)
            vo_out = job_dir / "with_vo.mp4"
            r = _run([
                "ffmpeg", "-y",
                "-i", str(current),
                "-i", voiceover_path,
                "-filter_complex",
                "[0:a]volume=0.15[orig];[1:a]volume=1.0[vo];[orig][vo]amix=inputs=2:duration=first[a]",
                "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", str(vo_out)
            ])
            if r.returncode != 0:
                raise RuntimeError(f"Voiceover mix failed: {r.stderr[-400:]}")
            current = vo_out

        # ── 5. Mix background music ────────────────────────────────────────
        if music_path and Path(music_path).exists():
            _update(job_id, status="mixing music", progress=78)
            music_out = job_dir / "with_music.mp4"
            r = _run([
                "ffmpeg", "-y",
                "-i", str(current),
                "-i", music_path,
                "-filter_complex",
                "[0:a]volume=1.0[main];[1:a]volume=0.12,aloop=loop=-1:size=2e+09[bg];[main][bg]amix=inputs=2:duration=first[a]",
                "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", str(music_out)
            ])
            if r.returncode != 0:
                raise RuntimeError(f"Music mix failed: {r.stderr[-400:]}")
            current = music_out

        # ── 6. Burn subtitles ──────────────────────────────────────────────
        if srt_content and srt_content.strip():
            _update(job_id, status="burning subtitles", progress=85)
            from services.subtitle_service import burn_subtitles, SUBTITLE_PRESETS

            srt_path = job_dir / "subtitles.srt"
            srt_path.write_text(srt_content, encoding="utf-8")

            style = SUBTITLE_PRESETS.get(subtitle_preset, SUBTITLE_PRESETS["minimal"])
            style_str = ",".join(f"{k}={v}" for k, v in style.items())
            srt_safe = str(srt_path.resolve()).replace("\\", "/").replace(":", "\\:")

            sub_out = job_dir / "with_subs.mp4"
            r = _run([
                "ffmpeg", "-y",
                "-i", str(current),
                "-vf", f"subtitles='{srt_safe}':force_style='{style_str}'",
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "copy",
                str(sub_out)
            ])
            if r.returncode != 0:
                raise RuntimeError(f"Subtitle burn failed: {r.stderr[-400:]}")
            current = sub_out

        # ── 7. Copy to output ──────────────────────────────────────────────
        _update(job_id, progress=95)
        out_name = f"project_{project_id}_{job_id[:8]}.mp4"
        out_path = OUTPUT_DIR / out_name
        shutil.copy2(str(current), str(out_path))

        # Update DB
        conn = get_db()
        execute(conn,
            "UPDATE projects SET output_video_path=%s, status='rendered', updated_at=NOW() WHERE id=%s",
            (str(out_path), project_id)
        )
        execute(conn,
            "UPDATE render_jobs SET status='completed', progress=100, output_path=%s, completed_at=NOW() WHERE job_id=%s",
            (str(out_path), job_id)
        )
        conn.commit()
        conn.close()

        render_jobs[job_id] = {
            "status":   "completed",
            "progress": 100,
            "output":   f"/outputs/{out_name}",
            "error":    None
        }

    except Exception as e:
        err = str(e)
        _update(job_id, status="failed", error_message=err)
        render_jobs[job_id] = {
            "status":   "failed",
            "progress": render_jobs.get(job_id, {}).get("progress", 0),
            "output":   None,
            "error":    err
        }
    finally:
        try:
            shutil.rmtree(job_dir, ignore_errors=True)
        except Exception:
            pass
