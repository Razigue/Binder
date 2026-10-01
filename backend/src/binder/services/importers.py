"""Automatic import: watched folder and mailbox attachments (IMAP).

Both sources are read-only: Binder neither moves nor deletes any file in the folder, and opens
the mailbox without marking messages as read. A document already present (same content),
including in the trash, is never imported again.
"""

import email
import email.policy
import hashlib
import imaplib
import logging
import ssl
import threading
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlmodel import Session, select

from binder import i18n
from binder.models import Document
from binder.services import activity, ingest, settings_store

log = logging.getLogger(__name__)

EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
# A file modified less than 2 s ago may still be being copied.
SETTLE_SECONDS = 2.0
# Small images in an email are logos or signatures, not documents.
MIN_MAIL_IMAGE = 30 * 1024
FOLDER_INTERVAL = 30.0
MAIL_INTERVAL = 300.0

FOLDER_KEY = "import.folder"
MAIL_KEY = "import.mail"

T = i18n.catalog(
    "importers",
    {
        "folder_not_found": {
            "en": "Folder not found: {path}",
            "fr": "Dossier introuvable : {path}",
        },
        "mailbox_not_found": {
            "en": "Mail folder not found: {folder}",
            "fr": "Dossier de messagerie introuvable : {folder}",
        },
        "from_folder": {
            "en": "from the watched folder ({path})",
            "fr": "depuis le dossier surveillé ({path})",
        },
        "from_mail": {"en": "from the email “{subject}”", "fr": "depuis l'e-mail « {subject} »"},
        "from_mail_sender": {
            "en": "from the email “{subject}” from {sender}",
            "fr": "depuis l'e-mail « {subject} » de {sender}",
        },
        "no_subject": {"en": "no subject", "fr": "sans objet"},
        "import_error": {
            "en": "Automatic import failed: {error}",
            "fr": "Import automatique impossible : {error}",
        },
    },
)


class FolderConfig(BaseModel):
    enabled: bool = False
    path: str = ""
    last_check: datetime | None = None
    last_error: str | None = None


class MailConfig(BaseModel):
    enabled: bool = False
    host: str = ""
    port: int = 993
    user: str = ""
    password: str = ""
    folder: str = "INBOX"
    # On the first run, go back this many days.
    since_days: int = 30
    uidvalidity: int | None = None
    last_uid: int = 0
    last_check: datetime | None = None
    last_error: str | None = None


def import_bytes(
    session: Session,
    data: bytes,
    filename: str,
    *,
    actor: str,
    origin: i18n.Msg,
    batch: str | None = None,
) -> Document | None:
    """Imports and analyses a file. None if it is unsupported or already known."""
    try:
        mime = ingest.guess_mime(filename, None)
    except ingest.UnsupportedFile:
        return None
    digest = hashlib.sha256(data).hexdigest()
    if session.exec(select(Document.id).where(Document.sha256 == digest)).first() is not None:
        return None
    doc, created = ingest.store(
        session, data, filename, mime, actor=actor, origin=origin, batch=batch
    )
    if not created:
        return None
    try:
        return ingest.analyze(session, doc)
    except Exception:
        log.exception("Could not analyse %s", filename)
        session.rollback()
        return doc


# --- Watched folder ------------------------------------------------------------------------

_seen: dict[Path, tuple[int, int]] = {}


def scan_folder(session: Session, cfg: FolderConfig) -> list[Document]:
    folder = Path(cfg.path).expanduser()
    if not folder.is_dir():
        raise FileNotFoundError(T("folder_not_found", path=folder))
    imported = []
    now = time.time()
    batch = ingest.new_batch("folder")
    for path in sorted(folder.rglob("*")):
        if path.suffix.lower() not in EXTENSIONS or any(p.startswith(".") for p in path.parts):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        key = (stat.st_size, stat.st_mtime_ns)
        if _seen.get(path) == key or now - stat.st_mtime < SETTLE_SECONDS or not path.is_file():
            continue
        doc = import_bytes(
            session,
            path.read_bytes(),
            path.name,
            actor="watcher",
            origin=T.msg("from_folder", path=path.relative_to(folder).as_posix()),
            batch=batch,
        )
        _seen[path] = key
        if doc:
            imported.append(doc)
    return imported


# --- Mailbox -------------------------------------------------------------------------------

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _imap_date(d: date) -> str:
    # IMAP month names are English, whatever the locale.
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"


def attachments(raw: bytes) -> tuple[i18n.Msg, list[tuple[str, bytes]]]:
    """(message description, [(name, content)]) of the importable attachments."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    subject = str(msg.get("subject", "")).strip() or T("no_subject")
    sender = str(msg.get("from", "")).strip()
    found = []
    for part in msg.walk():
        name = part.get_filename()
        if not name or Path(name).suffix.lower() not in EXTENSIONS:
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes) or not payload:
            continue
        if part.get_content_maintype() == "image" and len(payload) < MIN_MAIL_IMAGE:
            continue
        found.append((name, payload))
    if sender:
        origin = T.msg("from_mail_sender", subject=subject, sender=sender)
    else:
        origin = T.msg("from_mail", subject=subject)
    return origin, found


ImapFactory = Callable[[str, int], Any]


def _connect(host: str, port: int) -> imaplib.IMAP4_SSL:
    # Without an explicit context, imaplib does not verify the server certificate: an attacker
    # on the network could impersonate the server and capture the password.
    return imaplib.IMAP4_SSL(host, port, ssl_context=ssl.create_default_context())


def fetch_mail(
    session: Session, cfg: MailConfig, factory: ImapFactory | None = None
) -> list[Document]:
    """Imports the attachments of new messages. Updates `cfg.last_uid`."""
    imported: list[Document] = []
    batch = ingest.new_batch("mail")
    imap: Any = (factory or _connect)(cfg.host, cfg.port)
    try:
        imap.login(cfg.user, cfg.password)
        status, _ = imap.select(f'"{cfg.folder}"', readonly=True)
        if status != "OK":
            raise RuntimeError(T("mailbox_not_found", folder=cfg.folder))
        _, validity = imap.response("UIDVALIDITY")
        uidvalidity = int(validity[0]) if validity and validity[0] else None
        if uidvalidity != cfg.uidvalidity:
            cfg.uidvalidity, cfg.last_uid = uidvalidity, 0
        if cfg.last_uid:
            criteria = f"(UID {cfg.last_uid + 1}:*)"
        else:
            criteria = f"(SINCE {_imap_date(date.today() - timedelta(days=cfg.since_days))})"
        _, data = imap.uid("SEARCH", None, criteria)
        uids = sorted(int(u) for u in (data[0] or b"").split() if int(u) > cfg.last_uid)
        for uid in uids:
            # BODY.PEEK: the message is not marked as read.
            _, parts = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
            raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
            if raw:
                origin, files = attachments(raw)
                for name, content in files:
                    doc = import_bytes(
                        session, content, name, actor="mail", origin=origin, batch=batch
                    )
                    if doc:
                        imported.append(doc)
            cfg.last_uid = uid
    finally:
        try:
            imap.logout()
        except Exception:
            log.debug("IMAP logout failed", exc_info=True)
    return imported


# --- Scheduling ----------------------------------------------------------------------------

_lock = threading.Lock()


def run(session: Session, *, folder: bool = True, mail: bool = True) -> dict[str, Any]:
    """One pass over each enabled source. Errors are kept in the settings (shown in Settings)."""
    result: dict[str, Any] = {"folder": None, "mail": None}
    with _lock:
        if folder:
            cfg = settings_store.load(session, FOLDER_KEY, FolderConfig)
            if cfg.enabled and cfg.path:
                result["folder"] = _run_source(session, FOLDER_KEY, cfg, scan_folder)
        if mail:
            mcfg = settings_store.load(session, MAIL_KEY, MailConfig)
            if mcfg.enabled and mcfg.host and mcfg.user:
                result["mail"] = _run_source(session, MAIL_KEY, mcfg, fetch_mail)
    return result


def _run_source[C: FolderConfig | MailConfig](
    session: Session, key: str, cfg: C, fn: Callable[[Session, C], list[Document]]
) -> dict[str, Any]:
    try:
        docs = fn(session, cfg)
        error = None
    except Exception as exc:
        log.warning("Automatic import (%s): %s", key, exc)
        session.rollback()
        docs, error = [], str(exc) or exc.__class__.__name__
    fresh = settings_store.load(session, key, type(cfg))
    # Settings may have changed during the import: only the progress state is kept.
    fresh.last_check = datetime.now(UTC)
    fresh.last_error = error
    if isinstance(cfg, MailConfig) and isinstance(fresh, MailConfig):
        fresh.uidvalidity, fresh.last_uid = cfg.uidvalidity, cfg.last_uid
    if error and error != cfg.last_error:
        activity.log(session, "import_error", T.msg("import_error", error=error))
    settings_store.save(session, key, fresh)
    session.commit()
    return {"imported": len(docs), "error": error}
