"""Réglages persistants (base chiffrée), typés par des modèles Pydantic."""

from pydantic import BaseModel
from sqlmodel import Session

from binder.models import Setting


def load[T: BaseModel](session: Session, key: str, model: type[T]) -> T:
    row = session.get(Setting, key)
    return model.model_validate_json(row.value) if row else model()


def save(session: Session, key: str, value: BaseModel) -> None:
    row = session.get(Setting, key) or Setting(key=key)
    row.value = value.model_dump_json()
    session.add(row)
