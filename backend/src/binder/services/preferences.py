"""User preferences: interface language, country and theme.

"auto" / None fall back to the operating system (binder.i18n.system_locale). The effective
locale is cached per database engine and installed as the binder.i18n resolver, so every
message rendered by the backend (agent answers, activity log, letters…) follows the user's choice.
"""

from typing import Literal

from pydantic import BaseModel, field_validator
from sqlalchemy import Engine
from sqlmodel import Session

from binder import i18n
from binder.services import settings_store

KEY = "preferences"

LanguageChoice = Literal["auto", "en", "fr"]
ThemeChoice = Literal["system", "light", "dark"]


class Preferences(BaseModel):
    language: LanguageChoice = "auto"
    # ISO 3166-1 alpha-2 code; None: detected from the operating system.
    country: str | None = None
    theme: ThemeChoice = "system"

    @field_validator("country")
    @classmethod
    def _country(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if len(value) != 2 or not value.isalpha():
            raise ValueError("country must be an ISO 3166-1 alpha-2 code")
        return value.upper()


def effective(prefs: Preferences) -> i18n.Locale:
    language, country = i18n.system_locale()
    return i18n.Locale(
        language if prefs.language == "auto" else prefs.language, prefs.country or country
    )


_cache: tuple[Engine, Preferences] | None = None


def load(session: Session) -> Preferences:
    return settings_store.load(session, KEY, Preferences)


def save(session: Session, prefs: Preferences) -> None:
    global _cache
    from binder.db import get_engine

    settings_store.save(session, KEY, prefs)
    _cache = (get_engine(), prefs)


def current() -> Preferences:
    """Saved preferences (cached; reloaded when the database engine changes)."""
    global _cache
    from binder.db import get_engine

    engine = get_engine()
    if _cache is None or _cache[0] is not engine:
        with Session(engine) as session:
            _cache = (engine, load(session))
    return _cache[1]


def _resolve() -> i18n.Locale:
    return effective(current())


i18n.set_resolver(_resolve)
