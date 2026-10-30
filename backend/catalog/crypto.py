"""
Encryption of the API keys that admins enter in the UI.

Keys are Fernet-encrypted with CATALOG_SECRET_KEY. If that is unset, a key is
generated once into <FILES_DIR>/.catalog_secret (mode 0600) and reused from
there, so a restart doesn't lose access to the stored keys. Back that file up
together with the database, or set CATALOG_SECRET_KEY explicitly.
"""
import logging
import os
import threading
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from backend.config import CATALOG_SECRET_KEY, FILES_DIR

log = logging.getLogger(__name__)

SECRET_FILE_NAME = ".catalog_secret"

_fernet: Optional[Fernet] = None
_lock = threading.Lock()


class CatalogSecretError(Exception):
    """The catalog secret is invalid, or a stored key cannot be decrypted with it."""


def _secret_file() -> Path:
    """Path of the generated secret, next to the uploaded files."""
    return Path(FILES_DIR) / SECRET_FILE_NAME


def _load_or_create_secret() -> bytes:
    """
    Return the Fernet key: CATALOG_SECRET_KEY, else the generated secret file.

    The file is created with O_EXCL, so two processes starting at the same
    time end up with the same key.
    """
    if CATALOG_SECRET_KEY:
        return CATALOG_SECRET_KEY.strip().encode()

    path = _secret_file()
    if path.exists():
        return path.read_bytes().strip()

    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Another process created it in the meantime
        return path.read_bytes().strip()
    with os.fdopen(fd, "wb") as f:
        f.write(key)

    log.warning(
        f"CATALOG_SECRET_KEY is not set; generated a catalog secret in {path}. "
        "Keep this file (it decrypts the stored API keys) or set CATALOG_SECRET_KEY."
    )
    return key


def _get_fernet() -> Fernet:
    """The Fernet instance, created on first use."""
    global _fernet
    if _fernet is None:
        with _lock:
            if _fernet is None:
                try:
                    _fernet = Fernet(_load_or_create_secret())
                except ValueError as e:
                    raise CatalogSecretError(
                        "Invalid catalog secret: CATALOG_SECRET_KEY (or the secret file) must be "
                        "a Fernet key, e.g. from Fernet.generate_key()"
                    ) from e
    return _fernet


def encrypt(plaintext: str) -> str:
    """
    Encrypt an API key for storage in llm_providers.api_key_encrypted.

    Args:
        plaintext: The API key.

    Returns:
        The Fernet token as a string.
    """
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    """
    Decrypt a stored API key.

    Args:
        token: The value of llm_providers.api_key_encrypted.

    Returns:
        The API key.

    Raises:
        CatalogSecretError: If the token was encrypted with another secret or is corrupt.
    """
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise CatalogSecretError(
            "A stored API key cannot be decrypted. Was CATALOG_SECRET_KEY (or the "
            f"{SECRET_FILE_NAME} file) changed? Enter the key again."
        ) from e


def mask(key: Optional[str]) -> Optional[str]:
    """
    Show an API key as its prefix and last four characters, e.g. "sk-…1234".

    Short keys show less, so a mask never reveals most of a key.

    Args:
        key: The API key, or None.

    Returns:
        The masked key, or None without a key.
    """
    if not key:
        return None
    key = key.strip()
    if len(key) < 12:
        return "…" + key[-2:] if len(key) >= 8 else "…"
    dash = key.find("-")
    prefix = key[:dash + 1] if 0 < dash <= 4 else key[:3]
    return f"{prefix}…{key[-4:]}"
