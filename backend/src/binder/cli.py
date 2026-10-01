"""Point d'entrée : `binder` (serveur), `binder --desktop` (application) ou `binder --seed`."""

import argparse
import socket
import sys
import threading
import time

import httpx
import uvicorn

from binder.config import get_settings


def _serve() -> None:
    settings = get_settings()
    uvicorn.run("binder.main:app", host=settings.host, port=settings.port, log_level="info")


def _seed() -> None:
    from sqlmodel import Session

    from binder.db import get_engine
    from binder.services import ingest

    with Session(get_engine()) as session:
        for doc, created in ingest.seed_demo(session):
            print(f"{'+' if created else '='} {doc.title} ({doc.category.value})")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def run_desktop() -> None:
    """Application de bureau : serveur interne sur un port libre + fenêtre native.

    Moteur web du système sous Windows (Edge WebView2) et macOS (WebKit), Qt sous Linux.

    Le serveur vit dans un thread du même processus : fermer la fenêtre arrête tout.
    """
    import webview

    from binder.main import app

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(200):
        try:
            httpx.get(f"{url}/api/status", timeout=0.5)
            break
        except httpx.HTTPError:
            time.sleep(0.05)

    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.create_window("Binder", url, width=1320, height=860, min_size=(960, 640))
    webview.start(gui="qt" if sys.platform.startswith("linux") else None, private_mode=False)
    server.should_exit = True


def main() -> None:
    parser = argparse.ArgumentParser(prog="binder", description="Coffre-fort administratif local")
    parser.add_argument("--desktop", action="store_true", help="ouvrir dans une fenêtre native")
    parser.add_argument("--seed", action="store_true", help="importer les documents de démo")
    args = parser.parse_args()
    if args.seed:
        _seed()
    elif args.desktop:
        run_desktop()
    else:
        _serve()


if __name__ == "__main__":
    main()
