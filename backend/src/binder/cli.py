"""Entry point: `binder` (server), `binder --desktop` (application) or `binder --seed`."""

import argparse

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


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="binder", description="Binder: local AI administrative agent"
    )
    parser.add_argument("--desktop", action="store_true", help="open in a native window")
    parser.add_argument("--seed", action="store_true", help="import the demo documents")
    args = parser.parse_args()
    if args.seed:
        _seed()
    elif args.desktop:
        from binder import desktop

        desktop.run()
    else:
        _serve()


if __name__ == "__main__":
    main()
