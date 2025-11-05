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

# Database directory
DB_DIR = os.getenv('DB_DIR', '.')

# SSL/TLS configuration
USE_DEV_CERTS = os.getenv("USE_DEV_CERTS") == "True"

# Server configuration
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))

# Replicate API configuration
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
