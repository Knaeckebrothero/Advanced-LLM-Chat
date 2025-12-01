"""
Configuration constants and settings for the backend application.
"""
import os
from dotenv import load_dotenv, find_dotenv

# Load environment variables
load_dotenv(find_dotenv())

# Default settings for LLM generation
DEFAULT_MODEL = "openai/gpt-4o"
DEFAULT_TEMPERATURE = 0.5
DEFAULT_TOP_P = 0.5
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant!"

# CORS configuration
CORS_ORIGINS = [
    "http://localhost:4200",  # Angular default
    "http://localhost:8080",  # Common dev port
    "https://localhost:4200",
    "https://localhost:8080",
]

# PostgreSQL configuration
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'fessi_chat')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'fessi')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
POSTGRES_MIN_CONNECTIONS = int(os.getenv('POSTGRES_MIN_CONNECTIONS', '1'))
POSTGRES_MAX_CONNECTIONS = int(os.getenv('POSTGRES_MAX_CONNECTIONS', '10'))

# Database URL (can override individual settings)
DATABASE_URL = os.getenv('DATABASE_URL', None)

# SSL/TLS configuration
USE_DEV_CERTS = os.getenv("USE_DEV_CERTS") == "True"

# Server configuration
HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", "8443"))

# Filesystem configuration
FILESYSTEM_PATH = os.getenv("FILESYSTEM_PATH", ".filesystem")

# Replicate API configuration
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
