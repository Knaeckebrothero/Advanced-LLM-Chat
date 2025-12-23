# Backend Dockerfile for FastAPI + PostgreSQL + Neo4j application
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# - gcc: for native Python extensions
# - libpq-dev: for psycopg2 PostgreSQL driver
# - ffmpeg: for openai-whisper audio transcription
# - poppler-utils: for pdf2image PDF processing
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    ffmpeg \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend module and entry point
COPY backend/ ./backend/
COPY start_backend.py .

# Create directories for certificates and file storage
RUN mkdir -p /app/devcerts /app/.filesystem

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8443
ENV USE_DEV_CERTS=True

# Volume for persistent file storage
VOLUME ["/app/.filesystem"]

# Expose the backend port
EXPOSE 8443

# Run the application
CMD ["python", "start_backend.py", "--host", "0.0.0.0"]
