"""Rule-based classification and extraction.

Serves as a safety net when the local model is unavailable, and as a baseline for the
evaluation. Everything works on normalized text (lowercase, no accents). The keywords and
patterns below match the content of French documents: they stay in French.
"""

import re
import unicodedata
from datetime import date
from functools import cache
from itertools import islice

from binder import i18n
from binder.models import Category, DocType
from binder.schemas import Extraction

# Generated document titles (user-visible, in the current language).
T = i18n.catalog(
    "rules",
    {
        "untitled": {"en": "Document", "fr": "Document"},
        "with_year": {"en": "{label} {year}", "fr": "{label} {year}"},
        "quote_from": {"en": "Quote from {name}", "fr": "Devis {name}"},
        # Types whose title names the issuer: "EDF invoice" / "Facture EDF".
        "invoice": {"en": "{issuer} invoice", "fr": "Facture {issuer}"},
        "certificate": {"en": "{issuer} certificate", "fr": "Attestation {issuer}"},
        "insurance_certificate": {
            "en": "{issuer} insurance certificate",
            "fr": "Attestation d'assurance {issuer}",
        },
        "contract": {"en": "{issuer} contract", "fr": "Contrat {issuer}"},
        "payment_notice": {"en": "{issuer} payment notice", "fr": "Avis d'échéance {issuer}"},
        "payment_schedule": {"en": "{issuer} payment schedule", "fr": "Échéancier {issuer}"},
        "quote": {"en": "{issuer} quote", "fr": "Devis {issuer}"},
    },
)

# Weight = number of words in the expression: a long expression is more discriminating.
CATEGORY_KEYWORDS: dict[Category, list[str]] = {
    Category.TAXES: [
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
    Category.ENERGY: [
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
    Category.INSURANCE: [
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
    Category.BANK: [
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
    Category.IDENTITY: [
        "carte nationale d'identite",
        "carte d'identite",
        "passeport",
        "permis de conduire",
        "titre de sejour",
        "lieu de naissance",
    ],
    Category.VEHICLE: [
        "controle technique",
        "certificat d'immatriculation",
        "carte grise",
        "immatriculation",
        "vehicule",
        "kilometrage",
    ],
    Category.HOUSING: [
        "quittance de loyer",
        "loyer",
        "bail",
        "locataire",
        "bailleur",
        "charges locatives",
        "syndic",
        "depot de garantie",
    ],
    Category.HEALTH: [
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
    Category.WORK: [
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

# (pattern, type): the first matching pattern gives the document type. Order matters: specific
# types before generic ones ("attestation d'assurance" before "attestation").
DOC_TYPES: list[tuple[str, DocType]] = [
    (r"carte nationale d'identite|carte d'identite", DocType.IDENTITY_CARD),
    (r"passeport", DocType.PASSPORT),
    (r"permis de conduire", DocType.DRIVING_LICENCE),
    (r"titre de sejour", DocType.RESIDENCE_PERMIT),
    (r"controle technique", DocType.ROADWORTHINESS_TEST),
    (r"certificat d'immatriculation|carte grise", DocType.VEHICLE_REGISTRATION),
    (r"releve d'identite bancaire|(?<![a-z])rib(?![a-z])", DocType.BANK_DETAILS),
    (r"contrat de travail", DocType.EMPLOYMENT_CONTRACT),
    (r"contrat de location|(?<![a-z])bail (?:d'habitation|de location)", DocType.LEASE),
    (r"taxe fonciere", DocType.PROPERTY_TAX),
    (r"taxe d'habitation", DocType.HOUSING_TAX),
    (r"avis d'impot|impot sur le revenu", DocType.TAX_NOTICE),
    (r"quittance de loyer", DocType.RENT_RECEIPT),
    (r"avis d'echeance", DocType.PAYMENT_NOTICE),
    (r"attestation d'assurance", DocType.INSURANCE_CERTIFICATE),
    (r"releve (?:de compte|bancaire)", DocType.BANK_STATEMENT),
    (r"bulletin de (?:paie|salaire)|fiche de paie", DocType.PAYSLIP),
    (r"decompte de remboursement", DocType.REIMBURSEMENT_STATEMENT),
    (r"attestation", DocType.CERTIFICATE),
    (r"devis", DocType.QUOTE),
    (r"echeancier", DocType.PAYMENT_SCHEDULE),
    (r"facture", DocType.INVOICE),
    (r"contrat", DocType.CONTRACT),
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

# Expected fields per category: if they are missing, the document goes to review.
REQUIRED_FIELDS: dict[Category, list[str]] = {
    Category.TAXES: ["amount", "due_date"],
    Category.ENERGY: ["amount", "due_date"],
    Category.INSURANCE: ["amount", "due_date"],
    Category.TELECOM: ["amount", "due_date"],
    Category.HOUSING: ["amount"],
    Category.WORK: ["amount"],
    Category.BANK: ["issue_date"],
    Category.HEALTH: ["issue_date"],
    Category.SOCIAL: ["issue_date"],
    Category.IDENTITY: ["expiry_date"],
    Category.VEHICLE: [],
    Category.OTHER: [],
}

# French month names, to read dates written out in documents ("15 octobre 2026").
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


@cache
def _fold(char: str) -> str:
    if char in _SPECIAL:
        return _SPECIAL[char]
    decomposed = unicodedata.normalize("NFKD", char)
    if len(decomposed) > 1 and all(unicodedata.combining(c) for c in decomposed[1:]):
        char = decomposed[0]
    return char.lower()[:1] or char


def normalize(text: str) -> str:
    """Lowercase without accents. Keeps the length so as to map back to the original text."""
    if text.isascii():
        return text.lower()
    return "".join(map(_fold, text))


def _word_re(keyword: str) -> re.Pattern[str]:
    return re.compile(r"(?<![a-z])" + re.escape(keyword) + r"(?![a-z])")


_CATEGORY_RES = {
    category: [(kw, _word_re(kw), len(kw.split())) for kw in keywords]
    for category, keywords in CATEGORY_KEYWORDS.items()
}
_ISSUER_RES = [(key, _word_re(key), name) for key, name in ISSUERS.items()]


def _score_categories(norm: str) -> dict[Category, float]:
    scores: dict[Category, float] = {}
    for category in CATEGORY_KEYWORDS:
        total = 0.0
        for kw, pattern, weight in _CATEGORY_RES[category]:
            # Substring test first: most keywords are absent, and only 3 hits count.
            if kw in norm:
                total += sum(1 for _ in islice(pattern.finditer(norm), 3)) * weight
        if total:
            scores[category] = total
    # "assurance maladie" (national health insurance) must not tip towards home/car insurance.
    if Category.HEALTH in scores and Category.INSURANCE in scores and "assurance maladie" in norm:
        scores[Category.INSURANCE] = max(0.0, scores[Category.INSURANCE] - 2)
    return scores


def classify(norm: str) -> tuple[Category, float]:
    """Returns the category and a confidence between 0 and 1."""
    scores = _score_categories(norm)
    if not scores:
        return Category.OTHER, 0.2
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
        # Date on the same line after the keyword, otherwise on the next line (tables).
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
            # "Facture n° 2026-884512 du 24/09/2026": the reference stops before "du".
            cut = re.search(r"\s+(?:du|le|au|en date)\s", value[1])
            if cut:
                end = start + cut.start()
            return original[start:end].strip().upper()
    return None


# Types whose title names the issuer (message keys of T).
TITLED_WITH_ISSUER = {
    DocType.INVOICE,
    DocType.CERTIFICATE,
    DocType.INSURANCE_CERTIFICATE,
    DocType.CONTRACT,
    DocType.PAYMENT_NOTICE,
    DocType.PAYMENT_SCHEDULE,
    DocType.QUOTE,
}
# Yearly tax documents: the title gives the year.
TITLED_WITH_YEAR = {DocType.PROPERTY_TAX, DocType.HOUSING_TAX, DocType.TAX_NOTICE}


def detect_title(
    norm: str, category: Category, issuer: str | None, year: int | None, first_line: str = ""
) -> str:
    """Title in the current language: "EDF invoice" / "Facture EDF", "Property tax 2026"…"""
    doc_type = detect_doc_type(norm)
    if doc_type is None:
        # Unknown document: its first line (often the issuer's letterhead) says more.
        if category != Category.OTHER:
            return i18n.category_label(category)
        return first_line[:60] or T("untitled")
    if issuer and doc_type in TITLED_WITH_ISSUER:
        return T(doc_type.value, issuer=issuer)
    if doc_type == DocType.QUOTE and first_line and "devis" not in normalize(first_line):
        # Unknown issuer (craftsman, garage): its name usually heads the document.
        return T("quote_from", name=first_line[:50])
    label = i18n.doc_type_label(doc_type)
    if year and doc_type in TITLED_WITH_YEAR:
        return T("with_year", label=label, year=year)
    return label


def detect_issuer(norm: str) -> str | None:
    best: tuple[int, str] | None = None
    for key, pattern, name in _ISSUER_RES:
        m = pattern.search(norm) if key in norm else None
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else None


# Documents without amount or due date, whatever their category.
INFORMATIVE_TYPES = {
    DocType.CERTIFICATE,
    DocType.INSURANCE_CERTIFICATE,
    DocType.BANK_STATEMENT,
    DocType.CONTRACT,
    DocType.EMPLOYMENT_CONTRACT,
    DocType.QUOTE,
    DocType.VEHICLE_REGISTRATION,
    DocType.BANK_DETAILS,
    DocType.LEASE,
}
# Documents whose validity matters: without an end date, they go to review.
EXPIRING_TYPES = {
    DocType.IDENTITY_CARD,
    DocType.PASSPORT,
    DocType.DRIVING_LICENCE,
    DocType.RESIDENCE_PERMIT,
    DocType.ROADWORTHINESS_TEST,
}


def required_fields(category: Category, doc_type: str | None) -> list[str]:
    if doc_type in EXPIRING_TYPES:
        return ["expiry_date"]
    if doc_type in INFORMATIVE_TYPES:
        return ["issue_date"]
    return REQUIRED_FIELDS[category]


def missing_for(category: Category, fields: dict[str, object]) -> list[str]:
    doc_type = fields.get("doc_type")
    required = required_fields(category, doc_type if isinstance(doc_type, str) else None)
    return [f for f in required if fields.get(f) in (None, "")]


def detect_doc_type(norm: str) -> DocType | None:
    return next((doc_type for pattern, doc_type in DOC_TYPES if re.search(pattern, norm)), None)


def extract(text: str) -> Extraction:
    # NFKC undoes typographic ligatures ("ﬁ"), frequent in PDFs.
    text = unicodedata.normalize("NFKC", text)
    norm = normalize(text)
    original_lines = [line for line in text.replace("’", "'").splitlines() if line.strip()]
    lines = [normalize(line) for line in original_lines]

    category, confidence = classify(norm)
    issuer = detect_issuer(norm)
    expiry = _date_after_keyword(lines, EXPIRY_KEYWORDS)
    due = _date_after_keyword(lines, DUE_KEYWORDS)
    if due is not None and due == expiry:
        # "Prochain contrôle à présenter avant le…": an end of validity, not a payment.
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
