# DashClip V4 — AI Video Creation Studio

DashClip is an AI-powered video creation platform. Paste an idea, get a full video with script, stock footage, voiceover, music, subtitles and watermark — rendered locally on your machine.

---

## What It Does

- AI writes your script (Qwen via Ollama — no API key needed)
- Breaks script into scenes with unique stock footage keywords
- Fetches clips from Pexels + Pixabay
- Generates voiceover via edge-tts (12 voices)
- Finds copyright-safe music via Free Music Archive
- Burns subtitles into video
- Renders final MP4 with FFmpeg
- Creator Brain learns your style after every video

---

## Requirements

- Windows 10/11 (also works on Mac/Linux)
- Python 3.10+
- PostgreSQL 14+
- FFmpeg (in PATH)
- Ollama (running locally)
- 8GB RAM minimum (16GB recommended for qwen2.5:7b)

---

## Setup — Step by Step

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/dashclip.git
cd dashclip
```

### 2. Install Python dependencies
```bash
cd backend
pip install -r requirements.txt --break-system-packages
pip install edge-tts --break-system-packages
```

### 3. Set up PostgreSQL
```sql
CREATE DATABASE ai_script_video;
```

### 4. Configure environment
```bash
cp .env.example .env
# Edit .env with your values:
# - PEXELS_API_KEY (free at pexels.com/api)
# - PIXABAY_API_KEY (free at pixabay.com/api/docs)
# - DB_PASSWORD (your PostgreSQL password)
# - TEMP_DIR (your Windows temp path)
```

### 5. Install and start Ollama
```bash
# Download from https://ollama.com
ollama pull qwen2.5:7b
ollama pull qwen2.5:3b
ollama pull qwen2.5:1.5b
```

### 6. Install FFmpeg
Download from https://ffmpeg.org/download.html and add to PATH.

### 7. Start DashClip
```bash
cd backend
python -m uvicorn main:app --reload --port 8000
```

### 8. Open in browser
```
http://127.0.0.1:8000
```

---

## AI Model Routing

DashClip uses three Qwen tiers via Ollama:

| Tier | Model | Tasks |
|------|-------|-------|
| 1 — Smart | qwen2.5:7b | Script, scenes, director, brain |
| 2 — Medium | qwen2.5:3b | Classification, analysis, tagging |
| 3 — Fast | qwen2.5:1.5b | Keywords, cleanup, metadata |

Configure in `.env`:
```
DASHCLIP_AI_MODEL=qwen2.5:7b
DASHCLIP_AI_MEDIUM=qwen2.5:3b
DASHCLIP_AI_FAST=qwen2.5:1.5b
```

---

## API Keys Needed

| Service | Free? | Get Key |
|---------|-------|---------|
| Pexels | Yes | pexels.com/api |
| Pixabay | Yes | pixabay.com/api/docs |
| Free Music Archive | No key needed | Built-in |
| Ollama/Qwen | No key needed | Local |
| FFmpeg | Free | ffmpeg.org |

Optional (AI video generation when no stock found):
| Google Veo 2 | Paid | aistudio.google.com |
| RunwayML | Paid | runwayml.com |
| Luma AI | Paid | lumalabs.ai |

---

## Beta Status

This is a public beta. Expect bugs. Please open issues on GitHub.

Known limitations:
- No user authentication (single user mode)
- No cloud sync (all local)
- Ollama 1b model produces lower quality output than larger models

---

## License

MIT License — free to use, modify, distribute.
