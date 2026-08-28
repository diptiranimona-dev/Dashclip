CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) DEFAULT 'Untitled Project',
    script TEXT NOT NULL DEFAULT '',
    status VARCHAR(50) DEFAULT 'draft',
    output_video_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scenes (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    scene_number INTEGER NOT NULL,
    description TEXT NOT NULL,
    keywords TEXT[] NOT NULL DEFAULT '{}',
    duration_hint FLOAT DEFAULT 6.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clips (
    id SERIAL PRIMARY KEY,
    scene_id INTEGER REFERENCES scenes(id) ON DELETE CASCADE,
    video_url TEXT NOT NULL,
    preview_url TEXT,
    thumbnail_url TEXT,
    duration FLOAT,
    width INTEGER,
    height INTEGER,
    relevance_score FLOAT DEFAULT 0.0,
    selected BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS voiceovers (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    file_path TEXT,
    text_content TEXT,
    duration FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS music_tracks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    title VARCHAR(255),
    source VARCHAR(100),
    url TEXT,
    file_path TEXT,
    copyright_safe BOOLEAN DEFAULT TRUE,
    selected BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS subtitles (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    srt_content TEXT,
    preset VARCHAR(50) DEFAULT 'minimal',
    burned_in BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS render_jobs (
    id SERIAL PRIMARY KEY,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,
    job_id VARCHAR(100) UNIQUE NOT NULL,
    status VARCHAR(50) DEFAULT 'queued',
    progress INTEGER DEFAULT 0,
    output_path TEXT,
    error_message TEXT,
    clip_ids INTEGER[],
    voiceover_id INTEGER,
    music_id INTEGER,
    subtitle_id INTEGER,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scenes_project_id ON scenes(project_id);
CREATE INDEX IF NOT EXISTS idx_clips_scene_id ON clips(scene_id);
CREATE INDEX IF NOT EXISTS idx_clips_selected ON clips(selected);
CREATE INDEX IF NOT EXISTS idx_render_job_id ON render_jobs(job_id);