# DashClip V4 — Dockerfile for Render deployment
# Uses Python 3.11 slim + FFmpeg installed from apt
FROM python:3.11-slim

# Install FFmpeg and system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    ffprobe \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for layer caching
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install edge-tts separately (not in requirements for compatibility)
RUN pip install --no-cache-dir edge-tts

# Copy backend source
COPY backend/ .

# Copy frontend
COPY frontend/ ./frontend/

# Copy db schema
COPY db/ ./db/

# Create directories that may be needed locally
RUN mkdir -p /tmp/dashclip/outputs \
             /tmp/dashclip/uploads/voices \
             /tmp/dashclip/uploads/music \
             /tmp/dashclip/uploads/images \
             /tmp/dashclip/uploads/custom_clips \
             /tmp/dashclip/uploads/generated_clips \
             /tmp/dashclip/tmp

# Expose port (Render sets $PORT)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start command — reads $PORT from environment
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
