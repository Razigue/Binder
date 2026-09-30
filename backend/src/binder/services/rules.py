"""Classement et extraction par règles.

Sert de filet de sécurité quand le modèle local n'est pas disponible, et de point de
comparaison pour l'évaluation. Tout est fait sur un texte normalisé (minuscules, sans accents).
"""

import re
import unicodedata
from datetime import date

from binder.models import Category
from binder.schemas import Extraction

# Poids = nombre de mots de l'expression : une expression longue est plus discriminante.
CATEGORY_KEYWORDS: dict[Category, list[str]] = {
    Category.IMPOTS: [
        "avis d'impot",
        "impot sur le revenu",
        "taxe fonciere",
        "taxe d'habitation",
        "finances publiques",
        "impots.gouv",
        "numero fiscal",
        "dgfip",
        "prelevement a la source",
        "revenu fiscal de reference",
    ],
    Category.ENERGIE: [
        "edf",
        "engie",
        "totalenergies",
        "electricite",
        "gaz naturel",
        "kwh",
        "linky",
        "point de livraison",
        "veolia",
        "consommation d'eau",
        "facture d'energie",
    ],
    Category.ASSURANCE: [
        "assurance habitation",
        "assurance auto",
        "contrat d'assurance",
        "assureur",
        "maif",
        "macif",
        "axa",
        "allianz",
        "matmut",
        "groupama",
        "avis d'echeance",
        "cotisation annuelle",
        "sinistre",
        "responsabilite civile",
    ],
    Category.BANQUE: [
        "releve de compte",
        "releve bancaire",
        "iban",
        "bic",
        "solde crediteur",
        "solde debiteur",
        "credit agricole",
        "bnp paribas",
        "societe generale",
        "lcl",
        "boursorama",
        "caisse d'epargne",
        "banque populaire",
        "credit mutuel",
    ],
    Category.IDENTITE: [
        "carte nationale d'identite",
        "carte d'identite",
        "passeport",
        "permis de conduire",
        "titre de sejour",
        "lieu de naissance",
    ],
    Category.VEHICULE: [
        "controle technique",
        "certificat d'immatriculation",
        "carte grise",
        "immatriculation",
        "vehicule",
        "kilometrage",
    ],
    Category.LOGEMENT: [
        "quittance de loyer",
        "loyer",
        "bail",
        "locataire",
        "bailleur",
        "charges locatives",
        "syndic",
        "depot de garantie",
    ],
    Category.SANTE: [
        "assurance maladie",
        "ameli",
        "cpam",
        "mutuelle",
        "ordonnance",
        "remboursement de soins",
        "decompte de remboursement",
        "carte vitale",
    ],
    Category.SOCIAL: [
        "caf",
        "allocations familiales",
        "allocataire",
        "aide au logement",
        "apl",
        "prime d'activite",
        "france travail",
        "pole emploi",
        "urssaf",
        "attestation de paiement",
    ],
    Category.TRAVAIL: [
        "bulletin de paie",
        "bulletin de salaire",
        "fiche de paie",
        "salaire brut",
        "net a payer",
        "employeur",
        "contrat de travail",
        "conges payes",
        "net imposable",
    ],
    Category.TELECOM: [
        "orange",
        "sfr",
        "bouygues telecom",
        "free mobile",
        "freebox",
        "forfait mobile",
        "ligne fixe",
        "abonnement internet",
        "facture mobile",
    ],
}

# (motif, titre) — le premier motif trouvé donne le type de document.
DOC_TYPES: list[tuple[str, str]] = [
    (r"carte nationale d'identite|carte d'identite", "Carte d'identité"),
    (r"passeport", "Passeport"),
    (r"permis de conduire", "Permis de conduire"),
    (r"titre de sejour", "Titre de séjour"),
    (r"controle technique", "Contrôle technique"),
    (r"certificat d'immatriculation|carte grise", "Carte grise"),
    (r"taxe fonciere", "Taxe foncière"),
    (r"taxe d'habitation", "Taxe d'habitation"),
    (r"avis d'impot|impot sur le revenu", "Avis d'imposition"),
    (r"quittance de loyer", "Quittance de loyer"),
    (r"avis d'echeance", "Avis d'échéance"),
    (r"attestation d'assurance", "Attestation d'assurance"),
    (r"releve (?:de compte|bancaire)", "Relevé bancaire"),
    (r"bulletin de (?:paie|salaire)|fiche de paie", "Bulletin de paie"),
    (r"decompte de remboursement", "Décompte de remboursement"),
    (r"attestation", "Attestation"),
    (r"devis", "Devis"),
    (r"echeancier", "Échéancier"),
    (r"facture", "Facture"),
    (r"contrat", "Contrat"),
]

ISSUERS: dict[str, str] = {
    "edf": "EDF",
    "engie": "Engie",
    "totalenergies": "TotalEnergies",
    "veolia": "Veolia",
    "maif": "MAIF",
    "macif": "MACIF",
    "axa": "AXA",
    "allianz": "Allianz",
    "matmut": "Matmut",
    "groupama": "Groupama",
    "caf": "CAF",
    "cpam": "CPAM",
    "ameli": "Assurance Maladie",
    "finances publiques": "DGFiP",
    "dgfip": "DGFiP",
    "orange": "Orange",
    "sfr": "SFR",
    "bouygues telecom": "Bouygues Telecom",
    "free mobile": "Free",
    "freebox": "Free",
    "credit agricole": "Crédit Agricole",
    "bnp paribas": "BNP Paribas",
    "societe generale": "Société Générale",
    "lcl": "LCL",
    "boursorama": "Boursorama",
    "caisse d'epargne": "Caisse d'Épargne",
    "credit mutuel": "Crédit Mutuel",
    "france travail": "France Travail",
    "urssaf": "URSSAF",
    "autosur": "Autosur",
    "dekra": "Dekra",
    "securitest": "Sécuritest",
}

# Champs attendus par catégorie : s'ils manquent, le document part en vérification.
REQUIRED_FIELDS: dict[Category, list[str]] = {
    Category.IMPOTS: ["amount", "due_date"],
    Category.ENERGIE: ["amount", "due_date"],
    Category.ASSURANCE: ["amount", "due_date"],
    Category.TELECOM: ["amount", "due_date"],
    Category.LOGEMENT: ["amount"],
    Category.TRAVAIL: ["amount"],
    Category.BANQUE: ["issue_date"],
    Category.SANTE: ["issue_date"],
    Category.SOCIAL: ["issue_date"],
    Category.IDENTITE: ["expiry_date"],
    Category.VEHICULE: [],
    Category.AUTRE: [],
}

MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}

DUE_KEYWORDS = (
    r"echeance|date limite|avant le|au plus tard|a payer (?:avant|le)|a regler (?:avant|le)"
    r"|preleve le|prelevement (?:le|du|effectue le)|date de prelevement|date d'exigibilite"
    r"|date de paiement|limite de paiement|payable le"
)
EXPIRY_KEYWORDS = (
    r"date d'expiration|expire le|valable jusqu'au|valide jusqu'au|fin de validite"
    r"|prochain controle|a presenter avant le|date limite de validite"
)
ISSUE_KEYWORDS = (
    r"date d'emission|emis le|etabli le|date d'etablissement|date de (?:la )?facture"
    r"|fait le|edite le|date du releve|date :|du \d|delivree? le|date de delivrance"
    r"|date du controle"
)
AMOUNT_KEYWORDS = (
    r"montant|total|a payer|net a payer|somme|reste a payer|solde|cotisation|loyer|ttc|du :"
)
REFERENCE_KEYWORDS = (
    r"reference(?: de l'avis| client| du contrat)?|ref\.?"
    r"|n[°o] (?:de )?(?:contrat|client|allocataire|police|facture)"
    r"|numero (?:de )?(?:contrat|client|fiscal|allocataire|police|facture)"
    r"|(?:facture|contrat|avis) n[°o]|identifiant"
)

_AMOUNT_RE = re.compile(
    r"(?<![\d,.])(\d{1,3}(?:[   .]\d{3})+|\d+)(?:[,.](\d{1,2}))?\s*(?:€|eur\b|euros?\b)"
)
_NUM_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})(?!\d)")
_TEXT_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})(?:er)?\s+(" + "|".join(MONTHS) + r")\s+(\d{4})")
_REF_VALUE_RE = re.compile(r"[:\s]\s*([a-z0-9][a-z0-9\-/ ]{3,30}[a-z0-9])")


_SPECIAL = {"’": "'", " ": " ", " ": " "}


def _fold(char: str) -> str:
    if char in _SPECIAL:
        return _SPECIAL[char]
    decomposed = unicodedata.normalize("NFKD", char)
    if len(decomposed) > 1 and all(unicodedata.combining(c) for c in decomposed[1:]):
        char = decomposed[0]
    return char.lower()[:1] or char


def normalize(text: str) -> str:
    """Minuscules sans accents. Conserve la longueur pour pouvoir revenir au texte d'origine."""
    return "".join(_fold(c) for c in text)


def _score_categories(norm: str) -> dict[Category, float]:
    scores: dict[Category, float] = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        total = 0.0
        for kw in keywords:
            hits = len(re.findall(r"(?<![a-z])" + re.escape(kw) + r"(?![a-z])", norm))
            total += min(hits, 3) * len(kw.split())
        if total:
            scores[category] = total
    # « assurance maladie » ne doit pas faire pencher vers l'assurance habitation/auto.
    if Category.SANTE in scores and Category.ASSURANCE in scores and "assurance maladie" in norm:
        scores[Category.ASSURANCE] = max(0.0, scores[Category.ASSURANCE] - 2)
    return scores


def classify(norm: str) -> tuple[Category, float]:
    """Retourne la catégorie et une confiance entre 0 et 1."""
    scores = _score_categories(norm)
    if not scores:
        return Category.AUTRE, 0.2
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best, best_score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    margin = (best_score - second) / best_score
    strength = min(best_score / 6, 1.0)
    return best, round(0.35 + 0.35 * strength + 0.3 * margin, 2)


def parse_amount(raw_int: str, raw_dec: str | None) -> float:
    digits = re.sub(r"[   .]", "", raw_int)
    return float(f"{digits}.{(raw_dec or '0').ljust(2, '0')}")


def find_dates(line: str) -> list[date]:
    found: list[tuple[int, date]] = []
    for m in _NUM_DATE_RE.finditer(line):
        day, month, year = int(m[1]), int(m[2]), int(m[3])
        year += 2000 if year < 100 else 0
        try:
            found.append((m.start(), date(year, month, day)))
        except ValueError:
            continue
    for m in _TEXT_DATE_RE.finditer(line):
        try:
            found.append((m.start(), date(int(m[3]), MONTHS[m[2]], int(m[1]))))
        except ValueError:
            continue
    return [d for _, d in sorted(found, key=lambda x: x[0])]


def _date_after_keyword(lines: list[str], keywords: str) -> date | None:
    pattern = re.compile(keywords)
    for i, line in enumerate(lines):
        m = pattern.search(line)
        if not m:
            continue
        # Date sur la même ligne après le mot-clé, sinon sur la ligne suivante (tableaux).
        dates = find_dates(line[m.start() :]) or find_dates(" ".join(lines[i + 1 : i + 2]))
        if dates:
            return dates[0]
    return None


def extract_amount(lines: list[str]) -> float | None:
    keyword = re.compile(AMOUNT_KEYWORDS)
    best: tuple[int, float] | None = None
    for i, line in enumerate(lines):
        amounts = [parse_amount(m[1], m[2]) for m in _AMOUNT_RE.finditer(line)]
        if not amounts and i + 1 < len(lines) and keyword.search(line):
            amounts = [parse_amount(m[1], m[2]) for m in _AMOUNT_RE.finditer(lines[i + 1])]
        if not amounts:
            continue
        priority = 0
        if keyword.search(line):
            priority = 2
            if re.search(r"total|a payer|montant (?:du|de votre|a|total)", line):
                priority = 3
        candidate = (priority, max(amounts))
        if best is None or candidate > best:
            best = candidate
    return best[1] if best else None


def extract_reference(lines: list[str], original_lines: list[str]) -> str | None:
    pattern = re.compile(r"(?<![a-z])(?:" + REFERENCE_KEYWORDS + r")")
    for line, original in zip(lines, original_lines, strict=True):
        m = pattern.search(line)
        if not m:
            continue
        value = _REF_VALUE_RE.search(line, m.end())
        if value and any(c.isdigit() for c in value[1]):
            start, end = value.span(1)
            # « Facture n° 2026-884512 du 24/09/2026 » : la référence s'arrête avant « du ».
            cut = re.search(r"\s+(?:du|le|au|en date)\s", value[1])
            if cut:
                end = start + cut.start()
            return original[start:end].strip().upper()
    return None


def detect_title(
    norm: str, category: Category, issuer: str | None, year: int | None, first_line: str = ""
) -> str:
    base = detect_doc_type(norm)
    if base is None:
        # Document inconnu : sa première ligne (souvent l'en-tête de l'émetteur) parle mieux.
        base = category.value if category != Category.AUTRE else first_line[:60] or "Document"
    with_issuer = {
        "Facture",
        "Attestation",
        "Attestation d'assurance",
        "Contrat",
        "Avis d'échéance",
        "Échéancier",
        "Devis",
    }
    if issuer and base in with_issuer:
        base = f"{base} {issuer}"
    elif base == "Devis" and first_line and "devis" not in normalize(first_line):
        # Émetteur inconnu (artisan, garage) : son nom est en général en tête du document.
        base = f"Devis {first_line[:50]}"
    if year and base in {"Taxe foncière", "Taxe d'habitation", "Avis d'imposition"}:
        base = f"{base} {year}"
    return base


def detect_issuer(norm: str) -> str | None:
    best: tuple[int, str] | None = None
    for key, name in ISSUERS.items():
        m = re.search(r"(?<![a-z])" + re.escape(key) + r"(?![a-z])", norm)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else None


# Documents sans montant ni échéance, quelle que soit leur catégorie.
INFORMATIVE_TYPES = ("Attestation", "Relevé bancaire", "Contrat", "Devis", "Carte grise")
# Documents dont la validité compte : sans date de fin, ils partent en vérification.
EXPIRING_TYPES = (
    "Carte d'identité",
    "Passeport",
    "Permis de conduire",
    "Titre de séjour",
    "Contrôle technique",
)


def required_fields(category: Category, doc_type: str | None) -> list[str]:
    if doc_type in EXPIRING_TYPES:
        return ["expiry_date"]
    if doc_type and doc_type.startswith(INFORMATIVE_TYPES):
        return ["issue_date"]
    return REQUIRED_FIELDS[category]


def missing_for(category: Category, fields: dict[str, object]) -> list[str]:
    doc_type = fields.get("doc_type")
    required = required_fields(category, doc_type if isinstance(doc_type, str) else None)
    return [f for f in required if fields.get(f) in (None, "")]


def detect_doc_type(norm: str) -> str | None:
    return next((title for pattern, title in DOC_TYPES if re.search(pattern, norm)), None)


def extract(text: str) -> Extraction:
    # NFKC défait les ligatures typographiques (« ﬁ ») fréquentes dans les PDF.
    text = unicodedata.normalize("NFKC", text)
    norm = normalize(text)
    original_lines = [line for line in text.replace("’", "'").splitlines() if line.strip()]
    lines = [normalize(line) for line in original_lines]

    category, confidence = classify(norm)
    issuer = detect_issuer(norm)
    expiry = _date_after_keyword(lines, EXPIRY_KEYWORDS)
    due = _date_after_keyword(lines, DUE_KEYWORDS)
    if due is not None and due == expiry:
        # « Prochain contrôle à présenter avant le… » : une fin de validité, pas un paiement.
        due = None
    issue = _date_after_keyword(lines, ISSUE_KEYWORDS)
    if issue is None:
        others = [d for line in lines for d in find_dates(line) if d not in (due, expiry)]
        issue = min(others) if others else None
    amount = extract_amount(lines)
    reference = extract_reference(lines, original_lines)
    known = issue or due
    year = known.year if known else None
    doc_type = detect_doc_type(norm)
    fields: dict[str, object] = {
        "doc_type": doc_type,
        "amount": amount,
        "due_date": due,
        "expiry_date": expiry,
        "issue_date": issue,
        "reference": reference,
    }
    missing = missing_for(category, fields)
    if missing:
        confidence = round(confidence * 0.85, 2)

    return Extraction(
        category=category,
        title=detect_title(
            norm, category, issuer, year, original_lines[0].strip() if original_lines else ""
        ),
        issuer=issuer,
        amount=amount,
        issue_date=issue,
        due_date=due,
        expiry_date=expiry,
        reference=reference,
        confidence=confidence,
        missing_fields=missing,
        extractor="rules",
        doc_type=doc_type,
    )
