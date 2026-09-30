"""Import automatique : dossier surveillé et pièces jointes d'une boîte mail (IMAP).

Les deux sources sont en lecture seule : Binder ne déplace ni ne supprime aucun fichier du
dossier, et ouvre la boîte mail sans marquer les messages comme lus. Un document déjà présent
(même contenu), y compris à la corbeille, n'est jamais réimporté.
"""

import email
import email.policy
import hashlib
import imaplib
import logging
import threading
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlmodel import Session, select

from binder.db import get_engine
from binder.models import Document
from binder.services import activity, ingest, settings_store

log = logging.getLogger(__name__)

EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
# Un fichier modifié il y a moins de 2 s est peut-être encore en cours de copie.
SETTLE_SECONDS = 2.0
# Les petites images d'un e-mail sont des logos ou des signatures, pas des documents.
MIN_MAIL_IMAGE = 30 * 1024
FOLDER_INTERVAL = 30.0
MAIL_INTERVAL = 300.0

FOLDER_KEY = "import.folder"
MAIL_KEY = "import.mail"


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
    # Au premier passage, on remonte jusqu'à ce nombre de jours.
    since_days: int = 30
    uidvalidity: int | None = None
    last_uid: int = 0
    last_check: datetime | None = None
    last_error: str | None = None


def import_bytes(
    session: Session, data: bytes, filename: str, *, actor: str, origin: str
) -> Document | None:
    """Importe et analyse un fichier. None s'il est non pris en charge ou déjà connu."""
    try:
        mime = ingest.guess_mime(filename, None)
    except ingest.UnsupportedFile:
        return None
    digest = hashlib.sha256(data).hexdigest()
    if session.exec(select(Document.id).where(Document.sha256 == digest)).first() is not None:
        return None
    doc, created = ingest.store(session, data, filename, mime, actor=actor, origin=origin)
    if not created:
        return None
    try:
        return ingest.analyze(session, doc)
    except Exception:
        log.exception("Analyse de %s impossible", filename)
        session.rollback()
        return doc


# --- Dossier surveillé ---------------------------------------------------------------------

_seen: dict[Path, tuple[int, int]] = {}


def scan_folder(session: Session, cfg: FolderConfig) -> list[Document]:
    folder = Path(cfg.path).expanduser()
    if not folder.is_dir():
        raise FileNotFoundError(f"Dossier introuvable : {folder}")
    imported = []
    now = time.time()
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
            origin=f"depuis le dossier surveillé ({path.relative_to(folder)})",
        )
        _seen[path] = key
        if doc:
            imported.append(doc)
    return imported


# --- Boîte mail ----------------------------------------------------------------------------

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _imap_date(d: date) -> str:
    # Les noms de mois IMAP sont anglais, quelle que soit la locale.
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"


def attachments(raw: bytes) -> tuple[str, list[tuple[str, bytes]]]:
    """(description du message, [(nom, contenu)]) des pièces jointes importables."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    subject = str(msg.get("subject", "")).strip() or "sans objet"
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
    origin = f"depuis l'e-mail « {subject} »" + (f" de {sender}" if sender else "")
    return origin, found


ImapFactory = Callable[[str, int], Any]


def fetch_mail(
    session: Session, cfg: MailConfig, factory: ImapFactory | None = None
) -> list[Document]:
    """Importe les pièces jointes des nouveaux messages. Met à jour `cfg.last_uid`."""
    imported: list[Document] = []
    imap: Any = (factory or imaplib.IMAP4_SSL)(cfg.host, cfg.port)
    try:
        imap.login(cfg.user, cfg.password)
        status, _ = imap.select(f'"{cfg.folder}"', readonly=True)
        if status != "OK":
            raise RuntimeError(f"Dossier de messagerie introuvable : {cfg.folder}")
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
            # BODY.PEEK : le message n'est pas marqué comme lu.
            _, parts = imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
            raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
            if raw:
                origin, files = attachments(raw)
                for name, content in files:
                    doc = import_bytes(session, content, name, actor="mail", origin=origin)
                    if doc:
                        imported.append(doc)
            cfg.last_uid = uid
    finally:
        try:
            imap.logout()
        except Exception:
            log.debug("Déconnexion IMAP", exc_info=True)
    return imported


# --- Planification -------------------------------------------------------------------------

_lock = threading.Lock()


def run(session: Session, *, folder: bool = True, mail: bool = True) -> dict[str, Any]:
    """Un passage sur chaque source activée. Les erreurs sont gardées dans les réglages."""
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
        log.warning("Import automatique (%s) : %s", key, exc)
        session.rollback()
        docs, error = [], str(exc) or exc.__class__.__name__
    fresh = settings_store.load(session, key, type(cfg))
    # Les réglages ont pu changer pendant l'import : on ne garde que l'état de progression.
    fresh.last_check = datetime.now(UTC)
    fresh.last_error = error
    if isinstance(cfg, MailConfig) and isinstance(fresh, MailConfig):
        fresh.uidvalidity, fresh.last_uid = cfg.uidvalidity, cfg.last_uid
    if error and error != cfg.last_error:
        activity.log(session, "import_error", f"Import automatique impossible : {error}")
    settings_store.save(session, key, fresh)
    session.commit()
    return {"imported": len(docs), "error": error}


class Scheduler:
    """Thread de fond : dossier toutes les 30 s, boîte mail toutes les 5 min."""

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="binder-import", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _loop(self) -> None:
        last_mail = 0.0
        while not self._stop.wait(FOLDER_INTERVAL):
            check_mail = time.monotonic() - last_mail >= MAIL_INTERVAL
            try:
                with Session(get_engine()) as session:
                    run(session, mail=check_mail)
            except Exception:
                log.exception("Import automatique")
            if check_mail:
                last_mail = time.monotonic()
