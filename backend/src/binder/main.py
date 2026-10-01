"""FastAPI application: API + built interface (when present)."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session
from starlette.responses import Response

from binder import __version__, guard
from binder.api import assistant
from binder.api import journeys as journeys_api
from binder.api import scan as scan_api
from binder.api.routes import router
from binder.config import get_settings
from binder.db import get_engine
from binder.services import areas, background, llm_models, scan, setup

STATIC_DIR = Path(__file__).parent / "static"


class HashedAssets(StaticFiles):
    """Built assets: their name changes with their content, so they never need revalidating."""

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    with Session(get_engine()) as session:
        llm_models.restore(session)
        areas.backfill(session)
    setup.start()
    scheduler = background.Scheduler() if background.enabled() else None
    if scheduler:
        scheduler.start()
    yield
    scan.stop()
    if scheduler:
        scheduler.stop()
    setup.shutdown()


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = FastAPI(title="Binder", version=__version__, lifespan=lifespan)
    # No CORS: the interface (including through the Vite proxy) is served from the same origin.
    app.middleware("http")(guard.middleware(lambda: get_settings().access_token))
    app.include_router(router)
    app.include_router(assistant.router)
    app.include_router(journeys_api.router)
    app.include_router(scan_api.router)

    if (STATIC_DIR / "index.html").exists():
        app.mount("/assets", HashedAssets(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            candidate = STATIC_DIR / path
            if path and candidate.is_file() and STATIC_DIR in candidate.resolve().parents:
                return FileResponse(candidate)
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
