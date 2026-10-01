"""Master key management: encryption of the database (SQLCipher) and files (Fernet)."""

import base64
import hashlib
import os
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet

from binder.config import get_settings


def _load_master_secret() -> bytes:
    settings = get_settings()
    if settings.db_key:
        return settings.db_key.encode()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    key_file = settings.data_dir / "key"
    if not key_file.exists():
        fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(48))
    return key_file.read_text().strip().encode()


def _derive(purpose: str) -> bytes:
    return hashlib.sha256(_load_master_secret() + b":" + purpose.encode()).digest()


@lru_cache
def db_key() -> str:
    """Raw hexadecimal key for SQLCipher (x'...')."""
    return _derive("sqlcipher").hex()


@lru_cache
def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(_derive("files")))


def encrypt(data: bytes) -> bytes:
    return _fernet().encrypt(data)


def decrypt(token: bytes) -> bytes:
    return _fernet().decrypt(token)


def reset_caches() -> None:
    db_key.cache_clear()
    _fernet.cache_clear()
