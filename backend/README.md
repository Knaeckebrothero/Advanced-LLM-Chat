# Backend Refactoring

This directory contains the refactored backend code, organized into a proper module structure.

## Structure

```
backend/
├── __init__.py
├── main.py                 # FastAPI app setup and entry point
├── config.py               # Configuration constants
├── models/                 # Pydantic models
│   ├── __init__.py
│   ├── auth.py            # Authentication models
│   ├── common.py          # Common models (ErrorResponse)
│   ├── conversation.py    # Conversation models
│   ├── message.py         # Message models
│   └── settings.py        # Settings models
├── database/              # Database operations
│   ├── __init__.py
│   └── db.py             # Database initialization and connection
├── security/              # Security and authentication
│   ├── __init__.py
│   ├── auth.py           # Session management
│   ├── csrf.py           # CSRF token handling
│   └── logging.py        # Security logging
├── utils/                 # Utility functions
│   ├── __init__.py
│   ├── certificates.py   # SSL certificate generation
│   └── hash.py           # Hash utilities
├── services/              # Business logic services
│   ├── __init__.py
│   └── llm.py            # LLM operations
├── api/                   # API endpoints
│   ├── __init__.py
│   ├── auth.py           # Auth endpoints (✓ Complete)
│   ├── docs.py           # Documentation endpoints (✓ Complete)
│   ├── conversations.py  # Conversation endpoints (✓ Complete)
│   ├── messages.py       # Message endpoints (✓ Complete)
│   ├── settings.py       # Settings endpoints (✓ Complete)
│   └── files.py          # File upload endpoints (✓ Complete)
└── middleware/            # HTTP middleware
    ├── __init__.py
    └── middleware.py     # Logging, CSRF, security headers
```

## Status

### ✅ Refactoring Complete

All components have been successfully migrated from `backend_mockup.py`:

- ✅ Backend folder structure
- ✅ Configuration module
- ✅ All Pydantic models (24 total: auth, conversation, message, settings, common)
- ✅ Database module with complete schema initialization
- ✅ Security modules (auth, CSRF, logging)
- ✅ Utility modules (certificates, hash)
- ✅ Services module (LLM operations)
- ✅ API routes - all 24 endpoints:
  - **Auth** (5): guest_login, mock_login, logout, refresh_session, get_me
  - **Conversations** (6): list, get, create, update, delete, get_messages
  - **Messages** (7): send, generate, patch, delete, rate, regenerate, send_and_generate
  - **Settings** (2): get, update
  - **Files** (1): upload
  - **Docs** (3): openapi, swagger_ui, preflight
- ✅ Middleware module (logging, CSRF, security headers)
- ✅ Main FastAPI app setup with all routers registered

## How to Run

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the backend:
   ```bash
   python backend/main.py
   ```

   Or using the refactored structure:
   ```bash
   cd backend
   python main.py
   ```

3. The server will start on the configured host/port (default: https://127.0.0.1:8000 in dev mode with SSL)

## Migration from backend_mockup.py

✅ **Migration Complete**: All functionality from `backend_mockup.py` has been successfully migrated to the modular structure.

The original `backend_mockup.py` file (3,602 lines) remains in the repository for reference and can be safely deprecated once the refactored backend has been tested in production.

## Key Changes from backend_mockup.py

- **Modular structure**: Code organized by function (models, services, API routes, etc.)
- **Router-based endpoints**: Using FastAPI routers instead of direct app decorators
- **Clear separation of concerns**: Database, security, services, and API layers
- **Easier testing**: Individual modules can be tested independently
- **Better maintainability**: Smaller, focused files instead of one large 3600+ line file

## Development Notes

- The refactored backend uses the same database schema as the original
- All security features (CSRF, session management, rate limiting) are preserved
- The middleware stack is identical to the original implementation
- SSL certificate generation for development remains unchanged
