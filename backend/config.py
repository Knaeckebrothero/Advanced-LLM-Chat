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
# text-only models get placeholders and read files through the read_file tool.
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

# Conversation history sent to the model (backend/services/conversation_history.py):
# the newest messages that fit the model's context window (the catalog's context_window,
# DEFAULT_CONTEXT_WINDOW for models without one), at most HISTORY_MAX_MESSAGES
DEFAULT_CONTEXT_WINDOW = int(os.getenv("DEFAULT_CONTEXT_WINDOW", "32768"))
HISTORY_MAX_MESSAGES = int(os.getenv("HISTORY_MAX_MESSAGES", "1000"))
# Earlier answers go back to the model with their tool calls and the results (backend/llm/tool_record.py),
# so it knows what it did. Off: only their text, as before. A result longer than
# HISTORY_TOOL_RESULT_CHARS is cut in later turns (0: never); the model can call the tool again.
HISTORY_TOOL_CALLS = os.getenv("HISTORY_TOOL_CALLS", "true").lower() == "true"
HISTORY_TOOL_RESULT_CHARS = int(os.getenv("HISTORY_TOOL_RESULT_CHARS", "20000"))

# Memory review (backend/services/memory_review.py): once a conversation with a knowledge base
# agent has had no new message for MEMORY_REVIEW_IDLE_MINUTES, a model reads what was said since
# the last review and saves what matters to the agent's memory and knowledge base. Conversations
# quiet for more than MEMORY_REVIEW_MAX_AGE_DAYS are left alone (e.g. old ones of an agent that
# just got the knowledge base).
MEMORY_REVIEW_ENABLED = os.getenv("MEMORY_REVIEW_ENABLED", "true").lower() == "true"
MEMORY_REVIEW_IDLE_MINUTES = float(os.getenv("MEMORY_REVIEW_IDLE_MINUTES", "15"))
MEMORY_REVIEW_MAX_AGE_DAYS = float(os.getenv("MEMORY_REVIEW_MAX_AGE_DAYS", "7"))
# The time zone of the memory's dates ("today" in the prompt, the date of a memory line) and of the
# days in the journal of the nightly consolidation (backend/services/memory_dream.py), e.g. Europe/Berlin
MEMORY_TIME_ZONE = os.getenv("MEMORY_TIME_ZONE", "UTC")

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
# JSON file with providers, models and personas that app_init seeds into the catalog
# (relative to the repository root). Providers are taken from it on every seed; models
# and personas are only created when missing, so edits in the app are kept.
# Set it to an empty value to disable seeding. Provider API keys always come from the
# environment variables the providers name (api_key_env).
MODEL_CATALOG_FILE = os.getenv("MODEL_CATALOG_FILE", "catalog/models.json")
# Users who may manage the catalog (comma-separated emails). With AUTH_MODE=oidc they
# count only if the provider says the email is verified; OIDC_ADMIN_ROLE is the usual way there.
ADMIN_EMAILS = {
    email.strip().lower() for email in os.getenv("ADMIN_EMAILS", "").split(",") if email.strip()
}

# Authentication (docs/authentication.md). Guests can always chat; AUTH_MODE decides how
# everyone else logs in:
#   oidc: through an OpenID Connect provider such as Keycloak (the OIDC_* settings)
#   mock: with any email and no password (development only, never on a reachable server)
#   none: not at all (the default)
AUTH_MODE = os.getenv("AUTH_MODE", "").strip().lower() or "none"
SESSION_TIMEOUT_HOURS = int(os.getenv("SESSION_TIMEOUT_HOURS", "24"))
GUEST_SESSION_TIMEOUT_HOURS = int(os.getenv("GUEST_SESSION_TIMEOUT_HOURS", "6"))
# The provider's issuer, e.g. https://auth.example.com/realms/home for a Keycloak realm
OIDC_ISSUER = os.getenv("OIDC_ISSUER", "").strip().rstrip("/")
# Where the backend reads the provider's metadata; set it when the backend reaches the
# provider under another address than the browser (the bundled Keycloak in docker compose)
OIDC_DISCOVERY_URL = os.getenv("OIDC_DISCOVERY_URL", "").strip() or (
    f"{OIDC_ISSUER}/.well-known/openid-configuration" if OIDC_ISSUER else "")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "").strip()
OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET", "").strip()
OIDC_SCOPES = os.getenv("OIDC_SCOPES", "openid profile email").strip()
# Roles (Keycloak realm or client roles, or groups) that make a user an admin, or let a user
# log in at all; empty means no admin role, and everyone the provider accepts may log in
OIDC_ADMIN_ROLE = os.getenv("OIDC_ADMIN_ROLE", "").strip()
OIDC_REQUIRED_ROLE = os.getenv("OIDC_REQUIRED_ROLE", "").strip()
# Shown on the login button ("Log in with Keycloak")
OIDC_DISPLAY_NAME = os.getenv("OIDC_DISPLAY_NAME", "").strip() or "Keycloak"
# The backend's public address, which the provider redirects back to after a login; without
# OIDC_REDIRECT_URI it's API_URL (the backend address the frontend uses) or the request's address
_api_url = os.getenv("API_URL", "").strip().rstrip("/")
OIDC_REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI", "").strip() or (
    f"{_api_url}/api/auth/oidc/callback" if _api_url else "")
# The frontend's address, where a login or logout ends
FRONTEND_URL = (os.getenv("FRONTEND_URL", "").strip() or (CORS_ORIGINS[0] if _cors_env else "https://localhost:4200")).rstrip("/")

# Agent loop
# Maximum number of model calls per answer (each tool round counts as one)
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))

# Encrypts secrets the users store (MCP header values, OAuth tokens) in Postgres: any long random
# string, e.g. `openssl rand -hex 32`. Without it those features are unavailable; changing it makes
# the stored secrets unreadable (users sign in again).
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "").strip()

# MCP servers (docs/mcp.md): tools of Model Context Protocol servers for the agents
MCP_ENABLED = os.getenv("MCP_ENABLED", "true").lower() == "true"
# Admins may define stdio servers: commands the backend starts as subprocesses, with its rights
MCP_STDIO_ENABLED = os.getenv("MCP_STDIO_ENABLED", "false").lower() == "true"
# Signed-in users may add their own servers (used by agents that select the tool group user_mcp)
MCP_USER_SERVERS = os.getenv("MCP_USER_SERVERS", "true").lower() == "true"
# Users' own servers (and the OAuth endpoints they name) may be on private or loopback addresses
MCP_ALLOW_PRIVATE_URLS = os.getenv("MCP_ALLOW_PRIVATE_URLS", "false").lower() == "true"
# Where OAuth providers send the browser back after an MCP sign-in; without it API_URL's callback
# or the request's address
MCP_OAUTH_REDIRECT_URI = os.getenv("MCP_OAUTH_REDIRECT_URI", "").strip() or (
    f"{_api_url}/api/mcp/oauth/callback" if _api_url else "")
# The client name shown on a provider's consent page (dynamic client registration)
MCP_OAUTH_CLIENT_NAME = os.getenv("MCP_OAUTH_CLIENT_NAME", "").strip() or "LLM Chat"
MCP_CONNECT_TIMEOUT = float(os.getenv("MCP_CONNECT_TIMEOUT", "20"))  # Connect and list the tools
MCP_TOOL_TIMEOUT = float(os.getenv("MCP_TOOL_TIMEOUT", "120"))  # One tool call
MCP_IDLE_TIMEOUT = float(os.getenv("MCP_IDLE_TIMEOUT", "300"))  # An unused connection is closed
# How long a server's question to the user (elicitation) waits for an answer before it is cancelled
MCP_ELICITATION_TIMEOUT = float(os.getenv("MCP_ELICITATION_TIMEOUT", "300"))
MCP_MAX_RESULT_CHARS = int(os.getenv("MCP_MAX_RESULT_CHARS", "50000"))  # Longer tool results are cut
