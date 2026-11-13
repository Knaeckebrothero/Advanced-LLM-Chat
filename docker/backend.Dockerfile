# Backend Dockerfile for FastAPI + PostgreSQL + Neo4j application
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# - gcc: for native Python extensions
# - libpq-dev: for psycopg2 PostgreSQL driver
# - ffmpeg: for openai-whisper audio transcription
# - poppler-utils: pdftoppm renders the pages of PDFs
# - tini: the container's first process; it reaps the processes others leave behind
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    ffmpeg \
    poppler-utils \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend module, entry point and the default model catalog (MODEL_CATALOG_FILE=catalog/models.json)
COPY backend/ ./backend/
COPY catalog/ ./catalog/
COPY start_backend.py .

# The backend runs as the user "app", not as root. Its ids are fixed (the Helm chart runs the
# container with them), and it owns only its home (caches of local Whisper and of MCP stdio
# tools) and the directories for certificates and file storage; the code stays root's.
COPY docker/backend-entrypoint.sh /usr/local/bin/backend-entrypoint.sh
RUN chmod 755 /usr/local/bin/backend-entrypoint.sh \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/devcerts /app/.filesystem \
    && chown app:app /app/devcerts /app/.filesystem

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8443
ENV USE_DEV_CERTS=True
# Uploaded files, the TTS cache and logs go to the volume below
ENV FILESYSTEM_PATH=/app/.filesystem
ENV FILES_DIR=/app/.filesystem/files

# Volume for persistent file storage
VOLUME ["/app/.filesystem"]

# Expose the backend port
EXPOSE 8443

# Run the application. The container starts as root only so that the entrypoint can hand
# volumes of earlier versions (written as root) to app; it then drops root for good.
# Started as another user (docker run --user, Kubernetes runAsUser), it changes nothing.
# tini is the first process: a PDF worker that is killed for taking too long leaves its
# pdftoppm behind, and the Python server would never collect such processes
ENTRYPOINT ["tini", "--", "backend-entrypoint.sh"]
CMD ["python", "start_backend.py", "--host", "0.0.0.0"]
