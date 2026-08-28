"""
main.py  —  AI Script-to-Video V2
FastAPI backend. All business logic lives in services/.
"""

import os
import sys
import json
from pathlib import Path
from contextlib import asynccontextmanager

import psycopg2
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pydantic import BaseModel

load_dotenv()

# Add backend root to path so services can import db.py
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "services"))

from db import get_db, execute, fetchone, fetchall
from services import (
    ollama_service,
    project_service,
    clip_ranking_service,
    voice_service,
    music_service,
    subtitle_service,
    render_service,
    ad_service,
)

OUTPUT_DIR  = Path(os.getenv("OUTPUT_DIR",  "./outputs"))
UPLOAD_DIR  = Path(os.getenv("UPLOAD_DIR",  "./uploads"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# DB INIT
# ─────────────────────────────────────────────
def init_db():
    schema = Path(__file__).parent.parent / "db" / "schema.sql"
    conn = get_db()
    if schema.exists():
        conn.cursor().execute(schema.read_text())
    else:
        # Inline minimal schema
        conn.cursor().execute("""
            CREATE TABLE IF NOT EXISTS projects (id SERIAL PRIMARY KEY, title VARCHAR(255) DEFAULT 'Untitled', script TEXT DEFAULT '', status VARCHAR(50) DEFAULT 'draft', output_video_path TEXT, created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW());
            CREATE TABLE IF NOT EXISTS scenes (id SERIAL PRIMARY KEY, project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE, scene_number INTEGER NOT NULL, description TEXT NOT NULL, keywords TEXT[] DEFAULT '{}', duration_hint FLOAT DEFAULT 6, created_at TIMESTAMP DEFAULT NOW());
            CREATE TABLE IF NOT EXISTS clips (id SERIAL PRIMARY KEY, scene_id INTEGER REFERENCES scenes(id) ON DELETE CASCADE, video_url TEXT NOT NULL, preview_url TEXT, thumbnail_url TEXT, duration FLOAT, width INTEGER, height INTEGER, relevance_score FLOAT DEFAULT 0, selected BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW());
            CREATE TABLE IF NOT EXISTS voiceovers (id SERIAL PRIMARY KEY, project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE, type VARCHAR(50), file_path TEXT, text_content TEXT, duration FLOAT, created_at TIMESTAMP DEFAULT NOW());
            CREATE TABLE IF NOT EXISTS music_tracks (id SERIAL PRIMARY KEY, project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE, title VARCHAR(255), source VARCHAR(100), url TEXT, file_path TEXT, copyright_safe BOOLEAN DEFAULT TRUE, selected BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW());
            CREATE TABLE IF NOT EXISTS subtitles (id SERIAL PRIMARY KEY, project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE, srt_content TEXT, preset VARCHAR(50) DEFAULT 'minimal', burned_in BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW());
            CREATE TABLE IF NOT EXISTS render_jobs (id SERIAL PRIMARY KEY, project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE, job_id VARCHAR(100) UNIQUE, status VARCHAR(50) DEFAULT 'queued', progress INTEGER DEFAULT 0, output_path TEXT, error_message TEXT, clip_ids INTEGER[], voiceover_id INTEGER, music_id INTEGER, subtitle_id INTEGER, started_at TIMESTAMP, completed_at TIMESTAMP, created_at TIMESTAMP DEFAULT NOW());
        """)
    conn.commit()
    conn.close()
    print("✅ Database initialized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────
app = FastAPI(title="AI Script-to-Video V2", version="2.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_DIR)), name="outputs")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


# ─────────────────────────────────────────────
# PYDANTIC MODELS
# ─────────────────────────────────────────────
class GenerateScriptReq(BaseModel):
    prompt: str

class GenerateScenesReq(BaseModel):
    script: str
    project_id: int | None = None

class SaveProjectReq(BaseModel):
    title: str | None = None
    script: str | None = None

class SelectClipReq(BaseModel):
    clip_id: int
    scene_id: int

class RenderReq(BaseModel):
    project_id: int
    clip_ids: list[int]
    voiceover_id: int | None = None
    music_id: int | None = None
    subtitle_id: int | None = None
    subtitle_preset: str = "minimal"

class TTSReq(BaseModel):
    project_id: int
    text: str
    voice_id: str = "en-US-AriaNeural"

class MusicSearchReq(BaseModel):
    query: str
    page: int = 1

class AddMusicReq(BaseModel):
    project_id: int
    title: str
    url: str = ""
    preview_url: str = ""
    duration: float = 0

class ManualMusicReq(BaseModel):
    project_id: int
    title: str
    url: str = ""

class SubtitleReq(BaseModel):
    project_id: int
    narration_text: str
    total_duration: float
    preset: str = "minimal"

class VoiceSearchReq(BaseModel):
    query: str

class SaveSearchedVoiceReq(BaseModel):
    project_id: int
    url: str
    title: str = ""


# ═══════════════════════════════════════════════════════════════════
# PROJECT ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.get("/projects")
async def list_projects():
    return project_service.list_projects()

@app.post("/projects/create")
async def create_project(title: str = "Untitled Project"):
    return project_service.create_project(title=title)

@app.get("/projects/{project_id}")
async def get_project(project_id: int):
    p = project_service.get_project(project_id)
    if not p:
        raise HTTPException(404, "Project not found")
    return p

@app.post("/projects/{project_id}/save")
async def save_project(project_id: int, req: SaveProjectReq):
    return project_service.save_project(project_id, req.title, req.script)

@app.delete("/projects/{project_id}")
async def delete_project(project_id: int):
    project_service.delete_project(project_id)
    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════════════
# SCRIPT + SCENE GENERATION
# ═══════════════════════════════════════════════════════════════════

@app.post("/generate-script")
async def generate_script(req: GenerateScriptReq):
    text = await ollama_service.generate_script(req.prompt)
    return {"script": text}

@app.post("/generate-scenes")
async def generate_scenes(req: GenerateScenesReq):
    scenes_data = await ollama_service.generate_scenes(req.script)

    conn = get_db()

    if req.project_id:
        project_id = req.project_id
        execute(conn, "UPDATE projects SET script=%s, updated_at=NOW() WHERE id=%s",
                (req.script, project_id))
    else:
        row = execute(conn,
            "INSERT INTO projects (script) VALUES (%s) RETURNING id", (req.script,))
        project_id = row["id"]

    execute(conn, "DELETE FROM scenes WHERE project_id=%s", (project_id,))

    saved = []
    for s in scenes_data:
        row = execute(conn,
            """INSERT INTO scenes (project_id, scene_number, description, keywords, duration_hint)
               VALUES (%s,%s,%s,%s,%s) RETURNING id""",
            (project_id, s["scene"], s["description"],
             s.get("keywords", []), s.get("duration_hint", 6.0))
        )
        saved.append({
            "id":           row["id"],
            "scene":        s["scene"],
            "description":  s["description"],
            "keywords":     s.get("keywords", []),
            "duration_hint":s.get("duration_hint", 6.0),
        })

    conn.commit()
    conn.close()
    return {"project_id": project_id, "scenes": saved}


# ═══════════════════════════════════════════════════════════════════
# CLIP ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.get("/fetch-clips")
async def fetch_clips(scene_id: int, query: str = "", per_page: int = 5,
                      prefer_vertical: bool = False):
    conn = get_db()
    scene = fetchone(conn, "SELECT keywords FROM scenes WHERE id=%s", (scene_id,))
    conn.close()

    keywords = scene["keywords"] if scene else []
    if query:
        keywords = [query] + [k for k in keywords if k != query]

    clips = await clip_ranking_service.fetch_and_rank_clips(
        scene_id=scene_id,
        keywords=keywords[:3],
        per_keyword=per_page,
        prefer_vertical=prefer_vertical
    )
    return {"clips": clips, "scene_id": scene_id}

@app.post("/select-clip")
async def select_clip(req: SelectClipReq):
    conn = get_db()
    execute(conn, "UPDATE clips SET selected=FALSE WHERE scene_id=%s", (req.scene_id,))
    r = execute(conn,
        "UPDATE clips SET selected=TRUE WHERE id=%s AND scene_id=%s RETURNING id",
        (req.clip_id, req.scene_id))
    if not r:
        conn.rollback()
        conn.close()
        raise HTTPException(404, "Clip not found for this scene")
    conn.commit()
    conn.close()
    return {"status": "ok", "clip_id": req.clip_id}


# ═══════════════════════════════════════════════════════════════════
# VOICEOVER ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.get("/voice/options")
async def voice_options():
    return voice_service.get_voice_options()

@app.post("/voice/tts")
async def generate_tts(req: TTSReq):
    return await voice_service.generate_tts(req.project_id, req.text, req.voice_id)

@app.post("/voice/upload")
async def upload_voice(project_id: int = Form(...), file: UploadFile = File(...)):
    data = await file.read()
    return await voice_service.save_uploaded_voice(project_id, data, file.filename)

@app.post("/voice/search")
async def search_voice(req: VoiceSearchReq):
    return await voice_service.search_voice_audio(req.query)

@app.post("/voice/search/save")
async def save_searched_voice(req: SaveSearchedVoiceReq):
    return await voice_service.save_searched_voice(req.project_id, req.url, req.title)


# ═══════════════════════════════════════════════════════════════════
# MUSIC ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.post("/music/search")
async def search_music(req: MusicSearchReq):
    return await music_service.search_music(req.query, req.page)

@app.post("/music/add")
async def add_music(req: AddMusicReq):
    return await music_service.add_music_from_search(
        req.project_id, req.title, req.url, req.preview_url, req.duration)

@app.post("/music/upload")
async def upload_music(project_id: int = Form(...), file: UploadFile = File(...)):
    data = await file.read()
    return await music_service.save_uploaded_music(project_id, data, file.filename)

@app.post("/music/manual")
async def manual_music(req: ManualMusicReq):
    return await music_service.add_music_manual(req.project_id, req.title, req.url)

@app.get("/music/project/{project_id}")
async def get_project_music(project_id: int):
    return music_service.get_project_music(project_id)


# ═══════════════════════════════════════════════════════════════════
# SUBTITLE ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.post("/subtitles/generate")
async def generate_subtitles(req: SubtitleReq):
    srt = subtitle_service.generate_srt_from_text(req.narration_text, req.total_duration)
    record = subtitle_service.save_subtitle_record(req.project_id, srt, req.preset)
    return {**record, "srt_preview": srt[:500]}

@app.get("/subtitles/presets")
async def subtitle_presets():
    return list(subtitle_service.SUBTITLE_PRESETS.keys())


# ═══════════════════════════════════════════════════════════════════
# RENDER ROUTES
# ═══════════════════════════════════════════════════════════════════

@app.post("/render-video")
async def render_video(req: RenderReq, bg: BackgroundTasks):
    if not req.clip_ids:
        raise HTTPException(400, "No clip IDs provided")

    # Resolve clip URLs from DB
    conn = get_db()
    placeholders = ",".join(["%s"] * len(req.clip_ids))
    rows = fetchall(conn, f"SELECT id, video_url FROM clips WHERE id IN ({placeholders})", req.clip_ids)
    conn.close()

    id_to_url = {r["id"]: r["video_url"] for r in rows}
    clip_urls = [id_to_url[cid] for cid in req.clip_ids if cid in id_to_url]
    if not clip_urls:
        raise HTTPException(404, "No valid clips found")

    # Resolve optional asset paths
    voiceover_path = None
    music_path     = None
    srt_content    = None

    conn = get_db()
    if req.voiceover_id:
        vo = fetchone(conn, "SELECT file_path FROM voiceovers WHERE id=%s", (req.voiceover_id,))
        voiceover_path = vo["file_path"] if vo else None

    if req.music_id:
        mt = fetchone(conn, "SELECT file_path FROM music_tracks WHERE id=%s", (req.music_id,))
        music_path = mt["file_path"] if mt else None

    if req.subtitle_id:
        sub = fetchone(conn, "SELECT srt_content FROM subtitles WHERE id=%s", (req.subtitle_id,))
        srt_content = sub["srt_content"] if sub else None
    conn.close()

    job_id = render_service.create_job(
        req.project_id, req.clip_ids,
        req.voiceover_id, req.music_id, req.subtitle_id
    )

    bg.add_task(
        render_service.run_render,
        job_id, req.project_id, clip_urls,
        voiceover_path, music_path, srt_content, req.subtitle_preset
    )
    return {"job_id": job_id, "status": "queued"}

@app.get("/render-status/{job_id}")
async def render_status(job_id: str):
    status = render_service.get_job_status(job_id)
    if status is None:
        # Fallback: check DB (e.g. after server restart)
        conn = get_db()
        row = fetchone(conn, "SELECT * FROM render_jobs WHERE job_id=%s", (job_id,))
        conn.close()
        if not row:
            raise HTTPException(404, "Job not found")
        return {
            "status":   row["status"],
            "progress": row["progress"] or 0,
            "output":   f"/outputs/{Path(row['output_path']).name}" if row.get("output_path") else None,
            "error":    row.get("error_message")
        }
    return status


# ═══════════════════════════════════════════════════════════════════
# MISC
# ═══════════════════════════════════════════════════════════════════

@app.get("/ads/config")
async def ad_config():
    return ad_service.get_ad_config()

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}
