"""Evaluation of the agent on realistic requests, with the demo documents.

uv run python scripts/evaluate_agent.py              # configured Ollama model
uv run python scripts/evaluate_agent.py --rules      # router without a model
uv run python scripts/evaluate_agent.py --think -k reminder   # reasoning on, some scenarios

Each scenario starts from a fresh copy of the same library (16 demo PDFs, plus a photographed
water bill: an image, read by OCR or by the model's vision) and checks what matters: the tools
called, the documents cited, the figures in the answer and the changes made in the database.
"""

import argparse
import os
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from sqlmodel import Session, select

from binder import i18n
from binder.agent import loop
from binder.config import get_settings
from binder.db import get_engine, reset_engine
from binder.models import Category, Deadline, Document
from binder.samples import Sample, build_samples
from binder.schemas import ChatMessage, ChatResponse
from binder.services import ingest, llm
from binder.services.text import render_page

TODAY = date.today()


def d(days: int) -> date:
    return TODAY + timedelta(days=days)


def money(value: float) -> str:
    """An amount as the model may write it: 1240, 1 240, 1,240.00, 1 240,00…"""
    units, cents = f"{value:.2f}".split(".")
    grouped = units if len(units) <= 3 else rf"{units[:-3]}[\s.,]?{units[-3:]}"
    tail = r"(?:[.,]00)?" if cents == "00" else rf"[.,]{cents}"
    return rf"(?<![\d]){grouped}{tail}(?![\d])"


MONTHS = {
    "fr": [
        "janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
        "octobre", "novembre", "décembre",
    ],
    "en": [
        "january", "february", "march", "april", "may", "june", "july", "august", "september",
        "october", "november", "december",
    ],
}  # fmt: skip


def day(value: date) -> str:
    """A date as the model may write it: 6 octobre, October 6, 06/10/2026, 2026-10-06…"""
    names = "|".join(m[value.month - 1] for m in MONTHS.values())
    return (
        rf"(?:\b0?{value.day}(?:er|st|nd|rd|th)?\s+(?:{names})|(?:{names})\s+0?{value.day}\b"
        rf"|\b0?{value.day}[/.]0?{value.month}\b|{value.isoformat()})"
    )


@dataclass
class Scenario:
    name: str
    turns: list[str]
    tools: list[str] = field(default_factory=list)
    # Any of these tools (alternatives, e.g. reading or viewing the page).
    any_tool: list[str] = field(default_factory=list)
    cites: list[str] = field(default_factory=list)
    answer: list[str] = field(default_factory=list)
    forbid: list[str] = field(default_factory=list)
    effect: Callable[[Session, dict[str, int]], bool] | None = None
    letter: str | None = None
    language: str = "fr"


def deadline_done(filename: str) -> Callable[[Session, dict[str, int]], bool]:
    def check(session: Session, ids: dict[str, int]) -> bool:
        rows = session.exec(select(Deadline).where(Deadline.document_id == ids[filename]))
        return any(r.done for r in rows)

    return check


def reminder_on(start: date, end: date) -> Callable[[Session, dict[str, int]], bool]:
    def check(session: Session, ids: dict[str, int]) -> bool:
        rows = session.exec(select(Deadline).where(Deadline.source == "manual"))
        return any(start <= r.due_date <= end for r in rows)

    return check


def document(filename: str, test: Callable[[Document], bool]) -> Callable[..., bool]:
    def check(session: Session, ids: dict[str, int]) -> bool:
        doc = session.get(Document, ids[filename])
        return doc is not None and test(doc)

    return check


def both(*checks: Callable[[Session, dict[str, int]], bool]) -> Callable[..., bool]:
    return lambda session, ids: all(c(session, ids) for c in checks)


SCENARIOS = [
    # Facts held in the fields.
    Scenario(
        "taxe_fonciere",
        ["Combien je dois payer pour la taxe foncière et avant quand ?"],
        cites=["taxe-fonciere.pdf"],
        answer=[money(1240), day(d(5))],
    ),
    Scenario(
        "contrat_maif",
        ["Quel est mon numéro de contrat MAIF ?"],
        cites=["attestation-maif.pdf|maif-echeance.pdf|attestation-maif-ancienne.pdf"],
        answer=[r"4521877"],
    ),
    Scenario(
        "salaire",
        ["Quel est mon dernier salaire net ?"],
        cites=["bulletin-paie.pdf"],
        answer=[money(2134.56)],
    ),
    Scenario(
        "caf",
        ["Combien je touche de la CAF par mois ?"],
        cites=["attestation-caf.pdf"],
        answer=[money(212.45)],
    ),
    Scenario(
        "loyer",
        ["Mon loyer charges comprises, c'est combien ?"],
        cites=["quittance-loyer.pdf"],
        answer=[money(850)],
    ),
    Scenario(
        "cni_expiration",
        ["Ma carte d'identité expire quand ?"],
        cites=["carte-identite.pdf"],
        answer=[day(d(65))],
    ),
    Scenario(
        "controle_technique",
        ["Avant quand dois-je refaire le contrôle technique ?"],
        cites=["controle-technique.pdf"],
        answer=[day(d(570))],
    ),
    Scenario(
        "home_insurance_en",
        ["How much is my home insurance premium, and when is it due?"],
        cites=["maif-echeance.pdf"],
        answer=[money(278), day(d(18)), r"\b(?:the|is|due|premium)\b"],
        language="en",
    ),
    Scenario(
        "bank_balance_en",
        ["What was the balance on my latest bank statement?"],
        cites=["releve-bancaire.pdf"],
        answer=[money(2310.18)],
        language="en",
    ),
    # Facts only in the text.
    Scenario(
        "revenu_fiscal",
        ["Quel est mon revenu fiscal de référence ?"],
        cites=["avis-imposition.pdf"],
        answer=[money(32480)],
    ),
    Scenario(
        "consommation",
        ["Combien de kWh j'ai consommé sur ma dernière facture EDF ?"],
        cites=["facture-edf.pdf"],
        answer=[r"\b312\b"],
    ),
    Scenario(
        "immatriculation",
        ["Quelle est l'immatriculation de ma voiture ?"],
        cites=["controle-technique.pdf"],
        answer=[r"AB-?123-?CD"],
    ),
    Scenario(
        "forfait_mobile",
        ["Combien me coûte le forfait mobile seul chez Orange ?"],
        cites=["facture-orange.pdf"],
        answer=[money(19.99)],
    ),
    # Several documents, arithmetic.
    Scenario(
        "electricite_total",
        ["Combien j'ai payé d'électricité au total sur mes deux dernières factures ?"],
        cites=["facture-edf.pdf", "facture-edf-juillet.pdf"],
        answer=[money(175.42)],
    ),
    Scenario(
        "a_payer_15j",
        ["Qu'est-ce que je dois payer dans les 15 prochains jours ?"],
        tools=["list_deadlines"],
        answer=[r"taxe fonci|1[\s.,]?240"],
    ),
    Scenario(
        "deadlines_october_en",
        ["What do I have to pay in October, and how much in total?"],
        tools=["list_deadlines"],
        answer=[r"\d"],
        language="en",
    ),
    # Understanding and advice.
    Scenario(
        "avis_impot_que_faire",
        ["Qu'est-ce que je dois faire avec mon avis d'impôt sur le revenu ?"],
        cites=["avis-imposition.pdf"],
        answer=[money(1842), r"pay|régl|dû|due"],
    ),
    Scenario(
        "a_verifier",
        ["Quels documents sont à vérifier ?"],
        tools=["documents_to_review"],
    ),
    Scenario(
        "expirations",
        ["Est-ce que j'ai des papiers à renouveler bientôt ?"],
        any_tool=["list_expirations", "list_deadlines"],
        answer=[r"identit"],
    ),
    Scenario(
        "abonnements",
        ["Combien me coûtent mes abonnements par an, et y a-t-il eu des hausses ?"],
        tools=["list_subscriptions"],
        answer=[r"EDF|électricité"],
    ),
    # Nothing can go yet: an insurance certificate is kept 2 years, even once replaced.
    Scenario(
        "tri",
        ["Quels documents je peux jeter ?"],
        tools=["documents_to_sort_out"],
    ),
    Scenario(
        "dossier_location",
        ["Je veux louer un appartement : qu'est-ce qui me manque pour mon dossier ?"],
        tools=["prepare_folder"],
        answer=[r"contrat de travail|bulletins?|quittances?"],
    ),
    # Actions.
    Scenario(
        "rappel_cni",
        ["Rappelle-moi de renouveler ma carte d'identité un mois avant qu'elle expire."],
        tools=["create_reminder"],
        effect=reminder_on(d(65 - 33), d(65 - 27)),
    ),
    Scenario(
        "rappel_simple",
        ["Rappelle-moi de payer la cantine le 12 novembre"],
        tools=["create_reminder"],
        effect=reminder_on(date(TODAY.year, 11, 12), date(TODAY.year, 11, 12)),
    ),
    Scenario(
        "taxe_payee",
        ["J'ai payé la taxe foncière ce matin, marque-la comme réglée."],
        tools=["mark_deadline_paid"],
        effect=deadline_done("taxe-fonciere.pdf"),
    ),
    Scenario(
        "reclasser_devis",
        ["Le devis du garage est rangé dans Autre, mets-le dans Véhicule."],
        tools=["update_document"],
        effect=document("note-garage.pdf", lambda doc: doc.category == Category.VEHICLE),
    ),
    Scenario(
        "corriger_montant",
        ["Le devis du garage est finalement de 165 €, corrige le montant."],
        tools=["update_document"],
        effect=document("note-garage.pdf", lambda doc: doc.amount == 165),
    ),
    Scenario(
        "corbeille",
        ["Mets l'ancienne attestation MAIF, celle de l'an dernier, à la corbeille."],
        tools=["trash_document"],
        effect=both(
            document("attestation-maif-ancienne.pdf", lambda doc: doc.deleted_at is not None),
            document("attestation-maif.pdf", lambda doc: doc.deleted_at is None),
        ),
    ),
    Scenario(
        "resiliation_orange",
        ["Écris-moi une lettre pour résilier mon abonnement Orange."],
        tools=["write_letter"],
        letter="facture-orange.pdf",
    ),
    Scenario(
        "export_impots",
        ["Exporte mon dossier impôts"],
        tools=["export_folder"],
        answer=[r"/api/export\?category=taxes"],
    ),
    # Conversation.
    Scenario(
        "suivi",
        ["Trouve ma facture Orange", "Et elle est prélevée quand ?"],
        cites=["facture-orange.pdf"],
        answer=[day(d(20))],
    ),
    # Scan read by OCR or vision.
    Scenario(
        "facture_eau_photo",
        ["Combien je dois pour l'eau, et pour quand ?"],
        cites=["photo-facture-eau.png"],
        answer=[money(47.82), day(d(9))],
    ),
    Scenario(
        "regarde_page",
        ["Regarde l'image de ma facture d'eau : quel est le volume consommé ?"],
        any_tool=["view_document", "read_document", "search_documents"],
        cites=["photo-facture-eau.png"],
        answer=[r"\b38\b"],
    ),
    # Honesty.
    Scenario(
        "inconnu",
        ["Combien je paie pour Netflix ?"],
        # No amount given for Netflix (other true amounts may be mentioned).
        forbid=[r"Netflix[^.\n]*\d+[.,]\d{2}"],
    ),
]


def water_bill() -> Sample:
    html = f"""<h1>Eau du Grand Lyon</h1><h2>Facture d'eau</h2>
    <p>Facture du {d(-10).strftime("%d/%m/%Y")} — Référence client : EGL-55120</p>
    <table><tr><td>Volume consommé</td><td>38 m³</td></tr>
    <tr><td>Abonnement</td><td>12,40 €</td></tr>
    <tr><td>Montant TTC à payer</td><td class="big">47,82 €</td></tr></table>
    <p>À régler avant le {d(9).strftime("%d/%m/%Y")}</p>"""
    return Sample("photo-facture-eau.png", html, {})


def build_library(directory: Path) -> None:
    """The demo documents, filed with the rules (deterministic), plus a photographed bill."""
    use(directory)
    available = llm.is_available
    llm.is_available = lambda: False  # type: ignore[method-assign]
    try:
        with Session(get_engine()) as session:
            for sample in build_samples(TODAY):
                doc, _ = ingest.store(session, sample.pdf(), sample.filename, "application/pdf")
                ingest.analyze(session, doc)
            photo = water_bill()
            png = render_page(photo.pdf(), "application/pdf", 0, dpi=130)
            doc, _ = ingest.store(session, png, photo.filename, "image/png")
            ingest.analyze(session, doc)
    finally:
        llm.is_available = available  # type: ignore[method-assign]
    reset_engine()


def use(directory: Path, language: str = "fr") -> None:
    os.environ["BINDER_DATA_DIR"] = str(directory)
    # English speaker living in a euro country: French documents, amounts in euros.
    os.environ["BINDER_LOCALE"] = "fr_FR" if language == "fr" else "en_IE"
    get_settings.cache_clear()
    i18n.system_locale.cache_clear()
    reset_engine()


def flat(text: str) -> str:
    return re.sub(r"[  ]", " ", text)


def run(scenario: Scenario, library: Path, rules: bool) -> tuple[list[str], ChatResponse, float]:
    work = Path(tempfile.mkdtemp(prefix="binder-eval-"))
    shutil.copytree(library, work, dirs_exist_ok=True)
    use(work, scenario.language)
    history: list[ChatMessage] = []
    started = time.perf_counter()
    try:
        with Session(get_engine()) as session:
            ids = {doc.filename: doc.id for doc in session.exec(select(Document)) if doc.id}
            for message in scenario.turns:
                if rules:
                    response = loop._run_rules(session, message, [])
                else:
                    response = loop.run(session, message, history, [])
                session.commit()
                history += [
                    ChatMessage(role="user", content=message),
                    ChatMessage(
                        role="assistant",
                        content=response.answer,
                        documents=[doc.id for doc in response.documents],
                    ),
                ]
            elapsed = time.perf_counter() - started
            return check(scenario, response, session, ids), response, elapsed
    finally:
        reset_engine()
        shutil.rmtree(work, ignore_errors=True)


def check(
    scenario: Scenario, response: ChatResponse, session: Session, ids: dict[str, int]
) -> list[str]:
    errors = []
    called = [c.name for c in response.tool_calls]
    errors += [f"tool {t} not called" for t in scenario.tools if t not in called]
    if scenario.any_tool and not set(scenario.any_tool) & set(called):
        errors.append(f"none of {scenario.any_tool} called")
    for names in scenario.cites:
        if not any(ids.get(n) in response.citations for n in names.split("|")):
            errors.append(f"{names} not cited")
    answer = flat(response.answer)
    errors += [f"answer lacks /{p}/" for p in scenario.answer if not re.search(p, answer, re.I)]
    errors += [f"answer has /{p}/" for p in scenario.forbid if re.search(p, answer, re.I)]
    if scenario.effect and not scenario.effect(session, ids):
        errors.append("expected change not made")
    if scenario.letter:
        doc = session.get(Document, ids[scenario.letter])
        if not response.letters or (
            doc and doc.issuer and doc.issuer not in response.letters[0].body
        ):
            errors.append("letter missing or not addressed")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules", action="store_true", help="router without a model")
    parser.add_argument("--think", action="store_true", help="reasoning before each step")
    parser.add_argument("--model", help="Ollama model (default: configured one)")
    parser.add_argument("-k", help="only scenarios whose name contains this")
    parser.add_argument("-v", action="store_true", help="print answers and tool calls")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    os.environ["BINDER_AUTO_IMPORT"] = "false"
    if args.think:
        os.environ["BINDER_LLM_THINK"] = "true"
    if args.model:
        os.environ["BINDER_LLM_MODEL"] = args.model
    get_settings.cache_clear()
    if not args.rules and not llm.is_available():
        raise SystemExit("Model unavailable: check `ollama list` and BINDER_LLM_MODEL")

    library = Path(tempfile.mkdtemp(prefix="binder-library-"))
    build_library(library)
    chosen = [s for s in SCENARIOS if not args.k or args.k in s.name]
    passed, total_time = 0, 0.0
    for scenario in chosen:
        try:
            errors, response, elapsed = run(scenario, library, args.rules)
        except Exception as exc:  # noqa: BLE001 - one broken scenario must not stop the run
            errors, response, elapsed = [f"crash: {exc!r}"], ChatResponse(answer="", engine=""), 0
        total_time += elapsed
        passed += not errors
        tools = " ".join(c.name for c in response.tool_calls)
        if errors or args.v:
            tools = " ".join(f"{c.name}{c.arguments}" for c in response.tool_calls)
        print(f"{'✓' if not errors else '✗'} {scenario.name:22} {elapsed:5.1f}s  {tools}")
        for error in errors:
            print(f"      {error}")
        if args.v or errors:
            print(f"      → {flat(response.answer)[:400]}")
    shutil.rmtree(library, ignore_errors=True)
    engine = "rules" if args.rules else f"{llm.model()}{' + think' if args.think else ''}"
    print(
        f"\n{passed}/{len(chosen)} scenarios passed ({passed / max(1, len(chosen)):.0%}) with "
        f"{engine}, {total_time / max(1, len(chosen)):.1f} s per request on average"
    )


if __name__ == "__main__":
    main()
