"""
Security logging functionality.
"""
import json
import logging
import os
from datetime import datetime, UTC
from fastapi import Request
from backend.config import FILESYSTEM_PATH

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Main application logger
logger = logging.getLogger(__name__)

# Security logger with separate handler
security_logger = logging.getLogger("security")
security_logger.setLevel(logging.WARNING)

# CRUD operations logger
crud_logger = logging.getLogger("crud")
crud_logger.setLevel(logging.INFO)

# Create a file handler for security events
logs_dir = os.path.join(FILESYSTEM_PATH, 'logs')
os.makedirs(logs_dir, exist_ok=True)
security_log_path = os.path.join(logs_dir, 'security.log')
security_handler = logging.FileHandler(security_log_path)
security_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
security_logger.addHandler(security_handler)

# Create a file handler for CRUD operations
crud_log_path = os.path.join(logs_dir, 'crud_operations.log')
crud_handler = logging.FileHandler(crud_log_path)
crud_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s'
))
crud_logger.addHandler(crud_handler)


def log_security_event(event_type: str, details: dict, request: Request = None):
    """
    Logs a security event with details and optional request information. This
    function creates a structured log entry containing the type of event, the
    event details, and timestamp. If a request object is provided, it includes
    information about the request such as HTTP method, URL path, client host,
    and specific headers. All log entries are serialized to JSON format and
    logged with a warning level.

    :param event_type: Type of the security event.
    :type event_type: str
    :param details: A dictionary containing the details of the event.
    :type details: dict
    :param request: Optional HTTP request data associated with the event.
    :type request: Request or None
    :return: None
    """
    log_entry = {
        "event_type": event_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "details": details
    }

    if request:
        log_entry["request_info"] = {
            "method": request.method,
            "path": str(request.url.path),
            "client_host": request.client.host if request.client else "unknown",
            "headers": {
                "user-agent": request.headers.get("user-agent", "unknown"),
                "origin": request.headers.get("origin", "unknown")
            }
        }

    security_logger.warning(json.dumps(log_entry))
