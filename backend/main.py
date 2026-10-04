"""
main.py — DashClip V4
All routes. V4 Creator Intelligence + all V3 bug fixes.
"""
import os, sys, json, uuid, re
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "services"))

from db import get_db, execute, fetchone, fetchall
import services.ollama_service as ollama_service
import services.project_service as project_service
import services.clip_ranking_service as clip_ranking_service
import services.voice_service as voice_service
import services.music_service as music_service
import services.subtitle_service as subtitle_service
import services.render_service as render_service
import services.style_service as style_service
import services.timeline_service as timeline_service
import services.model_service as model_service
import services.director_service as director_service
import services.effect_service as effect_service
import services.ad_service as ad_service
import services.ai_provider_service as ai_provider
import services.creator_brain_service as creator_brain
import services.knowledge_service as knowledge_service
import services.brand_kit_service as brand_kit_service
import services.recommendation_service as recommendation_service
import services.template_service as template_service
import services.research_service as research_service
import services.analytics_service as analytics_service

# Paths managed by storage_service (local or Supabase)
import services.storage_service as _ss_early
OUTPUT_DIR = _ss_early.OUTPUT_DIR
UPLOAD_DIR = _ss_early.UPLOAD_DIR


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) DEFAULT 'Untitled Project',
            script TEXT DEFAULT '',
            status VARCHAR(50) DEFAULT 'draft',
            style_preset VARCHAR(50) DEFAULT 'cinematic',
            video_format VARCHAR(20) DEFAULT 'landscape',
            content_format VARCHAR(20) DEFAULT 'longform',
            video_dna JSONB DEFAULT '{}',
            story_arc JSONB DEFAULT '[]',
            voiceover_id INTEGER,
            music_id INTEGER,
            subtitle_id INTEGER,
            template_id INTEGER,
            creator_dna_version INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS scenes (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            scene_number INTEGER DEFAULT 1,
            description TEXT DEFAULT '',
            keywords TEXT[] DEFAULT '{}',
            duration_hint FLOAT DEFAULT 6.0,
            scene_title VARCHAR(255) DEFAULT '',
            camera_direction TEXT DEFAULT '',
            voiceover_text TEXT DEFAULT '',
            scene_emotion TEXT DEFAULT '',
            search_concepts JSONB DEFAULT '[]',
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS clips (
            id SERIAL PRIMARY KEY,
            scene_id INTEGER REFERENCES scenes(id) ON DELETE CASCADE,
            video_url TEXT,
            preview_url TEXT,
            thumbnail_url TEXT,
            duration FLOAT,
            width INTEGER,
            height INTEGER,
            relevance_score FLOAT DEFAULT 0,
            source VARCHAR(50) DEFAULT 'pexels',
            selected BOOLEAN DEFAULT FALSE,
            why_chosen TEXT DEFAULT '',
            keyword_score FLOAT DEFAULT 0,
            emotion_score FLOAT DEFAULT 0,
            style_score FLOAT DEFAULT 0,
            quality_score FLOAT DEFAULT 0,
            consistency_score FLOAT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS voiceovers (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            type VARCHAR(50) DEFAULT 'tts',
            file_path TEXT,
            text_content TEXT,
            duration FLOAT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS music_tracks (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            title VARCHAR(255),
            source VARCHAR(50) DEFAULT 'jamendo',
            url TEXT DEFAULT '',
            preview_url TEXT DEFAULT '',
            file_path TEXT,
            copyright_safe BOOLEAN DEFAULT TRUE,
            selected BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS subtitles (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            srt_content TEXT,
            preset VARCHAR(50) DEFAULT 'minimal',
            burned_in BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS render_jobs (
            id SERIAL PRIMARY KEY,
            job_id VARCHAR(100) UNIQUE,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            clip_ids JSONB DEFAULT '[]',
            voiceover_id INTEGER,
            music_id INTEGER,
            subtitle_id INTEGER,
            status VARCHAR(50) DEFAULT 'queued',
            progress INTEGER DEFAULT 0,
            output_path TEXT,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS timeline_tracks (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            track_type VARCHAR(50),
            track_index INTEGER DEFAULT 0,
            label VARCHAR(100),
            is_locked BOOLEAN DEFAULT FALSE,
            is_muted BOOLEAN DEFAULT FALSE,
            is_visible BOOLEAN DEFAULT TRUE,
            height INTEGER DEFAULT 56,
            color VARCHAR(20) DEFAULT '#1a2a1a',
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS timeline_items (
            id SERIAL PRIMARY KEY,
            track_id INTEGER REFERENCES timeline_tracks(id) ON DELETE CASCADE,
            project_id INTEGER,
            item_type VARCHAR(50) DEFAULT 'clip',
            scene_index INTEGER,
            clip_id INTEGER,
            source_url TEXT,
            start_time FLOAT DEFAULT 0,
            end_time FLOAT DEFAULT 5,
            duration FLOAT DEFAULT 5,
            trim_in FLOAT DEFAULT 0,
            trim_out FLOAT DEFAULT 0,
            label VARCHAR(255),
            speed FLOAT DEFAULT 1.0,
            opacity FLOAT DEFAULT 1.0,
            track_layer INTEGER DEFAULT 0,
            is_locked BOOLEAN DEFAULT FALSE,
            is_muted BOOLEAN DEFAULT FALSE,
            color_grade JSONB DEFAULT '{}',
            transform JSONB DEFAULT '{}',
            transition_in JSONB DEFAULT '{}',
            transition_out JSONB DEFAULT '{}',
            extra_data JSONB DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS model_settings (
            id SERIAL PRIMARY KEY,
            setting_key VARCHAR(100) UNIQUE,
            setting_value TEXT,
            updated_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS project_assets (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            asset_type VARCHAR(30) DEFAULT 'image',
            file_path TEXT,
            original_name VARCHAR(255),
            duration FLOAT,
            width INTEGER,
            height INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS project_analytics (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
            render_attempts INTEGER DEFAULT 0,
            render_success BOOLEAN DEFAULT FALSE,
            clip_replaced_by_user BOOLEAN DEFAULT FALSE,
            music_changed BOOLEAN DEFAULT FALSE,
            subtitle_edited BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    safe_alters = [
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS content_format VARCHAR(20) DEFAULT 'longform'",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS voiceover_id INTEGER",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS music_id INTEGER",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS subtitle_id INTEGER",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS template_id INTEGER",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS creator_dna_version INTEGER DEFAULT 0",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS video_dna JSONB DEFAULT '{}'",
        "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS scene_title VARCHAR(255) DEFAULT ''",
        "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS camera_direction TEXT DEFAULT ''",
        "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS voiceover_text TEXT DEFAULT ''",
        "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS scene_emotion TEXT DEFAULT ''",
        "ALTER TABLE scenes ADD COLUMN IF NOT EXISTS search_concepts JSONB DEFAULT '[]'",
        "ALTER TABLE clips ADD COLUMN IF NOT EXISTS why_chosen TEXT DEFAULT ''",
        "ALTER TABLE clips ADD COLUMN IF NOT EXISTS keyword_score FLOAT DEFAULT 0",
        "ALTER TABLE clips ADD COLUMN IF NOT EXISTS emotion_score FLOAT DEFAULT 0",
        "ALTER TABLE clips ADD COLUMN IF NOT EXISTS style_score FLOAT DEFAULT 0",
        "ALTER TABLE clips ADD COLUMN IF NOT EXISTS quality_score FLOAT DEFAULT 0",
        "ALTER TABLE clips ADD COLUMN IF NOT EXISTS consistency_score FLOAT DEFAULT 0",
        "ALTER TABLE music_tracks ADD COLUMN IF NOT EXISTS preview_url TEXT DEFAULT ''",
        "ALTER TABLE render_jobs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()",
        "ALTER TABLE timeline_items ADD COLUMN IF NOT EXISTS speed FLOAT DEFAULT 1.0",
        "ALTER TABLE timeline_items ADD COLUMN IF NOT EXISTS opacity FLOAT DEFAULT 1.0",
        "ALTER TABLE timeline_items ADD COLUMN IF NOT EXISTS color_grade JSONB DEFAULT '{}'",
        "ALTER TABLE timeline_items ADD COLUMN IF NOT EXISTS transition_in JSONB DEFAULT '{}'",
        "ALTER TABLE timeline_items ADD COLUMN IF NOT EXISTS transition_out JSONB DEFAULT '{}'",
        "ALTER TABLE timeline_tracks ADD COLUMN IF NOT EXISTS is_locked BOOLEAN DEFAULT FALSE",
        "ALTER TABLE timeline_tracks ADD COLUMN IF NOT EXISTS is_muted BOOLEAN DEFAULT FALSE",
        "ALTER TABLE timeline_tracks ADD COLUMN IF NOT EXISTS is_visible BOOLEAN DEFAULT TRUE",
        # Fix clip_ids column type — the root cause of all render 500s
        "DO $$ BEGIN IF (SELECT data_type FROM information_schema.columns WHERE table_name='render_jobs' AND column_name='clip_ids') = 'ARRAY' THEN ALTER TABLE render_jobs DROP COLUMN clip_ids; ALTER TABLE render_jobs ADD COLUMN clip_ids JSONB DEFAULT '[]'; END IF; EXCEPTION WHEN OTHERS THEN NULL; END $$",
        # Fix old un-normalized clip scores
        "UPDATE clips SET relevance_score = LEAST(relevance_score / 7.0, 1.0) WHERE relevance_score > 1.0",
        "UPDATE clips SET keyword_score=0.5,emotion_score=0.6,style_score=0.7,quality_score=0.6,consistency_score=0.7 WHERE keyword_score=0 AND relevance_score>0",
    ]
    for stmt in safe_alters:
        try: cur.execute(stmt)
        except Exception as e: print(f"[init_db] skip: {e}")
    conn.commit(); conn.close()

    # V4 tables
    try: creator_brain.ensure_tables()
    except Exception as e: print(f"[init_db] creator_brain: {e}")
    try: knowledge_service.ensure_tables()
    except Exception as e: print(f"[init_db] knowledge: {e}")
    try: brand_kit_service.ensure_tables()
    except Exception as e: print(f"[init_db] brand_kit: {e}")
    try: recommendation_service.ensure_tables()
    except Exception as e: print(f"[init_db] recommendations: {e}")
    try: template_service.ensure_tables()
    except Exception as e: print(f"[init_db] templates: {e}")
    try: analytics_service.ensure_tables()
    except Exception as e: print(f"[init_db] analytics: {e}")
    try: template_service.seed_builtin_templates()
    except Exception as e: print(f"[init_db] seed templates: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print(f"[DashClip V4] AI Provider: {ai_provider.get_provider()}")
    yield

app = FastAPI(title="DashClip V4", lifespan=lifespan)
# Production: set ALLOWED_ORIGINS=https://your-app.onrender.com in env
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
_allowed_origins = [o.strip() for o in _raw_origins.split(",")] if _raw_origins != "*" else ["*"]
app.add_middleware(CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"])
# Only mount local static dirs — in production files are on Supabase Storage
import services.storage_service as storage_service
_out_dir = storage_service.OUTPUT_DIR
_up_dir  = storage_service.UPLOAD_DIR
_out_dir.mkdir(parents=True, exist_ok=True)
_up_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(_out_dir)), name="outputs")
app.mount("/uploads", StaticFiles(directory=str(_up_dir)),  name="uploads")
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── REQUEST MODELS ────────────────────────────────────────────────────────────

class GenerateScriptReq(BaseModel):
    prompt: str
    video_style: str = "cinematic"
    content_type: str = "storytelling"
    content_format: str = "longform"
    scene_count: int = 0
    voiceover_hint: str = ""
    camera_hint: str = ""
    use_knowledge: bool = True

class GenerateScenesReq(BaseModel):
    script: str
    project_id: int | None = None
    target_count: int = 0
    style: str = "cinematic"
    content_type: str = "storytelling"
    content_format: str = "longform"
    topic: str = ""

class SaveProjectReq(BaseModel):
    title: str | None = None
    script: str | None = None
    style_preset: str | None = None
    video_format: str | None = None
    voiceover_id: int | None = None
    music_id: int | None = None
    subtitle_id: int | None = None
    content_format: str | None = None

class SelectClipReq(BaseModel):
    clip_id: int
    scene_id: int

class TTSReq(BaseModel):
    project_id: int
    text: str
    voice_id: str = "en-US-GuyNeural"

class SubtitleReq(BaseModel):
    project_id: int
    narration_text: str
    total_duration: float = 30.0
    preset: str = "minimal"

class SubtitleSyncReq(BaseModel):
    project_id: int
    voiceover_id: int
    preset: str = "minimal"

class MusicSearchReq(BaseModel):
    query: str

class AutoMusicReq(BaseModel):
    project_id: int
    style: str = "cinematic"
    script: str = ""

class ManualMusicReq(BaseModel):
    project_id: int
    title: str
    url: str

class MusicAddReq(BaseModel):
    project_id: int
    title: str
    url: str = ""
    preview_url: str = ""
    duration: float = 0
    source: str = "jamendo"

class RenderReq(BaseModel):
    project_id: int
    clip_ids: list[int]
    voiceover_id: int | None = None
    music_id: int | None = None
    subtitle_id: int | None = None
    subtitle_preset: str = "minimal"
    video_format: str = "landscape"
    image_paths: list[int | str] = []

class DirectorReq(BaseModel):
    project_id: int
    script: str = ""
    video_style: str = "cinematic"
    content_type: str = "storytelling"

class SceneIntelReq(BaseModel):
    project_id: int
    scene_id: int
    video_style: str = "cinematic"
    content_type: str = "storytelling"

class TimelineItemUpdateReq(BaseModel):
    label: str | None = None
    duration: float | None = None
    trim_in: float | None = None
    trim_out: float | None = None
    speed: float | None = None
    opacity: float | None = None
    color_grade: dict | None = None
    transition_in: dict | None = None
    start_time: float | None = None

class AnalyticsReq(BaseModel):
    render_attempts: int | None = None
    render_success: bool | None = None
    clip_replaced_by_user: bool | None = None
    music_changed: bool | None = None
    subtitle_edited: bool | None = None

class ScriptSectionsReq(BaseModel):
    script: str

class ModelSettingReq(BaseModel):
    key: str
    value: str

class VideoDNAReq(BaseModel):
    idea: str
    video_style: str = "cinematic"
    content_type: str = "storytelling"
    project_id: int | None = None

# V4 Models
class MemoryReq(BaseModel):
    memory_type: str
    memory_key: str
    memory_value: dict
    confidence: float = 0.7

class KnowledgeReq(BaseModel):
    topic: str
    entry_type: str = "fact"
    title: str
    content: str
    source_url: str = ""
    tags: list = []

class BrandKitReq(BaseModel):
    kit_name: str = "My Brand"
    primary_color: str = "#f5a623"
    secondary_color: str = "#ffffff"
    background_color: str = "#000000"
    accent_color: str = "#60a5fa"
    font_primary: str = "Syne"
    font_secondary: str = "Space Mono"
    brand_voice: str = "professional"
    brand_tone: str = "authoritative"
    default_style: str = "cinematic"
    default_format: str = "landscape"
    channel_name: str = ""
    channel_tagline: str = ""
    target_audience: str = ""
    content_pillars: list = []
    preferred_music_genres: list = []

class TemplateReq(BaseModel):
    name: str
    description: str = ""
    category: str = "general"
    style: str = "cinematic"
    format: str = "landscape"
    content_format: str = "longform"
    default_scene_count: int = 10
    default_duration_hint: float = 6.0
    script_template: str = ""
    voiceover_tone: str = "professional"
    music_mood: str = "ambient"
    tags: list = []

class ResearchReq(BaseModel):
    topic: str
    style: str = "documentary"
    content_type: str = "educational"
    scene_count: int = 10

class RecommendationActionReq(BaseModel):
    action: str  # "dismiss" or "apply"


# ── PROJECTS ──────────────────────────────────────────────────────────────────

@app.get("/projects")
async def list_projects():
    return project_service.list_projects()

@app.get("/projects/{project_id}")
async def get_project(project_id: int):
    p = project_service.get_project(project_id)
    if not p: raise HTTPException(404, "Project not found")
    return p

@app.post("/projects/create")
async def create_project(title: str = "Untitled Project", user_id: str = "default"):
    p = project_service.create_project(title)
    # Apply brand kit defaults
    try: brand_kit_service.apply_brand_to_project(user_id, p["id"])
    except Exception: pass
    return p

@app.post("/projects/{project_id}/save")
async def save_project(project_id: int, req: SaveProjectReq):
    return project_service.save_project(
        project_id, req.title, req.script, req.style_preset,
        req.video_format, req.voiceover_id, req.music_id,
        req.subtitle_id, req.content_format)

@app.post("/projects/{project_id}/duplicate")
async def duplicate_project(project_id: int):
    return project_service.duplicate_project(project_id)

@app.delete("/projects/{project_id}")
async def delete_project(project_id: int):
    project_service.delete_project(project_id)
    return {"status": "deleted"}

@app.post("/projects/{project_id}/analytics")
async def update_analytics(project_id: int, req: AnalyticsReq):
    conn = get_db()
    try:
        execute(conn, "INSERT INTO project_analytics (project_id) VALUES (%s) ON CONFLICT DO NOTHING", (project_id,))
        updates, params = [], []
        if req.render_attempts: updates.append("render_attempts=render_attempts+%s"); params.append(req.render_attempts)
        if req.render_success is not None: updates.append("render_success=%s"); params.append(req.render_success)
        if req.clip_replaced_by_user is not None: updates.append("clip_replaced_by_user=%s"); params.append(req.clip_replaced_by_user)
        if req.music_changed is not None: updates.append("music_changed=%s"); params.append(req.music_changed)
        if updates:
            params.append(project_id)
            execute(conn, f"UPDATE project_analytics SET {','.join(updates)} WHERE project_id=%s", tuple(params))
        conn.commit()
    finally: conn.close()
    return {"status": "ok"}

@app.post("/projects/{project_id}/score")
async def score_project(project_id: int, user_id: str = "default"):
    return await analytics_service.score_project(project_id, user_id)

@app.post("/projects/{project_id}/learn")
async def learn_from_project(project_id: int, user_id: str = "default", bg: BackgroundTasks = None):
    if bg:
        bg.add_task(creator_brain.learn_from_project, project_id, user_id)
        return {"status": "learning_scheduled"}
    await creator_brain.learn_from_project(project_id, user_id)
    return {"status": "learned"}

@app.post("/projects/{project_id}/apply-template/{template_id}")
async def apply_template(project_id: int, template_id: int):
    ok = template_service.apply_template_to_project(template_id, project_id)
    if not ok: raise HTTPException(404, "Template not found")
    return {"status": "applied"}

@app.post("/projects/{project_id}/save-as-template")
async def save_as_template(project_id: int, body: dict, user_id: str = "default"):
    return template_service.save_project_as_template(
        project_id, user_id, body.get("name","My Template"), body.get("description",""))


# ── AUTO DNA ─────────────────────────────────────────────────────────────────

@app.post("/director/auto-from-idea")
async def auto_from_idea(req: VideoDNAReq):
    try:
        result = await ollama_service.generate_video_dna_from_idea(req.idea, req.video_style, req.content_type)
        if req.project_id:
            conn = get_db()
            dna = result.get("video_dna", {})
            execute(conn, "UPDATE projects SET video_dna=%s,updated_at=NOW() WHERE id=%s",
                    (json.dumps(dna), req.project_id))
            conn.commit(); conn.close()
        return result
    except Exception as e: raise HTTPException(500, str(e))


# ── SCRIPT ────────────────────────────────────────────────────────────────────

@app.post("/generate-script")
async def generate_script(req: GenerateScriptReq, user_id: str = "default"):
    talking_points = []
    if req.use_knowledge:
        try: talking_points = await knowledge_service.get_talking_points_for_script(user_id, req.prompt, req.video_style)
        except Exception: pass
    text = await ollama_service.generate_script(
        req.prompt, req.video_style, req.content_type, req.content_format,
        req.scene_count, req.voiceover_hint, req.camera_hint, talking_points)
    return {"script": text}

@app.post("/script/sections")
async def script_sections(req: ScriptSectionsReq):
    return await ollama_service.generate_script_sections(req.script)


# ── SCENES ────────────────────────────────────────────────────────────────────

@app.post("/generate-scenes")
async def generate_scenes(req: GenerateScenesReq):
    target_count = req.target_count
    if target_count <= 0:
        tags = len(re.findall(r'\[SCENE', req.script, re.I))
        if tags >= 3: target_count = tags

    scenes_data = await ollama_service.generate_scenes(
        req.script, target_count=target_count, video_style=req.style,
        content_type=req.content_type, content_format=req.content_format, topic=req.topic)

    try: scenes_data = style_service.apply_style_to_scenes(scenes_data, req.style)
    except Exception: pass

    if req.content_format == "shortform":
        for s in scenes_data: s["duration_hint"] = min(s.get("duration_hint", 6.0), 2.5)
    else:
        for s in scenes_data:
            if s.get("duration_hint",0) < 3: s["duration_hint"] = 6.0

    conn = get_db()
    project_id = req.project_id
    if project_id:
        execute(conn, "UPDATE projects SET script=%s,content_format=%s,updated_at=NOW() WHERE id=%s",
                (req.script, req.content_format, project_id))
    else:
        row = execute(conn, "INSERT INTO projects (title,script,content_format) VALUES ('Untitled',%s,%s) RETURNING id",
                      (req.script, req.content_format))
        project_id = row["id"]

    execute(conn, "DELETE FROM scenes WHERE project_id=%s", (project_id,))
    saved = []
    for i, s in enumerate(scenes_data):
        kw = s.get("keywords", [])
        kw_list = [str(k) for k in kw if k] if isinstance(kw, list) else []
        row = execute(conn,
            """INSERT INTO scenes (project_id,scene_number,description,keywords,duration_hint,
               scene_title,camera_direction,voiceover_text,scene_emotion,search_concepts)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (project_id, i+1, s.get("description",""), kw_list,
             s.get("duration_hint",6.0), s.get("scene_title",""),
             s.get("camera_direction",""), s.get("voiceover_text",""),
             s.get("emotion","neutral"), json.dumps(kw_list)))
        s["id"] = row["id"]; s["scene"] = i + 1
        saved.append(s)
    conn.commit(); conn.close()
    return {"project_id": project_id, "scenes": saved}


# ── CLIPS ─────────────────────────────────────────────────────────────────────

@app.get("/fetch-clips")
async def fetch_clips(scene_id: int, per_page: int = 8, use_director: bool = False, query: str = ""):
    conn = get_db()
    scene = fetchone(conn, "SELECT * FROM scenes WHERE id=%s", (scene_id,))
    proj = fetchone(conn, "SELECT video_format,content_format,style_preset FROM projects WHERE id=%s",
                    (scene["project_id"],)) if scene else None
    conn.close()
    if not scene: raise HTTPException(404, "Scene not found")
    kw = list(scene.get("keywords") or [])
    sc = []
    try:
        raw_sc = scene.get("search_concepts")
        if raw_sc: sc = json.loads(raw_sc) if isinstance(raw_sc, str) else list(raw_sc)
    except Exception: pass
    if query.strip(): kw = [query.strip()] + kw
    if not kw and not sc: kw = [scene.get("description","nature")[:50]]
    prefer_vert = (proj or {}).get("video_format") == "portrait"
    clips = await clip_ranking_service.fetch_and_rank_clips(
        scene_id=scene_id, keywords=kw, per_keyword=3,
        prefer_vertical=prefer_vert, search_concepts=sc if use_director else kw)
    return {"clips": clips, "scene_id": scene_id}

@app.post("/select-clip")
async def select_clip(req: SelectClipReq, user_id: str = "default"):
    conn = get_db()
    # Track rejected clips
    old_selected = fetchone(conn, "SELECT * FROM clips WHERE scene_id=%s AND selected=TRUE", (req.scene_id,))
    if old_selected and old_selected["id"] != req.clip_id:
        creator_brain.track_clip_rejected(user_id, 0, dict(old_selected))
    execute(conn, "UPDATE clips SET selected=FALSE WHERE scene_id=%s", (req.scene_id,))
    execute(conn, "UPDATE clips SET selected=TRUE WHERE id=%s", (req.clip_id,))
    # Track accepted clip
    new_clip = fetchone(conn, "SELECT * FROM clips WHERE id=%s", (req.clip_id,))
    if new_clip: creator_brain.track_clip_accepted(user_id, 0, dict(new_clip))
    conn.commit(); conn.close()
    return {"status": "ok"}

@app.get("/director/clip-explanation/{clip_id}")
async def clip_explanation(clip_id: int):
    conn = get_db()
    clip = fetchone(conn, "SELECT * FROM clips WHERE id=%s", (clip_id,))
    conn.close()
    if not clip: raise HTTPException(404, "Clip not found")
    def _pct(v):
        val = float(v or 0)
        if val > 1.0: val = val / 7.0
        return f"{min(val * 100, 99):.0f}%"
    why = clip.get("why_chosen") or f"Source: {clip.get('source','?')} · {clip.get('width',0)}x{clip.get('height',0)} · {clip.get('duration',0):.1f}s"
    scores = {
        "emotion_match":    _pct(clip.get("emotion_score")),
        "visual_relevance": _pct(clip.get("keyword_score")),
        "style_match":      _pct(clip.get("style_score")),
        "quality":          _pct(clip.get("quality_score")),
        "consistency":      _pct(clip.get("consistency_score")),
        "total":            _pct(clip.get("relevance_score")),
    }
    all_zero = all(v == "0%" for k,v in scores.items() if k != "total")
    return {
        "clip_id": clip_id, "why_chosen": why,
        "scores": scores if not all_zero else {},
        "all_zero": all_zero,
        "metadata": {"source": clip.get("source"), "duration": clip.get("duration"),
                     "resolution": f"{clip.get('width',0)}x{clip.get('height',0)}"}
    }


# ── DIRECTOR ──────────────────────────────────────────────────────────────────

@app.post("/director/video-dna")
async def gen_video_dna(req: DirectorReq):
    try:
        result = await director_service.generate_video_dna(req.project_id, req.script, req.video_style, req.content_type)
        return result
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/director/scene-intelligence")
async def scene_intelligence(req: SceneIntelReq):
    try: return await director_service.analyse_scene(req.project_id, req.scene_id, req.video_style, req.content_type)
    except Exception as e: return {"scene_id": req.scene_id, "search_concepts": [], "emotion": "neutral"}

@app.post("/director/music-brief")
async def music_brief(req: DirectorReq):
    try: return await director_service.generate_music_brief(req.project_id, req.script, req.video_style, req.content_type)
    except Exception as e: raise HTTPException(500, str(e))

@app.post("/director/voiceover-brief")
async def voiceover_brief(req: DirectorReq):
    try: return await director_service.generate_voiceover_brief(req.project_id, req.script, req.video_style, req.content_type)
    except Exception as e: raise HTTPException(500, str(e))


# ── VOICE ─────────────────────────────────────────────────────────────────────

@app.get("/voice/options")
async def voice_options():
    return await voice_service.get_voice_options()

@app.post("/voice/tts")
async def generate_tts(req: TTSReq):
    return await voice_service.generate_tts(req.project_id, req.text, req.voice_id)

@app.post("/voice/upload")
async def upload_voice(project_id: int = Form(...), file: UploadFile = File(...)):
    data = await file.read()
    return await voice_service.save_uploaded_voice(project_id, data, file.filename)

@app.post("/voice/auto")
async def auto_voice(req: DirectorReq):
    return await voice_service.auto_generate_voiceover(req.project_id, req.script, req.video_style)


# ── MUSIC ─────────────────────────────────────────────────────────────────────

@app.post("/music/search")
async def search_music(req: MusicSearchReq):
    return await music_service.search_music(req.query)

@app.post("/music/auto")
async def auto_music(req: AutoMusicReq):
    return await music_service.auto_match_music(req.project_id, req.style, req.script)

@app.post("/music/add")
async def add_music(req: MusicAddReq):
    return await music_service.add_music_from_search(
        req.project_id, req.title, req.url, req.preview_url, req.duration, req.source)

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

@app.post("/music/select/{track_id}")
async def select_music(track_id: int, project_id: int):
    music_service.select_music_track(track_id, project_id)
    return {"status": "ok"}


# ── IMAGES ────────────────────────────────────────────────────────────────────

@app.post("/clips/upload-custom")
async def upload_custom_clip(project_id: int = Form(...), file: UploadFile = File(...)):
    """Upload user's own video file as a clip for any scene."""
    import uuid
    from pathlib import Path
    clips_dir = UPLOAD_DIR / "custom_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename).suffix or ".mp4"
    safe = f"{project_id}_{uuid.uuid4().hex[:10]}{ext}"
    dest = clips_dir / safe
    data = await file.read()
    dest.write_bytes(data)

    video_url = f"/uploads/custom_clips/{safe}"
    duration = 0.0
    width = 1280
    height = 720

    # Try to get duration/dimensions with ffprobe
    try:
        import subprocess, json as _json
        probe = subprocess.run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", str(dest)
        ], capture_output=True, text=True, timeout=10)
        if probe.returncode == 0:
            streams = _json.loads(probe.stdout).get("streams", [])
            for s in streams:
                if s.get("codec_type") == "video":
                    duration = float(s.get("duration", 0) or 0)
                    width = int(s.get("width", 1280) or 1280)
                    height = int(s.get("height", 720) or 720)
                    break
    except Exception as e:
        print(f"[upload_clip] ffprobe error: {e}")

    # Get first scene of project to attach clip to
    conn = get_db()
    first_scene = fetchone(conn,
        "SELECT id FROM scenes WHERE project_id=%s ORDER BY scene_number LIMIT 1",
        (project_id,))
    scene_id = first_scene["id"] if first_scene else None

    clip_id = None
    if scene_id:
        row = execute(conn, """
            INSERT INTO clips (scene_id, video_url, preview_url, thumbnail_url,
                duration, width, height, relevance_score, source, why_chosen,
                keyword_score, emotion_score, style_score, quality_score, consistency_score)
            VALUES (%s,%s,%s,%s,%s,%s,%s,0.95,'upload','User uploaded clip',
                0.9,0.8,0.8,0.9,0.9) RETURNING id
        """, (scene_id, video_url, video_url, "", duration, width, height))
        clip_id = row["id"] if row else None
    conn.commit(); conn.close()

    return {
        "id": clip_id,
        "video_url": f"http://127.0.0.1:8000{video_url}",
        "thumbnail_url": "",
        "duration": duration,
        "width": width,
        "height": height,
        "source": "upload",
        "file_path": str(dest),
    }

@app.post("/images/upload")
async def upload_image(project_id: int = Form(...), file: UploadFile = File(...)):
    import services.storage_service as _ss
    ext = Path(file.filename).suffix or ".jpg"
    safe = f"{project_id}_{uuid.uuid4().hex[:10]}{ext}"
    dest = _ss.get_upload_path("images", safe)
    data = await file.read()
    dest.write_bytes(data)
    public = _ss.upload_file(dest, f"images/{safe}")
    conn = get_db()
    row = execute(conn,
        "INSERT INTO project_assets (project_id,asset_type,file_path,original_name) VALUES (%s,'image',%s,%s) RETURNING id",
        (project_id, str(dest), file.filename))
    conn.commit(); conn.close()
    return {"id": row["id"], "url": public, "file_path": str(dest), "original_name": file.filename}

@app.get("/projects/{project_id}/images")
async def get_images(project_id: int):
    conn = get_db()
    rows = fetchall(conn, "SELECT * FROM project_assets WHERE project_id=%s AND asset_type='image' ORDER BY created_at DESC", (project_id,))
    conn.close()
    return {"images": rows}

@app.delete("/images/{image_id}")
async def delete_image(image_id: int):
    conn = get_db()
    execute(conn, "DELETE FROM project_assets WHERE id=%s", (image_id,))
    conn.commit(); conn.close()
    return {"status": "deleted"}


# ── SUBTITLES ─────────────────────────────────────────────────────────────────

@app.post("/subtitles/generate")
async def generate_subtitles(req: SubtitleReq):
    srt = subtitle_service.generate_srt_from_text(req.narration_text, req.total_duration)
    conn = get_db()
    row = execute(conn, "INSERT INTO subtitles (project_id,srt_content,preset) VALUES (%s,%s,%s) RETURNING id",
                  (req.project_id, srt, req.preset))
    conn.commit(); conn.close()
    return {"id": row["id"], "srt_content": srt, "preset": req.preset}

@app.post("/subtitles/sync")
async def sync_subtitles(req: SubtitleSyncReq):
    conn = get_db()
    vo = fetchone(conn, "SELECT * FROM voiceovers WHERE id=%s", (req.voiceover_id,))
    conn.close()
    if not vo: raise HTTPException(404, "Voiceover not found")
    srt = subtitle_service.generate_srt_from_text(vo.get("text_content",""), float(vo.get("duration") or 30.0))
    conn = get_db()
    row = execute(conn, "INSERT INTO subtitles (project_id,srt_content,preset) VALUES (%s,%s,%s) RETURNING id",
                  (req.project_id, srt, req.preset))
    conn.commit(); conn.close()
    return {"id": row["id"], "srt_content": srt, "preset": req.preset}


# ── RENDER ────────────────────────────────────────────────────────────────────

@app.post("/render-video")
async def render_video(req: RenderReq, bg: BackgroundTasks, user_id: str = "default"):
    conn = get_db()
    clip_urls = []
    for cid in req.clip_ids:
        c = fetchone(conn, "SELECT video_url FROM clips WHERE id=%s", (cid,))
        if c and c.get("video_url"): clip_urls.append(c["video_url"])

    proj = fetchone(conn, "SELECT video_format FROM projects WHERE id=%s", (req.project_id,))
    video_format = req.video_format or (proj.get("video_format") if proj else "landscape")
    execute(conn, "UPDATE projects SET video_format=%s,updated_at=NOW() WHERE id=%s", (video_format, req.project_id))

    voiceover_path = music_path = srt_content = None
    if req.voiceover_id:
        vo = fetchone(conn, "SELECT file_path FROM voiceovers WHERE id=%s", (req.voiceover_id,))
        if vo: voiceover_path = vo.get("file_path")
    if req.music_id:
        mt = fetchone(conn, "SELECT file_path, url, preview_url FROM music_tracks WHERE id=%s", (req.music_id,))
        if mt:
            fp = (mt.get("file_path") or "").strip()
            url = (mt.get("url") or "").strip()
            preview = (mt.get("preview_url") or "").strip()
            # Priority: local file → url → preview_url
            if fp and Path(fp).exists():
                music_path = fp
                print(f"[render] music using local file: {fp}")
            elif url and (url.startswith("http://") or url.startswith("https://")):
                music_path = url
                print(f"[render] music using URL: {url[:60]}")
            elif preview and (preview.startswith("http://") or preview.startswith("https://")):
                music_path = preview
                print(f"[render] music using preview URL: {preview[:60]}")
            else:
                music_path = None
                print(f"[render] WARNING: music_id={req.music_id} has no usable path")
    if req.subtitle_id:
        sub = fetchone(conn, "SELECT srt_content FROM subtitles WHERE id=%s", (req.subtitle_id,))
        if sub:
            srt_content = sub.get("srt_content")
            # If SRT is empty or very short, regenerate from voiceover
            if (not srt_content or len(srt_content) < 50) and req.voiceover_id:
                vo_for_sub = fetchone(conn, "SELECT text_content, duration FROM voiceovers WHERE id=%s", (req.voiceover_id,))
                if vo_for_sub and vo_for_sub.get("text_content"):
                    from services import subtitle_service
                    srt_content = subtitle_service.generate_srt_from_text(
                        vo_for_sub["text_content"],
                        float(vo_for_sub.get("duration") or 30.0)
                    )

    resolved_images = []
    if req.image_paths:
        try:
            int_ids = []
            str_paths = []
            for x in req.image_paths:
                try:
                    int_ids.append(int(x))
                except (ValueError, TypeError):
                    if isinstance(x, str) and x: str_paths.append(x)
            if int_ids:
                ph = ",".join(["%s"]*len(int_ids))
                rows = fetchall(conn, f"SELECT file_path FROM project_assets WHERE id IN ({ph}) AND asset_type='image'", int_ids)
                resolved_images = [r["file_path"] for r in rows if r.get("file_path")]
            resolved_images += [p for p in str_paths if Path(p).exists()]
        except Exception as e:
            print(f"[render] image resolve error: {e}")

    conn.commit(); conn.close()
    if not clip_urls: raise HTTPException(400, "No clips selected")

    # json.dumps here AND in create_job — belt and suspenders
    job_id = render_service.create_job(req.project_id, json.dumps(req.clip_ids),
                                        req.voiceover_id, req.music_id, req.subtitle_id)
    bg.add_task(render_service.run_render,
        job_id, req.project_id, clip_urls, voiceover_path, music_path,
        srt_content, req.subtitle_preset, video_format, resolved_images)

    # Schedule learning after render
    bg.add_task(_post_render_learn, req.project_id, user_id)
    return {"job_id": job_id, "status": "queued"}

async def _post_render_learn(project_id: int, user_id: str):
    try: await creator_brain.learn_from_project(project_id, user_id)
    except Exception as e: print(f"[brain] post-render learn: {e}")

@app.get("/render-status/{job_id}")
async def render_status(job_id: str):
    return await render_service.get_render_status(job_id)


# ── TIMELINE ─────────────────────────────────────────────────────────────────

@app.get("/projects/{project_id}/timeline")
async def get_timeline(project_id: int):
    return timeline_service.get_timeline(project_id)

@app.post("/projects/{project_id}/timeline/build")
async def build_timeline(project_id: int, body: dict):
    return timeline_service.build_timeline(project_id, body.get("scenes",[]), body.get("clips",[]))

@app.post("/projects/{project_id}/timeline/reorder")
async def reorder_timeline(project_id: int, body: dict):
    timeline_service.reorder_timeline_items(project_id, body.get("ordered_ids",[]))
    return {"status": "ok"}

@app.patch("/timeline/items/{item_id}")
async def update_timeline_item(item_id: int, req: TimelineItemUpdateReq):
    updates = {}
    if req.label is not None: updates["label"] = req.label
    if req.duration is not None: updates["duration"] = req.duration
    if req.trim_in is not None: updates["trim_in"] = req.trim_in
    if req.trim_out is not None: updates["trim_out"] = req.trim_out
    if req.speed is not None: updates["speed"] = req.speed
    if req.opacity is not None: updates["opacity"] = req.opacity
    if req.start_time is not None: updates["start_time"] = req.start_time
    if req.transition_in is not None: updates["transition_in"] = req.transition_in
    if req.color_grade is not None:
        cg = req.color_grade
        updates["color_grade"] = effect_service.apply_color_preset(cg["preset"]) if isinstance(cg, dict) and cg.get("preset") else cg
    timeline_service.update_timeline_item(item_id, updates)
    return {"status": "ok"}

@app.delete("/timeline/items/{item_id}")
async def delete_timeline_item(item_id: int):
    timeline_service.delete_timeline_item(item_id)
    return {"status": "ok"}

@app.post("/timeline/items/{item_id}/split")
async def split_item(item_id: int, body: dict):
    try: return timeline_service.split_timeline_item(item_id, float(body.get("split_offset",0)))
    except ValueError as e: raise HTTPException(400, str(e))

@app.post("/timeline/items/{item_id}/duplicate")
async def duplicate_item(item_id: int):
    try: return timeline_service.duplicate_timeline_item(item_id)
    except ValueError as e: raise HTTPException(404, str(e))


# ── MODELS ────────────────────────────────────────────────────────────────────

@app.get("/models/available")
async def available_models():
    return await model_service.get_available_models()

@app.get("/models/settings")
async def model_settings():
    return model_service.get_model_settings()

@app.post("/models/settings")
async def set_model_setting(req: ModelSettingReq):
    model_service.update_model_setting(req.key, req.value)
    return {"status": "ok"}


# ── V4: CREATOR BRAIN ─────────────────────────────────────────────────────────

@app.get("/v4/brain/profile")
async def get_brain_profile(user_id: str = "default"):
    return creator_brain.get_memory_summary(user_id)

@app.get("/v4/brain/dna")
async def get_creator_dna(user_id: str = "default"):
    return creator_brain.get_dna(user_id)

@app.get("/v4/brain/memories")
async def get_memories(user_id: str = "default", memory_type: str = None):
    if memory_type:
        return creator_brain.recall(user_id, memory_type)
    return creator_brain.recall_all(user_id)

@app.post("/v4/brain/remember")
async def add_memory(req: MemoryReq, user_id: str = "default"):
    creator_brain.remember(user_id, req.memory_type, req.memory_key, req.memory_value, req.confidence)
    return {"status": "remembered"}

@app.delete("/v4/brain/forget")
async def forget_memory(memory_type: str, memory_key: str, user_id: str = "default"):
    creator_brain.forget(user_id, memory_type, memory_key)
    return {"status": "forgotten"}

@app.get("/v4/brain/recommend-style")
async def recommend_style(topic: str = "", user_id: str = "default"):
    return await creator_brain.get_style_recommendation(user_id, topic)

@app.post("/v4/brain/rebuild-dna")
async def rebuild_dna(user_id: str = "default"):
    await creator_brain.rebuild_dna(user_id)
    return {"status": "dna_rebuilt", "dna": creator_brain.get_dna(user_id)}


# ── V4: KNOWLEDGE BASE ────────────────────────────────────────────────────────

@app.post("/v4/knowledge/research")
async def research_topic(req: ResearchReq, user_id: str = "default"):
    result = await knowledge_service.research_topic(req.topic, user_id)
    # Also do deep research
    deep = await research_service.research_and_outline(req.topic, req.style, req.content_type, req.scene_count)
    result["deep_research"] = deep
    return result

@app.post("/v4/knowledge/add")
async def add_knowledge(req: KnowledgeReq, user_id: str = "default"):
    return knowledge_service.add_knowledge(user_id, req.topic, req.entry_type, req.title, req.content, req.source_url, req.tags)

@app.get("/v4/knowledge/list")
async def list_knowledge(user_id: str = "default", topic: str = None):
    return knowledge_service.get_knowledge(user_id, topic)

@app.get("/v4/knowledge/topics")
async def list_topics(user_id: str = "default"):
    return knowledge_service.get_topics(user_id)

@app.delete("/v4/knowledge/{knowledge_id}")
async def delete_knowledge(knowledge_id: int, user_id: str = "default"):
    knowledge_service.delete_knowledge(knowledge_id, user_id)
    return {"status": "deleted"}

@app.post("/v4/knowledge/hooks")
async def get_hooks(body: dict, user_id: str = "default"):
    return await research_service.generate_hook_variations(body.get("topic",""), body.get("style","cinematic"), body.get("count",5))

@app.post("/v4/knowledge/b-roll")
async def get_b_roll(body: dict):
    return await research_service.suggest_b_roll(body.get("scene",""), body.get("topic",""), body.get("style","cinematic"))

@app.post("/v4/knowledge/improve-script")
async def improve_script(body: dict):
    return {"improved": await research_service.improve_script_section(
        body.get("section",""), body.get("section_type","intro"), body.get("style","cinematic"))}

@app.post("/v4/knowledge/suggest-next")
async def suggest_next(user_id: str = "default"):
    return await recommendation_service.suggest_next_video(user_id)


# ── V4: BRAND KIT ─────────────────────────────────────────────────────────────

@app.get("/v4/brand")
async def get_brand(user_id: str = "default"):
    return brand_kit_service.get_active_kit(user_id)

@app.post("/v4/brand")
async def save_brand(req: BrandKitReq, user_id: str = "default"):
    return brand_kit_service.create_or_update_kit(user_id, req.dict())

@app.get("/v4/brand/all")
async def all_brands(user_id: str = "default"):
    return brand_kit_service.get_all_kits(user_id)


# ── V4: TEMPLATES ─────────────────────────────────────────────────────────────

@app.get("/v4/templates")
async def list_templates(user_id: str = "default", category: str = None):
    return template_service.get_templates(user_id, category)

@app.post("/v4/templates")
async def create_template(req: TemplateReq, user_id: str = "default"):
    return template_service.create_template(user_id, req.dict())

@app.get("/v4/templates/{template_id}")
async def get_template(template_id: int):
    t = template_service.get_template(template_id)
    if not t: raise HTTPException(404, "Template not found")
    return t

@app.delete("/v4/templates/{template_id}")
async def delete_template(template_id: int, user_id: str = "default"):
    template_service.delete_template(template_id, user_id)
    return {"status": "deleted"}


# ── V4: ANALYTICS ─────────────────────────────────────────────────────────────

@app.get("/v4/analytics/stats")
async def creator_stats(user_id: str = "default"):
    return analytics_service.get_creator_stats(user_id)

@app.post("/v4/analytics/score/{project_id}")
async def score_project_route(project_id: int, user_id: str = "default"):
    return await analytics_service.score_project(project_id, user_id)


# ── V4: RECOMMENDATIONS ──────────────────────────────────────────────────────

@app.get("/v4/recommendations")
async def get_recommendations(user_id: str = "default", project_id: int = None):
    return recommendation_service.get_recommendations(user_id, project_id)

@app.post("/v4/recommendations/{rec_id}")
async def action_recommendation(rec_id: int, req: RecommendationActionReq, user_id: str = "default"):
    if req.action == "dismiss":
        recommendation_service.dismiss_recommendation(rec_id, user_id)
    elif req.action == "apply":
        recommendation_service.apply_recommendation(rec_id, user_id)
    return {"status": req.action}

@app.post("/v4/recommendations/generate/{project_id}")
async def generate_recommendations(project_id: int, user_id: str = "default"):
    return await recommendation_service.generate_project_recommendations(project_id, user_id)

@app.post("/v4/script/improve")
async def improve_script_section(body: dict):
    return {"improved": await recommendation_service.get_script_improvement(
        body.get("script",""), body.get("style","cinematic"), body.get("improvement_type","hook"))}


# ── V4: AI PROVIDER INFO ──────────────────────────────────────────────────────

@app.get("/v4/ai-provider")
async def ai_provider_info():
    """Returns full AI provider status for settings UI."""
    return await ai_provider.get_status()

@app.post("/v4/ai-provider/test")
async def test_ai_provider():
    """Real connection test — actually calls the provider. Never fakes success."""
    result = await ai_provider.test_connection()
    status_code = 200 if result["ok"] else 503
    from fastapi.responses import JSONResponse
    return JSONResponse(content=result, status_code=status_code)

@app.get("/v4/ai-provider/models")
async def list_ai_models():
    """List available models for current provider."""
    return await ai_provider.get_available_models()

class AIProviderConfigReq(BaseModel):
    provider: str           # "gemini" or "ollama"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"

@app.post("/v4/ai-provider/configure")
async def configure_ai_provider(req: AIProviderConfigReq):
    """
    Update AI provider config at runtime.
    Keys are stored server-side only — never returned to frontend.
    In production: update env vars in Render dashboard instead.
    """
    import services.ai_provider_service as _ai
    if req.provider == "gemini":
        if not req.gemini_api_key:
            raise HTTPException(400, "Gemini API key required")
        # Set at module level for this process
        os.environ["GEMINI_API_KEY"] = req.gemini_api_key
        os.environ["GEMINI_MODEL"] = req.gemini_model or "gemini-2.0-flash"
        os.environ["DASHCLIP_AI_PROVIDER"] = "gemini"
        # Reload module globals
        _ai.GEMINI_API_KEY = req.gemini_api_key
        _ai.GEMINI_MODEL = req.gemini_model or "gemini-2.0-flash"
        _ai._PROVIDER_ENV = "gemini"
    elif req.provider == "ollama":
        os.environ["DASHCLIP_AI_PROVIDER"] = "ollama"
        os.environ["OLLAMA_URL"] = req.ollama_url or "http://127.0.0.1:11434"
        os.environ["DASHCLIP_AI_MODEL"] = req.ollama_model or "qwen2.5:7b"
        _ai.OLLAMA_URL = req.ollama_url or "http://127.0.0.1:11434"
        _ai.MODEL_PRIMARY = req.ollama_model or "qwen2.5:7b"
        _ai._PROVIDER_ENV = "ollama"
        _ai._model_cache.clear()
    else:
        raise HTTPException(400, f"Unknown provider: {req.provider}")
    # Test the new config
    test = await _ai.test_connection()
    return {"configured": True, "test": test}


# ── SYSTEM ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Production health check — Render pings this every 30s."""
    import services.storage_service as _ss
    db_ok = False
    try:
        conn = get_db()
        fetchone(conn, "SELECT 1 as ok", ())
        conn.close()
        db_ok = True
    except Exception as e:
        print(f"[health] DB check failed: {e}")
    ai_status = {}
    try:
        ai_status = await ai_provider.get_status()
    except Exception:
        ai_status = {"provider": ai_provider.get_provider(), "ok": False}
    return {
        "status": "ok" if db_ok else "degraded",
        "version": "4.0.0",
        "db": "ok" if db_ok else "error",
        "storage": _ss.STORAGE_BACKEND,
        "ai_provider": ai_status.get("provider", "unknown"),
        "ai_ok": ai_status.get("ok", False),
        "ai_model": ai_status.get("model", "unknown"),
    }

@app.get("/ads/config")
async def ads_config():
    return {"ads_enabled": False}


# ── FRONTEND ──────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    for p in [
        Path(__file__).parent.parent / "frontend" / "index.html",
        Path(__file__).parent / "frontend" / "index.html",
        Path("frontend") / "index.html",
        Path("../frontend") / "index.html",
    ]:
        if p.exists(): return FileResponse(str(p))
    raise HTTPException(404, f"Frontend not found. Looked near {Path(__file__)}")

@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    for p in [
        Path(__file__).parent.parent / "frontend" / "index.html",
        Path(__file__).parent / "frontend" / "index.html",
        Path("frontend") / "index.html",
    ]:
        if p.exists(): return FileResponse(str(p))
    raise HTTPException(404, "Frontend not found")
