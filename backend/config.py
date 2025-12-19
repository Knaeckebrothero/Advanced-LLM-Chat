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

# Neo4j Knowledge Graph configuration
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'fessi_neo4j_dev')

# SSL/TLS configuration
USE_DEV_CERTS = os.getenv("USE_DEV_CERTS") == "True"

# Server configuration
HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", "8443"))

# Filesystem configuration
FILESYSTEM_PATH = os.getenv("FILESYSTEM_PATH", ".filesystem")

# Replicate API configuration
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# Image processing configuration for LLM
# Set to 'yes' to pass images to vision-capable models
# Set to 'no' to skip images or include a note that an image was attached
MODEL_RECEIVE_IMAGES = os.getenv("MODEL_RECEIVE_IMAGES", "yes").lower() == "yes"

# PDF page images for LLM (vision-capable models only)
# Set to 'yes' to send PDF page images along with extracted text
# Set to 'no' to send extracted text only
MODEL_RECEIVE_IMAGES_PDF = os.getenv("MODEL_RECEIVE_IMAGES_PDF", "yes").lower() == "yes"

# Files directory for uploaded files
FILES_DIR = os.getenv("FILES_DIR", "./files")

# Vision Helper LLM configuration
# Used for image/document analysis when primary model is text-only
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
VISION_BASE_URL = os.getenv("VISION_BASE_URL", OPENAI_BASE_URL)
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")
