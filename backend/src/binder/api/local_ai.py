"""Local AI routes: models overview, choice, upgrade offer, downloads and removal."""

import httpx
from fastapi import APIRouter, HTTPException

from binder import i18n
from binder.api.common import SessionDep
from binder.schemas import ModelChoice, ModelsOverview
from binder.services import llm, llm_models

router = APIRouter(prefix="/api")

T = i18n.catalog(
    "api",
    {
        "ollama_delete_failed": {
            "en": "Ollama could not delete the model ({status})",
            "fr": "Ollama n'a pas pu supprimer le modèle ({status})",
        },
        "ollama_down": {"en": "Ollama is not responding", "fr": "Ollama ne répond pas"},
    },
)


@router.get("/llm")
def llm_overview() -> ModelsOverview:
    return llm_models.overview()


@router.post("/llm/warm", status_code=204)
def warm_model() -> None:
    """Loads the model again if Ollama let it go: called when the chat opens, so the question
    being typed does not wait for it."""
    llm.ensure_loaded()


@router.put("/llm/model")
def choose_model(body: ModelChoice, session: SessionDep) -> ModelsOverview:
    try:
        llm_models.choose(session, body.name)
    except ConnectionError as e:
        raise HTTPException(503, str(e)) from e
    except llm_models.UnknownModel as e:
        raise HTTPException(400, str(e)) from e
    session.commit()
    return llm_models.overview()


@router.post("/llm/upgrade", status_code=202)
def accept_model_upgrade() -> ModelsOverview:
    """Downloads the better model offered; Binder switches to it once it is ready."""
    try:
        llm_models.accept_upgrade()
    except llm_models.UnknownModel as e:
        raise HTTPException(409, str(e)) from e
    return llm_models.overview()


@router.post("/llm/upgrade/decline")
def decline_model_upgrade(session: SessionDep) -> ModelsOverview:
    """Not offered again until the recommendation changes."""
    try:
        llm_models.decline_upgrade(session)
    except llm_models.UnknownModel as e:
        raise HTTPException(409, str(e)) from e
    session.commit()
    return llm_models.overview()


@router.post("/llm/models/{name}/download", status_code=202)
def download_model(name: str) -> ModelsOverview:
    try:
        llm_models.start_download(name)
    except llm_models.UnknownModel as e:
        raise HTTPException(404, str(e)) from e
    return llm_models.overview()


@router.delete("/llm/models/{name}/download", status_code=204)
def cancel_model_download(name: str) -> None:
    llm_models.cancel_download(name)


@router.delete("/llm/models/{name}", status_code=204)
def delete_model(name: str, session: SessionDep) -> None:
    try:
        llm_models.remove(session, name)
    except llm_models.UnknownModel as e:
        raise HTTPException(404, str(e)) from e
    except llm_models.Busy as e:
        raise HTTPException(409, str(e)) from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, T("ollama_delete_failed", status=e.response.status_code)) from e
    except httpx.HTTPError as e:
        raise HTTPException(503, T("ollama_down")) from e
    session.commit()
