"""Automatic import routes: watched folder and mailbox settings, run now, changes made."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, col, select

from binder import i18n
from binder.api.common import SessionDep
from binder.models import Activity
from binder.schemas import (
    Changes,
    FolderChoice,
    FolderSettings,
    ImportSettings,
    ImportSettingsIn,
    MailSettings,
)
from binder.services import activity, importers, settings_store

router = APIRouter(prefix="/api")

T = i18n.catalog(
    "api",
    {
        "dir_not_found": {"en": "Folder not found: {path}", "fr": "Dossier introuvable : {path}"},
        "empty_path": {"en": "(empty)", "fr": "(vide)"},
        "no_folder_picker": {
            "en": "No folder dialog available: type the folder path.",
            "fr": "Sélecteur de dossier indisponible : saisissez le chemin du dossier.",
        },
        "mail_incomplete": {
            "en": "Server, username and password are required",
            "fr": "Serveur, identifiant et mot de passe sont nécessaires",
        },
        # Activity log.
        "watch_enabled": {
            "en": "Watched folder enabled on {path}",
            "fr": "Dossier surveillé activé sur {path}",
        },
        "watch_disabled": {"en": "Watched folder disabled", "fr": "Dossier surveillé désactivé"},
        "mail_enabled": {
            "en": "Mailbox import enabled ({user})",
            "fr": "Import depuis la boîte mail activé ({user})",
        },
        "mail_disabled": {
            "en": "Mailbox import disabled",
            "fr": "Import depuis la boîte mail désactivé",
        },
    },
)


def _import_settings(session: Session) -> ImportSettings:
    folder = settings_store.load(session, importers.FOLDER_KEY, importers.FolderConfig)
    mail = settings_store.load(session, importers.MAIL_KEY, importers.MailConfig)
    return ImportSettings(
        folder=FolderSettings(**folder.model_dump()),
        mail=MailSettings(
            **mail.model_dump(exclude={"password"}), password_set=bool(mail.password)
        ),
    )


@router.get("/import/settings")
def get_import_settings(session: SessionDep) -> ImportSettings:
    return _import_settings(session)


@router.put("/import/settings")
def update_import_settings(body: ImportSettingsIn, session: SessionDep) -> ImportSettings:
    changed = False
    if body.folder is not None:
        folder = settings_store.load(session, importers.FOLDER_KEY, importers.FolderConfig)
        path = body.folder.path.strip()
        if body.folder.enabled and not Path(path).expanduser().is_dir():
            raise HTTPException(400, T("dir_not_found", path=path or T("empty_path")))
        changed = (folder.enabled, folder.path) != (body.folder.enabled, path)
        if changed:
            msg = (
                T.msg("watch_enabled", path=path)
                if body.folder.enabled
                else T.msg("watch_disabled")
            )
            activity.log(session, "settings", msg, actor="user")
        folder.enabled, folder.path, folder.last_error = body.folder.enabled, path, None
        settings_store.save(session, importers.FOLDER_KEY, folder)
    if body.mail is not None:
        mail = settings_store.load(session, importers.MAIL_KEY, importers.MailConfig)
        new = body.mail
        if new.enabled and not (new.host and new.user and (new.password or mail.password)):
            raise HTTPException(400, T("mail_incomplete"))
        if (mail.host, mail.user, mail.folder) != (new.host, new.user, new.folder):
            mail.uidvalidity, mail.last_uid = None, 0
        if mail.enabled != new.enabled:
            msg = T.msg("mail_enabled", user=new.user) if new.enabled else T.msg("mail_disabled")
            activity.log(session, "settings", msg, actor="user")
        mail = mail.model_copy(update=new.model_dump(exclude={"password"}))
        if new.password is not None:
            mail.password = new.password
        mail.last_error = None
        settings_store.save(session, importers.MAIL_KEY, mail)
    session.commit()
    if changed:
        importers.folder_changed()
    return _import_settings(session)


@router.post("/import/folder/choose")
def choose_import_folder(session: SessionDep) -> FolderChoice:
    """Browser mode: the system's folder dialog, opened on this machine (loopback only)."""
    current = settings_store.load(session, importers.FOLDER_KEY, importers.FolderConfig)
    try:
        return FolderChoice(path=importers.choose_folder(current.path))
    except importers.NoFolderPicker as e:
        raise HTTPException(501, T("no_folder_picker")) from e


@router.get("/changes")
def changes(session: SessionDep) -> Changes:
    """Latest entry Binder logged on its own (imports, analyses): the interface polls it and
    refreshes when it moves, so documents arriving in the background show up by themselves."""
    latest = session.exec(
        select(Activity.id).where(Activity.actor != "user").order_by(col(Activity.id).desc())
    ).first()
    return Changes(revision=latest or 0)


@router.post("/import/run")
def run_imports(session: SessionDep) -> dict[str, object]:
    """Checks the folder and the mailbox right away (otherwise: every 30 s / 5 min)."""
    return importers.run(session)
