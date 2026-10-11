FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libpq-dev \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir edge-tts

COPY backend/ .
COPY frontend/ ./frontend/
COPY db/ ./db/

RUN mkdir -p /tmp/dashclip/outputs \
             /tmp/dashclip/uploads/voices \
             /tmp/dashclip/uploads/music \
             /tmp/dashclip/uploads/images \
             /tmp/dashclip/uploads/custom_clips \
             /tmp/dashclip/uploads/generated_clips \
             /tmp/dashclip/tmp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
