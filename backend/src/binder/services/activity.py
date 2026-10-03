"""Activity log: every action by Binder or the user, in plain language.

Entries are added to the session without committing: they leave with the transaction of the
action they describe (or disappear with it on failure).

The summary is an i18n message (key + parameters) stored in `details["msg"]` and rendered in
the current language when displayed; `summary` keeps the text rendered at write time for
entries whose message no longer exists.
"""

import json
from typing import Any, TypedDict

from sqlmodel import Session

from binder import i18n
from binder.models import Activity, Document

T = i18n.catalog(
    "activity",
    {
        "changes": {
            "en": "“{title}” edited ({changes})",
            "fr": "« {title} » modifié ({changes})",
        },
        "change": {
            "en": "{field:field}: {old} → {new}",
            "fr": "{field:field} : {old} → {new}",
        },
        "separator": {"en": "; ", "fr": " ; "},
    },
)


class Change(TypedDict):
    """One edited field, as stored in the parameters of the "changes" message."""

    field: str
    old: Any
    new: Any


def display(value: object) -> str:
    """Readable value: €1,240.00, 15 Oct 2026, "—" when empty (current language)."""
    return i18n.format_field_value("", value)


def log(
    session: Session,
    action: str,
    msg: i18n.Msg,
    *,
    actor: str = "binder",
    document: Document | None = None,
    document_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> Activity:
    entry = Activity(
        actor=actor,
        action=action,
        summary=msg.render(),
        document_id=document.id if document else document_id,
        details=json.dumps(
            {**(details or {}), "msg": msg.to_json()}, ensure_ascii=False, default=str
        ),
    )
    session.add(entry)
    return entry


def summary(entry: Activity, details: dict[str, Any]) -> str:
    """Summary in the current language (stored text for entries without a known message)."""
    msg = details.get("msg")
    if isinstance(msg, dict) and i18n.is_known(str(msg.get("key"))):
        return i18n.render(str(msg["key"]), msg.get("params") or {})
    return entry.summary


def changes_summary(title: str, changes: dict[str, tuple[object, object]]) -> i18n.Msg:
    rows = [
        Change(field=name, old=i18n.jsonable(old), new=i18n.jsonable(new))
        for name, (old, new) in changes.items()
    ]
    return T.msg("changes", title=title, changes=rows)


def _render_changes(changes: list[Change], language: i18n.Language) -> str:
    return T.get("separator", language).join(
        i18n.render(
            "activity.change",
            {
                "field": c["field"],
                "old": i18n.format_field_value(c["field"], c["old"], language),
                "new": i18n.format_field_value(c["field"], c["new"], language),
            },
            language,
        )
        for c in changes
    )


i18n.register_param_renderer("changes", _render_changes)
