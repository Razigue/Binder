"""What Binder knows about the user: the sender of letters, and context for the agent.

The user fills it in Settings, or tells the agent. Binder also completes it by itself from the
documents (the member named on most of them, the address, email and mobile written in them):
only empty fields, and only when the documents agree. Fields Binder filled are marked `auto` and
follow the documents until the user changes them; what the user typed is never overwritten.
"""

from pydantic import BaseModel, Field
from sqlmodel import Session

from binder import i18n
from binder.services import activity, household, settings_store, undo

T = i18n.catalog(
    "profile",
    {
        "learned": {
            "en": "Your details were completed from your documents (Settings)",
            "fr": "Vos coordonnées ont été complétées à partir de vos documents (Réglages)",
        },
        "updated": {
            "en": "Your details were updated",
            "fr": "Vos coordonnées ont été mises à jour",
        },
    },
)

KEY = "profile"
FIELDS = ("name", "address", "city", "email", "phone")
# A detail is trusted when it appears on at least this many documents.
CONFIRMED = 2


class Profile(BaseModel):
    name: str = ""
    address: str = ""
    city: str = ""
    email: str = ""
    phone: str = ""
    # What the agent must know about the user (situation, household, constraints), in their
    # own words: given to the model with every question.
    notes: str = Field(default="", max_length=2000)
    # Fields Binder filled from the documents (it keeps them up to date until the user edits).
    auto: list[str] = []


def load(session: Session) -> Profile:
    return settings_store.load(session, KEY, Profile)


def detected(session: Session) -> dict[str, str]:
    """The user's details as the documents show them."""
    found: dict[str, str] = {}
    main = next((m for m in household.members(session) if len(m.name.split()) >= 2), None)
    if main and main.documents >= CONFIRMED:
        found["name"] = main.name
    home = household.home_address(session, at_least=CONFIRMED)
    if home:
        street, town = home
        found["address"] = f"{street}\n{town}"
        found["city"] = town.split(" ", 1)[-1]
    found.update(household.contact_details(session))
    return found


def learn(session: Session) -> list[str]:
    """Fills the empty fields from the documents and keeps Binder's own ones up to date
    (cleared when the documents no longer show them). Returns the fields changed."""
    profile = load(session)
    found = detected(session)
    changed = []
    for field in FIELDS:
        current = getattr(profile, field)
        if current and field not in profile.auto:
            continue  # the user's own value
        value = found.get(field, "")
        if value == current:
            continue
        setattr(profile, field, value)
        changed.append(field)
        if value and field not in profile.auto:
            profile.auto.append(field)
        elif not value and field in profile.auto:
            profile.auto.remove(field)
    if changed:
        undo.setting_changed(session, KEY)
        settings_store.save(session, KEY, profile)
        if any(getattr(profile, f) for f in changed):
            activity.log(session, "settings", T.msg("learned"))
    return changed


def update(session: Session, values: dict[str, str], *, actor: str = "user") -> Profile:
    """Saves what the user gave (Settings or the agent): those fields become theirs."""
    profile = load(session)
    before = profile.model_copy(deep=True)
    for field, value in values.items():
        if field not in (*FIELDS, "notes"):
            continue
        value = value.strip()
        if field != "notes" and getattr(profile, field) != value and field in profile.auto:
            profile.auto.remove(field)
        setattr(profile, field, value)
    profile = Profile.model_validate(profile.model_dump())
    if profile != before:
        undo.setting_changed(session, KEY)
        settings_store.save(session, KEY, profile)
        activity.log(session, "settings", T.msg("updated"), actor=actor)
    return profile
