"""
storage_service.py — DashClip V4
Unified storage layer.
Local dev: writes to ./uploads/ and ./outputs/ (fast, no config needed)
Production (Render): writes to Supabase Storage, returns public URLs
Controlled by STORAGE_BACKEND env var: "local" (default) or "supabase"
"""
import os
from pathlib import Path

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")
SUPABASE_URL    = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY    = os.getenv("SUPABASE_SERVICE_KEY", "")  # service role key, not anon
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "dashclip-media")

# Local paths — used in local mode, and as temp staging in production
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/dashclip/outputs"))
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/dashclip/uploads"))

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
for sub in ["voices", "music", "images", "custom_clips", "generated_clips"]:
    (UPLOAD_DIR / sub).mkdir(parents=True, exist_ok=True)

_supabase_client = None

def _get_supabase():
    global _supabase_client
    if _supabase_client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required for supabase storage")
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client

def is_production() -> bool:
    return STORAGE_BACKEND == "supabase"

def upload_file(local_path: Path, storage_key: str) -> str:
    """
    Upload file to storage. Returns public URL.
    local:    returns /outputs/filename or /uploads/subdir/filename
    supabase: uploads to bucket, returns public CDN URL
    """
    if STORAGE_BACKEND == "supabase":
        try:
            sb = _get_supabase()
            with open(local_path, "rb") as f:
                data = f.read()
            sb.storage.from_(SUPABASE_BUCKET).upload(
                storage_key, data,
                file_options={"content-type": _content_type(local_path),
                              "upsert": "true"}
            )
            public = sb.storage.from_(SUPABASE_BUCKET).get_public_url(storage_key)
            return public
        except Exception as e:
            print(f"[storage] Supabase upload failed: {e} — falling back to local URL")
            return f"/uploads/{storage_key}"
    else:
        # Local: file is already in the right place, return relative URL
        fname = local_path.name
        if "outputs" in str(local_path):
            return f"/outputs/{fname}"
        # Reconstruct relative path from uploads dir
        try:
            rel = local_path.relative_to(UPLOAD_DIR)
            return f"/uploads/{rel}"
        except ValueError:
            return f"/uploads/{fname}"

def download_file(url: str, dest: Path) -> bool:
    """
    Download file from storage URL to local path.
    Used by render_service to stage files before FFmpeg.
    """
    if not url:
        return False
    try:
        if url.startswith("http://") or url.startswith("https://"):
            import httpx
            with httpx.Client(timeout=120, follow_redirects=True) as c:
                r = c.get(url, headers={"User-Agent": "DashClip/4.0"})
                if r.status_code == 200 and len(r.content) > 100:
                    dest.write_bytes(r.content)
                    return True
            return False
        else:
            # Local path
            src = Path(url.lstrip("/"))
            if src.exists():
                import shutil
                shutil.copy2(src, dest)
                return True
            # Try relative to OUTPUT_DIR or UPLOAD_DIR
            for base in [OUTPUT_DIR, UPLOAD_DIR, Path(".")]:
                candidate = base / url.lstrip("/")
                if candidate.exists():
                    import shutil
                    shutil.copy2(candidate, dest)
                    return True
        return False
    except Exception as e:
        print(f"[storage] download failed {url}: {e}")
        return False

def get_output_path(filename: str) -> Path:
    """Return local path to write a rendered video to."""
    return OUTPUT_DIR / filename

def get_upload_path(subdir: str, filename: str) -> Path:
    """Return local path to write an upload to."""
    p = UPLOAD_DIR / subdir / filename
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def public_url(filename: str, subdir: str = "outputs") -> str:
    """Return public URL for a stored file."""
    if STORAGE_BACKEND == "supabase" and SUPABASE_URL:
        try:
            sb = _get_supabase()
            key = f"{subdir}/{filename}"
            return sb.storage.from_(SUPABASE_BUCKET).get_public_url(key)
        except Exception:
            pass
    return f"/{subdir}/{filename}"

def _content_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".mp4": "video/mp4", ".mp3": "audio/mpeg",
        ".wav": "audio/wav", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".png": "image/png",
        ".webm": "video/webm", ".srt": "text/plain",
    }.get(ext, "application/octet-stream")
