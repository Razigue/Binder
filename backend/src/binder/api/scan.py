"""Phone scanning, desktop side: open the session, follow the pages, import or cancel."""

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from binder import i18n
from binder.services import scan

T = i18n.catalog(
    "scan_api",
    {
        "no_session": {"en": "No scan session in progress", "fr": "Aucune numérisation en cours"},
        "no_network": {
            "en": "This computer is not connected to a local network (Wi-Fi or Ethernet).",
            "fr": "Cet ordinateur n'est connecté à aucun réseau local (Wi-Fi ou Ethernet).",
        },
        "server_failed": {
            "en": "Could not open the scanning server: {error}",
            "fr": "Impossible d'ouvrir le serveur de numérisation : {error}",
        },
        "no_page": {"en": "No page to import", "fr": "Aucune page à importer"},
        "page_not_found": {"en": "Page not found", "fr": "Page introuvable"},
    },
)

router = APIRouter(prefix="/api/scan")


class ScanPageOut(BaseModel):
    id: str
    detected: bool


class ScanSessionOut(BaseModel):
    url: str
    qr_code: str
    phone_connected: bool
    documents: list[list[ScanPageOut]]
    imported: list[int] | None


def _out(session: scan.ScanSession) -> ScanSessionOut:
    return ScanSessionOut(
        url=session.url,
        qr_code=session.qr_code(),
        phone_connected=session.phone_connected,
        documents=[
            [ScanPageOut(id=p.id, detected=p.page.detected) for p in pages]
            for pages in session.documents()
        ],
        imported=session.imported,
    )


def _current() -> scan.ScanSession:
    session = scan.current()
    if session is None:
        raise HTTPException(404, T("no_session"))
    return session


@router.post("/session")
def open_session() -> ScanSessionOut:
    try:
        return _out(scan.start())
    except scan.NoNetwork as exc:
        raise HTTPException(503, T("no_network")) from exc
    except (scan.ScanError, OSError) as exc:
        raise HTTPException(503, T("server_failed", error=str(exc))) from exc


@router.get("/session")
def get_session() -> ScanSessionOut:
    session = _current()
    session.touch()
    return _out(session)


@router.delete("/session", status_code=204)
def close_session() -> None:
    scan.stop()


@router.post("/session/import")
def import_session() -> ScanSessionOut:
    session = _current()
    if not session.pages and session.imported is None:
        raise HTTPException(400, T("no_page"))
    scan.import_documents(session)
    return _out(session)


@router.get("/pages/{page_id}/thumb")
def page_thumb(page_id: str) -> Response:
    page = _current().find(page_id)
    if page is None:
        raise HTTPException(404, T("page_not_found"))
    return Response(page.page.thumb, media_type="image/jpeg")


@router.delete("/pages/{page_id}", status_code=204)
def delete_page(page_id: str) -> None:
    if not scan.remove_page(_current(), page_id):
        raise HTTPException(404, T("page_not_found"))
