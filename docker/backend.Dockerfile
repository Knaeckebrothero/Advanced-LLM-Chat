# Backend Dockerfile for FastAPI + SQLite application
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend application
COPY backend_mockup.py .

# Create directories for certificates and database
RUN mkdir -p /app/devcerts /app/data

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8443
ENV USE_DEV_CERTS=True

# Volume for persistent SQLite database
VOLUME ["/app/data"]

# Expose the backend port
EXPOSE 8443

# Run the application
CMD ["python", "backend_mockup.py"]
