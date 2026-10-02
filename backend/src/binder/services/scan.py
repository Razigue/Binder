"""Phone scanning: a session, its pages, and the server the phone talks to.

The main server only listens on the loopback interface. To let a phone send its photos, a second
server listens on the local network, over HTTPS (browsers only grant camera access to a secure
page), and only while a scan session is open. It serves the scanning page and receives images:
nothing else, and never the documents. Each session draws a random token, carried by the QR code;
every request from the phone must present it.

Pages stay in memory until the import: they never touch the disk unencrypted.
"""

import datetime as dt
import ipaddress
import logging
import os
import secrets
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import segno
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from sqlmodel import Session

from binder import i18n
from binder.config import get_settings
from binder.db import get_engine
from binder.services import ingest, scan_image

log = logging.getLogger(__name__)

T = i18n.catalog(
    "scan",
    {
        "from_phone": {"en": "from the phone", "fr": "depuis le téléphone"},
        "filename": {"en": "Scan {stamp}", "fr": "Scan {stamp}"},
    },
)

MAX_PAGES = 200
# A session forgotten with the window open closes by itself.
IDLE_TIMEOUT = 30 * 60
# The phone is shown as connected if it was heard from recently (it polls every few seconds).
CONNECTED_WITHIN = 8.0
# iOS refuses certificates valid for more than 825 days, even once accepted by hand.
CERT_DAYS = 800


class ScanError(RuntimeError):
    pass


class NoNetwork(ScanError):
    pass


@dataclass
class ScanPage:
    id: str
    document: int
    page: scan_image.Page


@dataclass
class ScanSession:
    token: str
    url: str
    created: float = field(default_factory=time.monotonic)
    last_activity: float = field(default_factory=time.monotonic)
    phone_seen: float | None = None
    pages: list[ScanPage] = field(default_factory=list)
    imported: list[int] | None = None

    def touch(self, *, phone: bool = False) -> None:
        self.last_activity = time.monotonic()
        if phone:
            self.phone_seen = self.last_activity

    @property
    def phone_connected(self) -> bool:
        return self.phone_seen is not None and time.monotonic() - self.phone_seen < CONNECTED_WITHIN

    def documents(self) -> list[list[ScanPage]]:
        """Pages grouped by document, in the order the phone numbered them."""
        groups: dict[int, list[ScanPage]] = {}
        for page in self.pages:
            groups.setdefault(page.document, []).append(page)
        return [groups[key] for key in sorted(groups)]

    def find(self, page_id: str) -> ScanPage | None:
        return next((p for p in self.pages if p.id == page_id), None)

    def qr_code(self) -> str:
        """QR code as an SVG data URI, dark on light whatever the theme (scanners need it)."""
        return str(segno.make(self.url, error="m").svg_data_uri(scale=6, border=2))


# --- Network --------------------------------------------------------------------------------


def lan_address() -> str | None:
    """IPv4 address of this computer on the local network (interface of the default route)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            # UDP: nothing is sent, the system only picks the outgoing interface.
            s.connect(("10.254.254.254", 1))
            address = str(s.getsockname()[0])
        except OSError:
            return None
    ip = ipaddress.ip_address(address)
    return None if ip.is_loopback or ip.is_unspecified or ip.is_link_local else address


def _cert_dir() -> Path:
    return get_settings().data_dir / "scan"


def certificate(address: str) -> tuple[Path, Path]:
    """Self-signed certificate for `address`, kept between launches so that the phone only has
    to accept it once. Renewed when it expires or when the computer's address changes."""
    folder = _cert_dir()
    cert_path, key_path = folder / "cert.pem", folder / "key.pem"
    if cert_path.exists() and key_path.exists():
        try:
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
            names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            ips = {str(ip) for ip in names.get_values_for_type(x509.IPAddress)}
            fresh = cert.not_valid_after_utc - dt.datetime.now(dt.UTC) > dt.timedelta(days=7)
            if address in ips and fresh:
                return cert_path, key_path
        except (ValueError, x509.ExtensionNotFound):
            pass

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Binder")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=CERT_DAYS))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(address))]),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    folder.mkdir(parents=True, exist_ok=True)
    key_path.unlink(missing_ok=True)
    with os.fdopen(os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
        f.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def _bind(port: int) -> socket.socket:
    """Listening socket on every interface: the preferred port, or any free one."""
    for candidate in (port, 0):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("0.0.0.0", candidate))
            return sock
        except OSError:
            sock.close()
    raise ScanError("No port available")


class _Server:
    """The HTTPS server of the phone, in a thread of this process."""

    def __init__(self, address: str) -> None:
        from binder.scan_app import create_scan_app

        cert, key = certificate(address)
        self.socket = _bind(get_settings().scan_port)
        self.port = int(self.socket.getsockname()[1])
        config = uvicorn.Config(
            create_scan_app(),
            ssl_certfile=str(cert),
            ssl_keyfile=str(key),
            log_level="warning",
            # The phone keeps its connection open between frames.
            timeout_keep_alive=30,
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(
            target=self.server.run, kwargs={"sockets": [self.socket]}, daemon=True
        )

    def start(self) -> None:
        self.thread.start()
        deadline = time.monotonic() + 5
        while not self.server.started and self.thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not self.server.started:
            self.stop()
            raise ScanError("The scanning server did not start")

    def stop(self) -> None:
        self.server.should_exit = True
        if self.thread.is_alive():
            self.thread.join(timeout=5)
        self.socket.close()


# --- Session --------------------------------------------------------------------------------

_lock = threading.RLock()
_session: ScanSession | None = None
_server: _Server | None = None
_watchdog: threading.Thread | None = None
# Analysis of imported documents still running in the background (see wait_for_analysis).
_analysis_threads: list[threading.Thread] = []


def current() -> ScanSession | None:
    return _session


def start() -> ScanSession:
    """Opens a scan session (or returns the one in progress) and starts the server."""
    global _session, _server
    with _lock:
        if _session is not None and _session.imported is None:
            _session.touch()
            return _session
        address = lan_address()
        if address is None:
            raise NoNetwork("No local network")
        if _server is None:
            server = _Server(address)
            server.start()
            _server = server
        token = secrets.token_urlsafe(24)
        url = f"https://{address}:{_server.port}/?t={token}"
        _session = ScanSession(token=token, url=url)
        _start_watchdog()
        log.info("Phone scanning open on %s:%s", address, _server.port)
        return _session


def stop() -> None:
    """Closes the session, discards pages not imported and stops the server."""
    global _session, _server
    with _lock:
        _session = None
        server, _server = _server, None
    if server is not None:
        server.stop()
        log.info("Phone scanning closed")


def check_token(token: str | None) -> ScanSession | None:
    session = _session
    if session is None or token is None or not secrets.compare_digest(token, session.token):
        return None
    return session


def _start_watchdog() -> None:
    global _watchdog
    if _watchdog is not None and _watchdog.is_alive():
        return

    def watch() -> None:
        while True:
            time.sleep(15)
            with _lock:
                session = _session
                if _server is None:
                    return
                idle = session is None or time.monotonic() - session.last_activity > IDLE_TIMEOUT
            if idle:
                stop()
                return

    _watchdog = threading.Thread(target=watch, daemon=True)
    _watchdog.start()


def add_page(
    session: ScanSession, document: int, data: bytes, hint: scan_image.Quad | None = None
) -> ScanPage:
    if session.imported is not None:
        raise ScanError("Session already imported")
    if len(session.pages) >= MAX_PAGES:
        raise ScanError("Too many pages")
    processed = scan_image.process(data, hint)
    page = ScanPage(id=uuid.uuid4().hex[:12], document=document, page=processed)
    with _lock:
        session.pages.append(page)
    session.touch()
    return page


def remove_page(session: ScanSession, page_id: str) -> bool:
    with _lock:
        page = session.find(page_id)
        if page is None:
            return False
        session.pages.remove(page)
    session.touch()
    return True


def import_documents(session: ScanSession) -> list[int]:
    """One PDF per scanned document, stored then analysed in the background. Idempotent."""
    with _lock:
        if session.imported is not None:
            return session.imported
        documents = session.documents()
        stamp = dt.datetime.now().strftime("%Y-%m-%d %H.%M")
        ids: list[int] = []
        batch = ingest.new_batch("scan")
        with Session(get_engine()) as db:
            for n, pages in enumerate(documents, start=1):
                pdf = scan_image.build_pdf([p.page.image for p in pages])
                suffix = f" ({n})" if len(documents) > 1 else ""
                doc, created = ingest.store(
                    db,
                    pdf,
                    f"{T('filename', stamp=stamp)}{suffix}.pdf",
                    "application/pdf",
                    origin=T("from_phone"),
                    batch=batch,
                )
                if created and doc.id is not None:
                    ids.append(doc.id)
        session.imported = ids
        session.pages.clear()
        session.touch()

    def analyse() -> None:
        # One after the other: the local model handles one document at a time anyway.
        for doc_id in ids:
            ingest.analyze_in_background(doc_id)

    thread = threading.Thread(target=analyse, name="scan-analysis", daemon=True)
    with _lock:
        _analysis_threads.append(thread)
    thread.start()
    return ids


def wait_for_analysis(timeout: float = 90) -> None:
    """Waits for the background analysis of every scanned document imported so far (tests: it
    must not outlive the database it writes to)."""
    with _lock:
        threads, _analysis_threads[:] = list(_analysis_threads), []
    for thread in threads:
        thread.join(timeout)
