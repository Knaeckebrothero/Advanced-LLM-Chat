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
│   ├── conversations.py  # Conversation endpoints (TODO)
│   ├── messages.py       # Message endpoints (TODO)
│   ├── settings.py       # Settings endpoints (TODO)
│   └── files.py          # File upload endpoints (TODO)
└── middleware/            # HTTP middleware
    ├── __init__.py
    └── middleware.py     # Logging, CSRF, security headers
```

## Status

### Completed ✓
- Backend folder structure
- Configuration module
- All Pydantic models (auth, conversation, message, settings, common)
- Database module with initialization
- Security modules (auth, CSRF, logging)
- Utility modules (certificates, hash)
- Services module (LLM operations)
- API docs routes module
- **API auth routes module** (all 5 endpoints: guest_login, mock_login, logout, refresh_session, get_me)
- Middleware module (logging, CSRF, security headers)
- Main FastAPI app setup with router registration

### Pending TODO
The following API endpoint modules have placeholder routers that need to be populated with implementations from `backend_mockup.py`:

- **Conversations endpoints** (`backend/api/conversations.py`):
  - GET /api/conversations
  - GET /api/conversation/{conversation_id}
  - POST /api/conversation/create
  - PATCH /api/conversation/{conversation_id}
  - DELETE /api/conversation/{conversation_id}
  - GET /api/conversation/messages/{conversation_id}/{timestamp}/{messages_count}

- **Messages endpoints** (`backend/api/messages.py`):
  - POST /api/message/send
  - POST /api/message/generate
  - PATCH /api/message/patch
  - DELETE /api/message/delete/{conversation_id}/{message_id}
  - POST /api/message/rate
  - POST /api/message/regenerate
  - POST /api/message/send-and-generate

- **Settings endpoints** (`backend/api/settings.py`):
  - GET /api/settings
  - PUT /api/settings

- **Files endpoints** (`backend/api/files.py`):
  - POST /api/files/upload

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

The original `backend_mockup.py` file remains intact. To complete the migration:

1. For each TODO endpoint in the API modules, extract the corresponding function from `backend_mockup.py`
2. Convert the `@app.decorator` to use the router (follow the pattern in `backend/api/auth.py`)
3. Update imports to use the new module structure
4. Uncomment the router imports in `backend/main.py`
5. Test the endpoint
6. Once all endpoints are migrated and tested, `backend_mockup.py` can be deprecated

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
