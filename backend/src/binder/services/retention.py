"""Durées de conservation conseillées (particuliers, France), avec suggestion de tri.

Repères issus de la fiche « Combien de temps conserver ses papiers ? » de service-public.fr ;
en cas de doute, la durée la plus longue est retenue. Binder ne supprime jamais rien de
lui-même : il propose, l'utilisateur met à la corbeille.
"""

from dataclasses import dataclass
from datetime import date

from binder.models import Category, Document


@dataclass(frozen=True)
class Rule:
    label: str
    # Durée en années à partir de la date du document. None : pas de durée fixe.
    years: int | None = None
    # Compter jusqu'au 31 décembre (délai de reprise fiscale).
    end_of_year: bool = False
    # Peut être trié dès qu'une version plus récente le remplace.
    until_replaced: bool = False


FOREVER = Rule("À conserver sans limite")

BY_TYPE: dict[str, Rule] = {
    "Bulletin de paie": Rule("Jusqu'à la liquidation de la retraite"),
    "Contrat": Rule("Toute la durée du contrat, puis 2 ans"),
    "Carte grise": Rule("Tant que vous possédez le véhicule"),
    "Contrôle technique": Rule("Jusqu'au contrôle suivant", until_replaced=True),
    "Carte d'identité": Rule("Tant qu'elle est valide", until_replaced=True),
    "Passeport": Rule("Tant qu'il est valide", until_replaced=True),
    "Permis de conduire": Rule("Tant qu'il est valide", until_replaced=True),
    "Titre de séjour": Rule("Tant qu'il est valide", until_replaced=True),
    # Même remplacée, elle peut prouver la couverture lors d'un sinistre passé.
    "Attestation d'assurance": Rule("2 ans", years=2),
    "Devis": Rule("Sans obligation de conservation"),
}

BY_CATEGORY: dict[Category, Rule] = {
    Category.IMPOTS: Rule("3 ans après l'année d'imposition", years=3, end_of_year=True),
    Category.ENERGIE: Rule("5 ans", years=5),
    Category.TELECOM: Rule("1 an", years=1),
    Category.BANQUE: Rule("5 ans", years=5),
    Category.LOGEMENT: Rule("3 ans", years=3),
    Category.ASSURANCE: Rule("2 ans", years=2),
    Category.SANTE: Rule("2 ans", years=2),
    Category.SOCIAL: Rule("2 ans", years=2),
    Category.TRAVAIL: Rule("Jusqu'à la liquidation de la retraite"),
    Category.IDENTITE: Rule("Tant qu'elle est valide", until_replaced=True),
    Category.VEHICULE: Rule("Tant que vous possédez le véhicule"),
}


def rule_for(doc: Document) -> Rule | None:
    if doc.keep_forever:
        return FOREVER
    return BY_TYPE.get(doc.doc_type or "") or BY_CATEGORY.get(doc.category)


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 février
        return d.replace(year=d.year + years, day=28)


def keep_until(doc: Document) -> date | None:
    rule = rule_for(doc)
    if rule is None or rule.years is None:
        return None
    base = doc.issue_date or doc.due_date or doc.created_at.date()
    if rule.end_of_year:
        return date(base.year + rule.years, 12, 31)
    return _add_years(base, rule.years)


def deletion_reason(doc: Document, today: date | None = None) -> str | None:
    """Pourquoi ce document peut être trié, ou None s'il faut le garder."""
    rule = rule_for(doc)
    if rule is None or doc.keep_forever or doc.deleted_at is not None:
        return None
    today = today or date.today()
    if rule.until_replaced and doc.superseded_by is not None:
        return "Remplacé par une version plus récente"
    end = keep_until(doc)
    if end is not None and end < today:
        return f"Durée de conservation dépassée ({rule.label.lower()})"
    return None
