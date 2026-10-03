"""What the user may be entitled to, or must do, without any paper telling them (France).

A newcomer to paperwork does not know what to ask for: the prime d'activité, the housing aid or
the free supplementary health insurance are only paid to those who apply, and a first tax return
or the monthly France Travail update come with no letter. Binder looks at the situation given at
first launch (profile.CHOICES) and at the papers (payslips, lease, what the CAF already sent),
and suggests the few that likely concern the user, each with the official page and its
simulator. It never decides eligibility: amounts and ceilings change every year, the official
simulator answers; Binder only says "worth checking" and stays quiet when the papers show the
user already has it.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from sqlmodel import Session, select

from binder import i18n
from binder.db import in_use
from binder.models import DocType, Document
from binder.services import preferences, profile
from binder.services.areas import Area
from binder.services.portals import Portal, public
from binder.services.rules import normalize

T = i18n.catalog(
    "rights",
    {
        "activity_bonus_title": {
            "en": "Check your right to the prime d'activité",
            "fr": "Vérifiez votre droit à la prime d'activité",
        },
        "activity_bonus_detail": {
            "en": "The CAF tops up modest earnings every month, students and apprentices "
            "included, but only for those who apply. The simulation takes 10 minutes.",
            "fr": "La CAF complète chaque mois les revenus modestes, étudiants et apprentis "
            "compris, mais seulement pour qui en fait la demande. La simulation prend "
            "10 minutes.",
        },
        "activity_bonus_prompt": {
            "en": "Could I be entitled to the prime d'activité? How do I apply?",
            "fr": "Ai-je droit à la prime d'activité ? Comment la demander ?",
        },
        "housing_aid_title": {
            "en": "Check your right to housing aid",
            "fr": "Vérifiez votre droit à l'aide au logement",
        },
        "housing_aid_detail": {
            "en": "Tenants, students included, can get help with the rent from the CAF. Nothing "
            "is paid for the months before the request: apply as soon as you move in.",
            "fr": "Les locataires, étudiants compris, peuvent être aidés pour le loyer par la "
            "CAF. Rien n'est versé pour les mois d'avant la demande : faites-la dès "
            "l'emménagement.",
        },
        "housing_aid_prompt": {
            "en": "Could I get housing aid (APL) for my rent? How do I apply?",
            "fr": "Puis-je toucher l'aide au logement (APL) pour mon loyer ? Comment la demander ?",
        },
        "health_cover_title": {
            "en": "A supplementary health insurance, free or almost",
            "fr": "Une mutuelle gratuite ou presque",
        },
        "health_cover_detail": {
            "en": "With low income, the complémentaire santé solidaire covers what the Assurance "
            "Maladie does not: doctor, glasses, dentist. Check in a few minutes.",
            "fr": "Avec de faibles revenus, la complémentaire santé solidaire rembourse ce que "
            "l'Assurance Maladie ne prend pas : médecin, lunettes, dentiste. Vérifiez en "
            "quelques minutes.",
        },
        "health_cover_prompt": {
            "en": "Could I get the complémentaire santé solidaire? How do I apply?",
            "fr": "Ai-je droit à la complémentaire santé solidaire ? Comment la demander ?",
        },
        "first_return_title": {
            "en": "Your first income tax return",
            "fr": "Votre première déclaration de revenus",
        },
        "first_return_detail": {
            "en": "You earned income in {year}: declare it online on impots.gouv.fr, usually "
            "between mid-April and early June. Even with little income, it gives you the tax "
            "notice that the CAF and landlords ask for.",
            "fr": "Vous avez eu des revenus en {year} : déclarez-les en ligne sur impots.gouv.fr, "
            "en général de mi-avril à début juin. Même avec peu de revenus, elle vous donne "
            "l'avis d'impôt que demandent la CAF et les propriétaires.",
        },
        "first_return_prompt": {
            "en": "It is my first income tax return: how do I do it, step by step?",
            "fr": "C'est ma première déclaration de revenus : comment la faire, étape par étape ?",
        },
        "job_update_title": {
            "en": "Monthly update with France Travail",
            "fr": "Actualisation mensuelle France Travail",
        },
        "job_update_detail": {
            "en": "Before {date:date}: without it, your allowance for the month is not paid "
            "and you may be struck off.",
            "fr": "Avant le {date:date} : sans elle, l'allocation du mois n'est pas versée et "
            "vous risquez la radiation.",
        },
        "job_update_prompt": {
            "en": "How do I do my monthly update with France Travail?",
            "fr": "Comment faire mon actualisation mensuelle France Travail ?",
        },
        "student_grant_title": {
            "en": "Grant and student housing: apply this spring",
            "fr": "Bourse et logement étudiant : demande ce printemps",
        },
        "student_grant_detail": {
            "en": "The Dossier social étudiant for next year (Crous grant and housing) is filed "
            "online in the spring, usually until the end of May. After that, housing is "
            "much harder to get.",
            "fr": "Le dossier social étudiant de l'an prochain (bourse et logement Crous) se "
            "dépose en ligne au printemps, en général jusqu'à fin mai. Après, le logement "
            "devient bien plus difficile à obtenir.",
        },
        "student_grant_prompt": {
            "en": "How do I fill in my Dossier social étudiant (Crous grant and housing)?",
            "fr": "Comment remplir mon dossier social étudiant (bourse et logement Crous) ?",
        },
        "simulate": {"en": "Run the simulation", "fr": "Faire la simulation"},
        "go_to": {"en": "Go to {site}", "fr": "Aller sur {site}"},
        "explain": {"en": "Explain", "fr": "M'expliquer"},
        "not_concerned": {"en": "Not for me", "fr": "Pas concerné"},
        "done": {"en": "Done", "fr": "C'est fait"},
    },
)

COUNTRIES = {"FR"}
# Official pages (service-public.gouv.fr): each explains the right and links the simulator.
ACTIVITY_BONUS_PAGE = "https://www.service-public.gouv.fr/particuliers/vosdroits/F2882"
HOUSING_AID_PAGE = "https://www.service-public.gouv.fr/particuliers/vosdroits/F12006"
HEALTH_COVER_PAGE = "https://www.service-public.gouv.fr/particuliers/vosdroits/F10027"
SERVICE_PUBLIC = "service-public.gouv.fr"
# A payslip this recent means the user works now.
WORKING_WITHIN = timedelta(days=92)
# Net monthly pay above which the prime d'activité is not worth suggesting: about 1.5 times the
# net minimum wage, where it ends for a single person (the simulator has the exact figures).
ACTIVITY_BONUS_CEILING = 2100.0
# What the CAF's own papers say when the user already receives it.
ACTIVITY_BONUS_WORDS = ("prime d'activite", "prime d activite")
HOUSING_AID_WORDS = (
    "aide au logement",
    "aide personnalisee au logement",
    " apl ",
    " als ",
    " alf ",
)
# Income tax returns open online in April and close, by département, in early June.
RETURN_OPENS = (4, 1)
RETURN_CLOSES = (6, 10)
# France Travail's monthly update: from the 28th (26th in February) to the 15th.
UPDATE_OPENS = 28
UPDATE_OPENS_FEBRUARY = 26
UPDATE_CLOSES = 15
UPDATE_URGENT = timedelta(days=3)
# The Dossier social étudiant: filed in the spring (1 March to 31 May in 2026).
GRANT_MONTHS = (3, 4, 5)


@dataclass(frozen=True)
class Right:
    key: str
    title: str
    detail: str
    area: Area
    link: Portal
    link_label: str
    prompt: str
    # "done" for a duty (the update), "not_concerned" for a right to check.
    dismiss_label: str
    tone: Literal["urgent", "soon", "info"] = "info"
    when: date | None = None


@dataclass(frozen=True)
class _Papers:
    types: set[str]
    payslips: list[Document]
    caf_text: str


def _papers(session: Session) -> _Papers:
    docs = list(session.exec(select(Document).where(in_use())))
    caf = [
        f"{d.title} {d.text}"
        for d in docs
        if " caf " in f" {' '.join(normalize(d.issuer or '').split())} "
        or d.doc_type == DocType.BENEFIT_DECISION
    ]
    return _Papers(
        types={d.doc_type for d in docs if d.doc_type},
        payslips=sorted(
            (d for d in docs if d.doc_type == DocType.PAYSLIP),
            key=_slip_date,
        ),
        caf_text=f" {' '.join(normalize(' '.join(caf)).split())} ",
    )


def _slip_date(doc: Document) -> date:
    return doc.issue_date or doc.created_at.date()


def _activity_bonus(me: profile.Profile, papers: _Papers, today: date) -> Right | None:
    recent = [d for d in papers.payslips if today - _slip_date(d) <= WORKING_WITHIN]
    if not recent and me.situation != "employee":
        return None
    if me.situation == "retired" or any(w in papers.caf_text for w in ACTIVITY_BONUS_WORDS):
        return None
    pay = recent[-1].amount if recent else None
    if pay is not None and pay > ACTIVITY_BONUS_CEILING:
        return None
    return Right(
        key=f"activity_bonus:{today.year}",
        title=T("activity_bonus_title"),
        detail=T("activity_bonus_detail"),
        area="work",
        link=Portal(name=SERVICE_PUBLIC, url=ACTIVITY_BONUS_PAGE),
        link_label=T("simulate"),
        prompt=T("activity_bonus_prompt"),
        dismiss_label=T("not_concerned"),
    )


def _housing_aid(me: profile.Profile, papers: _Papers, today: date) -> Right | None:
    tenant = me.housing == "tenant" or bool(papers.types & {DocType.LEASE, DocType.RENT_RECEIPT})
    if not tenant or me.housing in ("owner", "hosted"):
        return None
    if any(w in papers.caf_text for w in HOUSING_AID_WORDS):
        return None
    return Right(
        key=f"housing_aid:{today.year}",
        title=T("housing_aid_title"),
        detail=T("housing_aid_detail"),
        area="housing",
        link=Portal(name=SERVICE_PUBLIC, url=HOUSING_AID_PAGE),
        link_label=T("simulate"),
        prompt=T("housing_aid_prompt"),
        dismiss_label=T("not_concerned"),
    )


def _health_cover(me: profile.Profile, papers: _Papers, today: date) -> Right | None:
    if me.situation not in ("student", "job_seeker"):
        return None
    return Right(
        key=f"health_cover:{today.year}",
        title=T("health_cover_title"),
        detail=T("health_cover_detail"),
        area="health",
        link=Portal(name=SERVICE_PUBLIC, url=HEALTH_COVER_PAGE),
        link_label=T("simulate"),
        prompt=T("health_cover_prompt"),
        dismiss_label=T("not_concerned"),
    )


def _first_return(papers: _Papers, today: date) -> Right | None:
    opens, closes = date(today.year, *RETURN_OPENS), date(today.year, *RETURN_CLOSES)
    if not opens <= today <= closes or DocType.TAX_NOTICE in papers.types:
        return None
    if not any(_slip_date(d).year == today.year - 1 for d in papers.payslips):
        return None
    impots = public("impots")
    return Right(
        key=f"first_return:{today.year}",
        title=T("first_return_title"),
        detail=T("first_return_detail", year=today.year - 1),
        area="money",
        link=impots,
        link_label=T("go_to", site=impots.name),
        prompt=T("first_return_prompt"),
        dismiss_label=T("done"),
        tone="soon",
        when=closes,
    )


def update_window(today: date) -> date | None:
    """The deadline of France Travail's monthly update open today, if one is."""
    if today.day <= UPDATE_CLOSES:
        return date(today.year, today.month, UPDATE_CLOSES)
    opens = UPDATE_OPENS_FEBRUARY if today.month == 2 else UPDATE_OPENS
    if today.day < opens:
        return None
    return date(today.year + today.month // 12, today.month % 12 + 1, UPDATE_CLOSES)


def _job_update(me: profile.Profile, today: date) -> Right | None:
    if me.situation != "job_seeker":
        return None
    deadline = update_window(today)
    if deadline is None:
        return None
    france_travail = public("france_travail")
    return Right(
        key=f"job_update:{deadline.isoformat()[:7]}",
        title=T("job_update_title"),
        detail=T("job_update_detail", date=deadline),
        area="work",
        link=france_travail,
        link_label=T("go_to", site=france_travail.name),
        prompt=T("job_update_prompt"),
        dismiss_label=T("done"),
        tone="urgent" if deadline - today < UPDATE_URGENT else "soon",
        when=deadline,
    )


def _student_grant(me: profile.Profile, today: date) -> Right | None:
    if me.situation != "student" or today.month not in GRANT_MONTHS:
        return None
    portal = public("etudiant")
    return Right(
        key=f"student_grant:{today.year}",
        title=T("student_grant_title"),
        detail=T("student_grant_detail"),
        area="family",
        link=portal,
        link_label=T("go_to", site=portal.name),
        prompt=T("student_grant_prompt"),
        dismiss_label=T("done"),
        tone="soon",
        when=date(today.year, GRANT_MONTHS[-1], 31),
    )


def detect(session: Session, today: date | None = None) -> list[Right]:
    today = today or date.today()
    country = preferences.effective(preferences.load(session)).country
    if (country or "").upper() not in COUNTRIES:
        return []
    me = profile.load(session)
    papers = _papers(session)
    found = [
        _job_update(me, today),
        _first_return(papers, today),
        _student_grant(me, today),
        _activity_bonus(me, papers, today),
        _housing_aid(me, papers, today),
        _health_cover(me, papers, today),
    ]
    return [r for r in found if r is not None]
