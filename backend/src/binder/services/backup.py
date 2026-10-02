"""Automatic backup and recovery code.

Once a day, when something changed, Binder writes one archive of the library to the backup
folder: the database as SQLCipher keeps it (encrypted), the encrypted files, and the master
secret wrapped with the recovery code (scrypt + Fernet). Nothing in it is readable without that
code. The code is shown once, in the To do feed, until the user says they wrote it down; it is
then forgotten by Binder.

On a new computer (or after losing the `key` file), the welcome screen restores an archive with
the code.
"""

import base64
import json
import logging
import os
import secrets
import shutil
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from binder import __version__, i18n, security
from binder.config import get_settings
from binder.models import Activity
from binder.services import activity, settings_store

log = logging.getLogger(__name__)

T = i18n.catalog(
    "backup",
    {
        "folder": {"en": "Binder backups", "fr": "Sauvegardes Binder"},
        "done": {"en": "Backup saved ({name})", "fr": "Sauvegarde enregistrée ({name})"},
        "restored": {"en": "Library restored from a backup", "fr": "Bibliothèque restaurée"},
        "wrong_code": {
            "en": "This recovery code does not open this backup.",
            "fr": "Ce code de récupération n'ouvre pas cette sauvegarde.",
        },
        "not_backup": {
            "en": "This file is not a Binder backup.",
            "fr": "Ce fichier n'est pas une sauvegarde Binder.",
        },
        "env_key": {
            "en": "The key is set by BINDER_DB_KEY: remove it to restore a backup.",
            "fr": "La clé est fixée par BINDER_DB_KEY : retirez-la pour restaurer.",
        },
    },
)

KEY = "backup"
EXTENSION = ".binderbackup"
KEEP = 7
EVERY = timedelta(days=1)
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I
GROUPS, GROUP_SIZE = 6, 4


class BackupState(BaseModel):
    # Shown until the user confirms they wrote it down, then erased.
    code: str | None = None
    confirmed: bool = False
    # Master secret wrapped with the code: salt and Fernet token (base64).
    salt: str = ""
    wrapped: str = ""
    last_backup: datetime | None = None
    last_activity: int = 0
    last_error: str | None = None


class BackupInfo(BaseModel):
    code: str | None
    confirmed: bool
    folder: str
    last_backup: datetime | None
    last_error: str | None


class WrongCode(ValueError):
    pass


def new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(GROUPS * GROUP_SIZE))
    return "-".join(raw[i : i + GROUP_SIZE] for i in range(0, len(raw), GROUP_SIZE))


def _normalize(code: str) -> bytes:
    return "".join(c for c in code.upper() if c.isalnum()).encode()


def _fernet(code: str, salt: bytes) -> Fernet:
    kdf = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1)
    return Fernet(base64.urlsafe_b64encode(kdf.derive(_normalize(code))))


def wrap(code: str) -> tuple[str, str]:
    salt = os.urandom(16)
    token = _fernet(code, salt).encrypt(security.master_secret())
    return base64.b64encode(salt).decode(), token.decode()


def unwrap(code: str, salt: str, wrapped: str) -> bytes:
    try:
        return _fernet(code, base64.b64decode(salt)).decrypt(wrapped.encode())
    except (InvalidToken, ValueError) as e:
        raise WrongCode(T("wrong_code")) from e


def state(session: Session) -> BackupState:
    """The saved state; creates the recovery code on first use."""
    current = settings_store.load(session, KEY, BackupState)
    if not current.wrapped:
        current.code = new_code()
        current.salt, current.wrapped = wrap(current.code)
        settings_store.save(session, KEY, current)
        session.commit()
    return current


def info(session: Session) -> BackupInfo:
    current = state(session)
    return BackupInfo(
        code=None if current.confirmed else current.code,
        confirmed=current.confirmed,
        folder=str(folder()),
        last_backup=current.last_backup,
        last_error=current.last_error,
    )


def confirm(session: Session) -> None:
    """The user wrote the code down: Binder forgets it."""
    current = state(session)
    current.confirmed, current.code = True, None
    settings_store.save(session, KEY, current)


def renew_code(session: Session) -> str:
    """A new code (the former one keeps opening the former backups)."""
    current = state(session)
    current.code = new_code()
    current.salt, current.wrapped = wrap(current.code)
    current.confirmed = False
    settings_store.save(session, KEY, current)
    return current.code


def folder() -> Path:
    settings = get_settings()
    if settings.backup_dir is not None:
        return settings.backup_dir.expanduser()
    documents = Path.home() / "Documents"
    if documents.is_dir():
        return documents / T.get("folder", i18n.current_language())
    return settings.data_dir / "backups"


def _export_database(target: Path) -> None:
    """Consistent encrypted copy of the database (sqlcipher_export, same key)."""
    from binder.db import _connect

    conn = _connect()
    try:
        key = security.db_key()
        conn.execute(f"ATTACH DATABASE ? AS backup KEY \"x'{key}'\"", (str(target),))
        conn.execute("SELECT sqlcipher_export('backup')")
        conn.execute("DETACH DATABASE backup")
    finally:
        conn.close()


def create(session: Session) -> Path:
    """Writes a backup archive now; keeps the latest ones."""
    current = state(session)
    settings = get_settings()
    dest = folder()
    dest.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H.%M")
    final = dest / f"Binder {stamp}{EXTENSION}"
    partial = final.with_suffix(".partial")
    database = dest / ".binder-export.db"
    database.unlink(missing_ok=True)
    try:
        _export_database(database)
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_STORED) as archive:
            archive.write(database, "binder.db")
            files = settings.files_dir
            if files.is_dir():
                for path in sorted(files.iterdir()):
                    if path.is_file():
                        archive.write(path, f"files/{path.name}")
            archive.writestr(
                "recovery.json",
                json.dumps(
                    {
                        "version": __version__,
                        "created_at": datetime.now(UTC).isoformat(),
                        "salt": current.salt,
                        "wrapped": current.wrapped,
                    }
                ),
            )
        partial.replace(final)
    finally:
        database.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
    for old in sorted(dest.glob(f"Binder *{EXTENSION}"))[:-KEEP]:
        old.unlink(missing_ok=True)
    current = settings_store.load(session, KEY, BackupState)
    current.last_backup = datetime.now(UTC)
    current.last_error = None
    current.last_activity = _activity_mark(session)
    settings_store.save(session, KEY, current)
    activity.log(session, "backup", T.msg("done", name=final.name))
    session.commit()
    return final


def _activity_mark(session: Session) -> int:
    return int(session.exec(select(func.max(Activity.id))).one() or 0)


def due(session: Session, now: datetime | None = None) -> bool:
    """A backup is due once a day, when something changed since the last one."""
    current = settings_store.load(session, KEY, BackupState)
    now = now or datetime.now(UTC)
    last = current.last_backup
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    if last is not None and now - last < EVERY:
        return False
    return _activity_mark(session) > current.last_activity


def run_if_due(session: Session) -> Path | None:
    if not due(session):
        return None
    try:
        return create(session)
    except Exception as e:
        log.exception("Backup failed")
        session.rollback()
        current = settings_store.load(session, KEY, BackupState)
        current.last_error = str(e) or type(e).__name__
        settings_store.save(session, KEY, current)
        session.commit()
        return None


def restore(archive_path: Path, code: str) -> None:
    """Replaces the (empty) library with the archive's. The database engine must be closed."""
    settings = get_settings()
    if settings.db_key:
        raise WrongCode(T("env_key"))
    try:
        archive = zipfile.ZipFile(archive_path)
    except (zipfile.BadZipFile, OSError) as e:
        raise ValueError(T("not_backup")) from e
    with archive:
        names = set(archive.namelist())
        if not {"binder.db", "recovery.json"} <= names:
            raise ValueError(T("not_backup"))
        recovery = json.loads(archive.read("recovery.json"))
        secret = unwrap(code, recovery["salt"], recovery["wrapped"])
        data = settings.data_dir
        data.mkdir(parents=True, exist_ok=True)
        staging = data / "restore.partial"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        for name in names:
            if name == "binder.db" or (name.startswith("files/") and "/" not in name[6:]):
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    for suffix in ("", "-wal", "-shm"):
        (data / f"binder.db{suffix}").unlink(missing_ok=True)
    (staging / "binder.db").replace(data / "binder.db")
    files = data / "files"
    files.mkdir(exist_ok=True)
    if (staging / "files").is_dir():
        for path in (staging / "files").iterdir():
            path.replace(files / path.name)
    shutil.rmtree(staging, ignore_errors=True)
    key_file = data / "key"
    key_file.unlink(missing_ok=True)
    fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(secret.decode())
    security.reset_caches()


def log_restored(session: Session) -> None:
    activity.log(session, "backup", T.msg("restored"), actor="user")
    current = settings_store.load(session, KEY, BackupState)
    # The code that opened the backup is known to the user.
    current.confirmed, current.code = True, None
    settings_store.save(session, KEY, current)
    session.commit()
