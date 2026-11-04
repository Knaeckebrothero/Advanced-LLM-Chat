"""
Encryption of secrets the users store in Postgres (MCP header values, OAuth tokens).

The key comes from ENCRYPTION_KEY, any long random string: Fernet (AES-128-CBC with an
HMAC) with a key derived from it by SHA-256. Without ENCRYPTION_KEY nothing can be
encrypted, and the features that need it say so (encryption_available()).
"""
import base64
import hashlib
import json
import logging
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken

from backend.config import ENCRYPTION_KEY

log = logging.getLogger(__name__)

# Why encryption is unavailable, for the API and the logs
NO_KEY_REASON = "ENCRYPTION_KEY is not set"


class SecretUnavailable(RuntimeError):
    """No ENCRYPTION_KEY, or a value encrypted with another key."""


def _fernet() -> Optional[Fernet]:
    if not ENCRYPTION_KEY:
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(ENCRYPTION_KEY.encode()).digest())
    return Fernet(key)


_FERNET = _fernet()


def encryption_available() -> bool:
    """Whether ENCRYPTION_KEY is set."""
    return _FERNET is not None


def encrypt(value: str) -> str:
    """Encrypt a text. Raises SecretUnavailable without ENCRYPTION_KEY."""
    if _FERNET is None:
        raise SecretUnavailable(NO_KEY_REASON)
    return _FERNET.encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a text. Raises SecretUnavailable without the key it was encrypted with."""
    if _FERNET is None:
        raise SecretUnavailable(NO_KEY_REASON)
    try:
        return _FERNET.decrypt(token.encode()).decode()
    except InvalidToken:
        raise SecretUnavailable("A stored secret can't be decrypted (ENCRYPTION_KEY changed?)")


def encrypt_json(value: Any) -> str:
    """Encrypt a JSON value."""
    return encrypt(json.dumps(value))


def decrypt_json(token: Optional[str]) -> Any:
    """Decrypt a JSON value; None stays None."""
    if token is None:
        return None
    return json.loads(decrypt(token))
