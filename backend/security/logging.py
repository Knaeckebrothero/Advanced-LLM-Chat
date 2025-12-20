"""
Security logging functionality.
"""
import json
import logging
import os
from datetime import datetime, UTC
from fastapi import Request
from backend.config import (
    LOG_LEVEL, LOG_FILE_LEVEL, LOG_FORMAT,
    LOG_DATE_FORMAT, LOG_DIRECTORY, LOG_FILE
)


def configure_logging():
    """
    Configures the root logger with console and file handlers.
    This function sets up centralized logging for the entire application.
    After calling this, any module can use logging.getLogger(__name__)
    to get a properly configured logger.
    """
    # Create logs directory if it doesn't exist
    os.makedirs(LOG_DIRECTORY, exist_ok=True)

    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all, handlers filter by level

    # Clear any existing handlers to avoid duplicates on re-import
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler for main application log
    log_file_path = os.path.join(LOG_DIRECTORY, LOG_FILE)
    file_handler = logging.FileHandler(log_file_path)
    file_handler.setLevel(getattr(logging, LOG_FILE_LEVEL, logging.DEBUG))
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Log startup message
    root_logger.info(f"Logging configured: console={LOG_LEVEL}, file={LOG_FILE_LEVEL}")


# Configure logging when this module is imported
configure_logging()

# Main application logger for this module
logger = logging.getLogger(__name__)

# Security logger with separate file handler
security_logger = logging.getLogger("security")
security_logger.setLevel(logging.WARNING)

# CRUD operations logger with separate file handler
crud_logger = logging.getLogger("crud")
crud_logger.setLevel(logging.INFO)

# Create file handlers for specialized loggers
# These write to their own files in addition to the main application log
security_log_path = os.path.join(LOG_DIRECTORY, 'security.log')
security_handler = logging.FileHandler(security_log_path)
security_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
security_logger.addHandler(security_handler)

crud_log_path = os.path.join(LOG_DIRECTORY, 'crud_operations.log')
crud_handler = logging.FileHandler(crud_log_path)
crud_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - [%(funcName)s] - %(message)s',
    datefmt=LOG_DATE_FORMAT
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
