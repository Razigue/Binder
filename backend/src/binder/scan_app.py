"""Application served to the phone on the local network (see binder.services.scan).

It only knows the scanning page and the pages of the session in progress. Every API call must
carry the session token (`X-Scan-Token` header, or `t` parameter for images).
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from binder.services import scan, scan_image

MOBILE_DIR = Path(__file__).parent / "mobile"
ASSETS = {"scan.js": "text/javascript", "scan.css": "text/css"}
MAX_IMAGE = 20 * 1024 * 1024
# Live frames are small: the phone sends a reduced copy of its viewfinder.
MAX_FRAME = 1024 * 1024

CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; "
    "connect-src 'self'; media-src 'self' blob: mediastream:; manifest-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


class PageOut(BaseModel):
    id: str
    document: int
    detected: bool


class StateOut(BaseModel):
    pages: list[PageOut]
    imported: int | None


class DetectOut(BaseModel):
    quad: list[tuple[float, float]] | None


class FinishOut(BaseModel):
    imported: int


def _session(token: str | None, *, phone: bool = True) -> scan.ScanSession:
    session = scan.check_token(token)
    if session is None:
        raise HTTPException(403, "Session expired")
    session.touch(phone=phone)
    return session


async def _body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length", "")
    if declared and (not declared.isdigit() or int(declared) > limit):
        raise HTTPException(413, "Image too large")
    data = await request.body()
    if not data or len(data) > limit:
        raise HTTPException(413 if data else 400, "Invalid image")
    return data


def _quad(text: str | None) -> scan_image.Quad | None:
    """Normalised corners "x1,y1,x2,y2,x3,y3,x4,y4" → quad, None if absent or malformed."""
    try:
        values = [float(v) for v in (text or "").split(",")]
    except ValueError:
        return None
    if len(values) != 8:
        return None
    return [(values[i], values[i + 1]) for i in range(0, 8, 2)]


def _page_out(page: scan.ScanPage) -> PageOut:
    return PageOut(id=page.id, document=page.document, detected=page.page.detected)


TokenHeader = Annotated[str | None, Header(alias="X-Scan-Token")]


def create_scan_app() -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def harden(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers["Content-Security-Policy"] = CSP
        headers["X-Content-Type-Options"] = "nosniff"
        headers["Referrer-Policy"] = "no-referrer"
        headers["Permissions-Policy"] = "camera=(self)"
        headers["Cache-Control"] = "no-store"
        return response

    @app.get("/", include_in_schema=False)
    def page(t: str | None = None) -> FileResponse:
        # The page itself is harmless; without a valid token it shows an "expired" message.
        return FileResponse(MOBILE_DIR / "index.html", media_type="text/html")

    @app.get("/{name}", include_in_schema=False)
    def asset(name: str) -> FileResponse:
        if name not in ASSETS:
            raise HTTPException(404)
        return FileResponse(MOBILE_DIR / name, media_type=ASSETS[name])

    @app.get("/api/state")
    def state(token: TokenHeader = None) -> StateOut:
        session = _session(token)
        return StateOut(
            pages=[_page_out(p) for p in session.pages],
            imported=len(session.imported) if session.imported is not None else None,
        )

    @app.post("/api/detect")
    async def detect(request: Request, token: TokenHeader = None) -> DetectOut:
        _session(token)
        data = await _body(request, MAX_FRAME)
        try:
            image = await run_in_threadpool(scan_image.decode, data)
            return DetectOut(quad=await run_in_threadpool(scan_image.detect, image))
        except scan_image.InvalidImage as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/pages", status_code=201)
    async def add_page(
        request: Request,
        document: Annotated[int, Query(ge=1, le=999)],
        quad: str | None = None,
        token: TokenHeader = None,
    ) -> PageOut:
        session = _session(token)
        data = await _body(request, MAX_IMAGE)
        try:
            page = await run_in_threadpool(scan.add_page, session, document, data, _quad(quad))
            return _page_out(page)
        except scan_image.InvalidImage as exc:
            raise HTTPException(400, str(exc)) from exc
        except scan.ScanError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/api/pages/{page_id}/thumb")
    def thumb(page_id: str, t: str | None = None) -> Response:
        session = _session(t)
        found = session.find(page_id)
        if found is None:
            raise HTTPException(404)
        return Response(found.page.thumb, media_type="image/jpeg")

    @app.delete("/api/pages/{page_id}", status_code=204)
    def delete_page(page_id: str, token: TokenHeader = None) -> None:
        if not scan.remove_page(_session(token), page_id):
            raise HTTPException(404)

    @app.post("/api/finish")
    def finish(token: TokenHeader = None) -> FinishOut:
        session = _session(token)
        if not session.pages and session.imported is None:
            raise HTTPException(400, "No page")
        return FinishOut(imported=len(scan.import_documents(session)))

    return app
