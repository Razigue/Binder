"""Routes of the folders (checklists), subscriptions and letter templates."""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from binder.api.assistant import folder_status, folder_zip
from binder.api.common import SessionDep
from binder.services import folders, letters, profile, subscriptions

router = APIRouter(prefix="/api")


@router.get("/folders")
def list_folders(session: SessionDep) -> list[folders.FolderStatus]:
    docs = folders.current_documents(session)
    return [folders.evaluate(session, kind, docs=docs) for kind in folders.KINDS.values()]


@router.get("/folders/{key}")
def get_folder(key: str, session: SessionDep) -> folders.FolderStatus:
    return folder_status(session, key)


@router.get("/folders/{key}/export")
def export_folder(key: str, session: SessionDep) -> StreamingResponse:
    """ZIP of the documents found, numbered, with the list of what is still missing."""
    return folder_zip(session, folder_status(session, key))


@router.get("/subscriptions")
def list_subscriptions(session: SessionDep) -> list[subscriptions.Subscription]:
    return subscriptions.detect(session)


# --- Letter templates ----------------------------------------------------------------------


@router.get("/profile")
def get_profile(session: SessionDep) -> profile.Profile:
    return profile.load(session)


@router.put("/profile")
def update_profile(body: profile.Profile, session: SessionDep) -> profile.Profile:
    saved = profile.update(session, body.model_dump(exclude={"auto"}))
    session.commit()
    return saved


@router.get("/letters/kinds")
def letter_kinds() -> dict[str, str]:
    return letters.kind_titles()
