"""
Configuration constants and settings for the backend application.
"""
import os
from dotenv import load_dotenv, find_dotenv

# TODO: Change this to a propper .cfg or .toml based config with a config loader!

# Load environment variables
load_dotenv(find_dotenv())

# CORS configuration
# Can be set via CORS_ORIGINS env var as comma-separated list
# Example: CORS_ORIGINS=http://10.18.2.105:8200,https://example.com
_cors_env = os.getenv('CORS_ORIGINS', '')
CORS_ORIGINS = [
    origin.strip() for origin in _cors_env.split(',') if origin.strip()
] if _cors_env else [
    "http://localhost:4200",  # Angular default
    "http://localhost:8080",  # Common dev port
    "https://localhost:4200",
    "https://localhost:8080",
]

# PostgreSQL configuration
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_DB = os.getenv('POSTGRES_DB', 'llm_chat')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'llm_chat')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', '')
POSTGRES_MIN_CONNECTIONS = int(os.getenv('POSTGRES_MIN_CONNECTIONS', '1'))
POSTGRES_MAX_CONNECTIONS = int(os.getenv('POSTGRES_MAX_CONNECTIONS', '10'))

# Database URL (can override individual settings)
DATABASE_URL = os.getenv('DATABASE_URL', None)

# Neo4j Knowledge Graph configuration (optional)
# When enabled, the agent gets read-only tools to inspect, search and query the graph
NEO4J_ENABLED = os.getenv('NEO4J_ENABLED', 'false').lower() == 'true'
NEO4J_URI = os.getenv('NEO4J_URI', 'bolt://localhost:7687')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'llm_chat_neo4j_dev')
# Optional Cypher file that app_init uses to seed an empty graph
NEO4J_SEED_FILE = os.getenv('NEO4J_SEED_FILE')
# Maximum number of rows a graph tool returns to the agent
NEO4J_MAX_RESULTS = int(os.getenv('NEO4J_MAX_RESULTS', '25'))

# SSL/TLS configuration
USE_DEV_CERTS = os.getenv("USE_DEV_CERTS") == "True"
SSL_CERTFILE = os.getenv("SSL_CERTFILE")  # Path to certificate file (overrides USE_DEV_CERTS)
SSL_KEYFILE = os.getenv("SSL_KEYFILE")    # Path to private key file (overrides USE_DEV_CERTS)

# Server configuration
HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", "8443"))

# Filesystem configuration
FILESYSTEM_PATH = os.getenv("FILESYSTEM_PATH", "filesystem")

# Tavily Web Search configuration
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Image processing configuration for LLM
# Whether the chat model gets images is decided per model (ModelConfig.supports_vision);
# text-only models get placeholders and read files through the get_file_content tool.
# MODEL_RECEIVE_IMAGES is only the default of FileRetrievalService.get_content().
MODEL_RECEIVE_IMAGES = os.getenv("MODEL_RECEIVE_IMAGES", "false").lower() == "true"

# PDF page images for LLM (vision-capable models only)
# Set to 'true' to send PDF page images along with extracted text
# Set to 'false' to send extracted text only
MODEL_RECEIVE_IMAGES_PDF = os.getenv("MODEL_RECEIVE_IMAGES_PDF", "false").lower() == "true"

# Files directory for uploaded files
FILES_DIR = os.getenv("FILES_DIR", "./files")

# Vision Helper LLM configuration
# Used for image/document analysis when primary model is text-only
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
VISION_BASE_URL = os.getenv("VISION_BASE_URL", OPENAI_BASE_URL)
VISION_MODEL = os.getenv("VISION_MODEL", "gpt-4o-mini")
VISION_TIMEOUT = float(os.getenv("VISION_TIMEOUT", "120"))  # Timeout for vision requests

# OpenAI Audio/Whisper Configuration
# WHISPER_BASE_URL allows deploying Whisper on a separate server/GPU from other models
WHISPER_BASE_URL = os.getenv("WHISPER_BASE_URL", OPENAI_BASE_URL)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", None)  # Optional: 'en', 'de', etc.
WHISPER_TIMEOUT = float(os.getenv("WHISPER_TIMEOUT", "120"))  # Timeout for transcription requests
USE_LOCAL_WHISPER = os.getenv("USE_LOCAL_WHISPER", "false").lower() == "true"
LOCAL_WHISPER_MODEL = os.getenv("LOCAL_WHISPER_MODEL", "base")  # tiny, base, small, medium, large

# Text-to-Speech Configuration
# TTS_BASE_URL allows deploying TTS on a separate server/GPU from other models
TTS_BASE_URL = os.getenv("TTS_BASE_URL", OPENAI_BASE_URL)
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")  # tts-1 (fast) or tts-1-hd (quality)
TTS_VOICE_EN = os.getenv("TTS_VOICE_EN", "nova")  # Voice for English
TTS_VOICE_DE = os.getenv("TTS_VOICE_DE", "onyx")  # Voice for German
TTS_TIMEOUT = float(os.getenv("TTS_TIMEOUT", "120"))  # Timeout for TTS requests

# TTS Preprocessing Configuration
# Preprocesses text through LLM before TTS to improve audio quality
# Removes markdown, converts tables to prose, summarizes code blocks
TTS_PREPROCESS_ENABLED = os.getenv("TTS_PREPROCESS_ENABLED", "true").lower() == "true"
TTS_PREPROCESS_VERSION = "v1"  # Increment to invalidate cached preprocessed text

# LLM request timeout in seconds, for every provider (backend/llm/client.py)
# Increase for slow models (CPU inference, model loading time)
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))

# Reasoning effort of the environment fallback model (backend/llm/types.py reads these directly):
# REASONING_LEVEL is the reasoning_effort of the OpenAI environment model for chat answers,
# AUXILIARY_REASONING_LEVEL the effort for titles and speech preprocessing (Claude: output_config.effort).
# Unset = the provider's default. Catalog models carry their own reasoning_effort.

# Logging configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE_LEVEL = os.getenv("LOG_FILE_LEVEL", "DEBUG").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
LOG_DATE_FORMAT = os.getenv("LOG_DATE_FORMAT", "%Y-%m-%d %H:%M:%S")
LOG_DIRECTORY = os.getenv("LOG_DIRECTORY", os.path.join(FILESYSTEM_PATH, "logs"))
LOG_FILE = os.getenv("LOG_FILE", "application.log")

# Model catalog
# Fernet key for API keys entered in the UI. If unset, a key is generated once and
# stored next to the uploaded files (see backend/catalog/crypto.py).
CATALOG_SECRET_KEY = os.getenv("CATALOG_SECRET_KEY")
# Optional JSON file with providers, models and personas that app_init seeds into the catalog
MODEL_CATALOG_FILE = os.getenv("MODEL_CATALOG_FILE")
# Users who may manage the catalog, until roles come from Keycloak (comma-separated emails)
ADMIN_EMAILS = {
    email.strip().lower() for email in os.getenv("ADMIN_EMAILS", "").split(",") if email.strip()
}

# Agent loop
# Maximum number of model calls per answer (each tool round counts as one)
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))
