"""Checks of an extraction against the text it was read from.

A small model sometimes invents a value, misreads a long number or swaps day and month. Every
amount, date, reference, IBAN and SIRET it gives must be found in the document's text once
normalised (spaces, decimal comma, thousands separators, day-first dates, months in words);
otherwise it is dropped and the document goes to review. Doubts are recorded as codes
("unverified:due_date"), shown with the document until the user validates it.

The confidence of a reading is computed from these checks only, never taken from the model.
"""

import calendar
import re
import unicodedata
from datetime import date, timedelta

from binder.schemas import Extraction
from binder.services.rules import normalize

AMOUNT_FIELDS = ("amount_ht", "amount_tva", "amount_ttc", "amount_due")
DATE_FIELDS = ("issue_date", "due_date", "expiry_date", "period_start", "period_end")
PERIOD_FIELDS = ("period_start", "period_end")
# Fields compared between the rules and the model.
COMPARED_DATES = ("issue_date", "due_date", "expiry_date")
# HT + TVA = TTC, to the cent (rounding on each line of an invoice).
AMOUNT_TOLERANCE = 0.02

# Doubt codes ("code" or "code:field").
UNVERIFIED = "unverified"  # value not found in the text: dropped
OCR_MISMATCH = "ocr_mismatch"  # scan: what the model saw is not in the OCR text: kept
DATE_SWAPPED = "date_swapped"  # found only with day and month swapped: corrected
INVALID = "invalid"  # IBAN or SIRET whose check digits are wrong: dropped
INCONSISTENT_AMOUNTS = "inconsistent_amounts"  # HT + TVA != TTC
IMPLAUSIBLE_DATES = "implausible_dates"
DISAGREEMENT = "disagreement"  # rules and model read a different amount or date
TRANSCRIBED = "transcribed"  # the only text is the model's own transcription: unchecked
TRUNCATED = "truncated"  # too long: the model read the start and the end only
SEVERAL_DOCUMENTS = "several_documents"  # one file, apparently several documents

MONTH_NAMES = {
    # French (normalised: no accents), then English; abbreviations as printed.
    "janvier": 1, "janv": 1, "fevrier": 2, "fevr": 2, "fev": 2, "mars": 3, "avril": 4,
    "avr": 4, "mai": 5, "juin": 6, "juillet": 7, "juil": 7, "aout": 8, "septembre": 9,
    "sept": 9, "octobre": 10, "oct": 10, "novembre": 11, "nov": 11, "decembre": 12, "dec": 12,
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4,
    "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8,
    "september": 9, "sep": 9, "october": 10, "november": 11, "december": 12,
}  # fmt: skip
_MONTHS = "|".join(sorted(MONTH_NAMES, key=len, reverse=True))

# A run of digits with the separators numbers are written with ("1 240,00", "1.240,50").
_NUMBER_RUN = re.compile(r"\d[\d.,' ]*\d|\d")
_DAY_FIRST = re.compile(r"(?<!\d)(\d{1,2}) ?[/.-] ?(\d{1,2}) ?[/.-] ?(\d{4}|\d{2})(?!\d)")
_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_DAY_MONTH = re.compile(rf"(?<![a-z\d])(\d{{1,2}})(?:er|st|nd|rd|th)?\.? ({_MONTHS})\.? (\d{{4}})")
_MONTH_DAY = re.compile(rf"(?<![a-z])({_MONTHS})\.? (\d{{1,2}})(?:st|nd|rd|th)?,? (\d{{4}})")
_MONTH_YEAR = re.compile(rf"(?<![a-z])({_MONTHS})\.? (\d{{4}})(?!\d)")
# "janvier à septembre 2026": the first month takes the year of the second.
_MONTH_RANGE = re.compile(
    rf"(?<![a-z])({_MONTHS})\.? (?:a|au|-|to|until) ({_MONTHS})\.? (\d{{4}})(?!\d)"
)
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_NUMERIC_MONTH = re.compile(r"(?<![\d/.-])(\d{1,2}) ?[/.-] ?(\d{4})(?!\d)")


def _plain(text: str) -> str:
    """Lowercase, no accents, every kind of space as one plain space."""
    text = normalize(unicodedata.normalize("NFKC", text))
    return re.sub(r"[^\S\n]+", " ", text.replace("’", "'"))


def _token_values(token: str) -> set[float]:
    """What a number without spaces may mean: "1.240,50" → 1240.5; "1,240" → 1240 or 1.24."""
    if token.isdigit():
        return {float(token)}
    values: set[float] = set()
    seps = [i for i, c in enumerate(token) if not c.isdigit()]
    last = seps[-1]
    head, tail = token[:last], token[last + 1 :]
    digits = re.sub(r"\D", "", head)
    if not digits or not tail.isdigit():
        return values
    if token[last] in ".," and len(tail) <= 2:
        values.add(float(f"{digits}.{tail}"))
    if len(tail) == 3:
        values.add(float(digits + tail))
    return values


def numbers(text: str) -> set[float]:
    """Every value a number of the text may have, rounded to the cent."""
    found: set[float] = set()
    for run in _NUMBER_RUN.findall(_plain(text)):
        tokens = run.strip(" .,'").split(" ")
        for i, first in enumerate(tokens):
            found |= _token_values(first)
            # "1 240,00": groups of three digits after a space continue the number.
            if not first.isdigit() or len(first) > 3:
                continue
            joined = first
            for nxt in tokens[i + 1 :]:
                if not re.fullmatch(r"\d{3}(?:[.,]\d{1,2})?", nxt):
                    break
                joined += nxt
                found |= _token_values(joined)
                if not nxt.isdigit():
                    break
    return {round(v, 2) for v in found}


def _date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def dates(text: str) -> set[date]:
    """Every full date of the text, numeric dates read day first (15/10/2026)."""
    plain = _plain(text)
    found: list[date | None] = []
    for m in _DAY_FIRST.finditer(plain):
        year = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
        found.append(_date(year, int(m[2]), int(m[1])))
    found += [_date(int(m[1]), int(m[2]), int(m[3])) for m in _ISO.finditer(plain)]
    for m in _DAY_MONTH.finditer(plain):
        found.append(_date(int(m[3]), MONTH_NAMES[m[2]], int(m[1])))
    for m in _MONTH_DAY.finditer(plain):
        found.append(_date(int(m[3]), MONTH_NAMES[m[1]], int(m[2])))
    return {d for d in found if d is not None}


def months(text: str) -> set[tuple[int, int]]:
    """Months named without a day ("septembre 2026", "09/2026"): (year, month)."""
    plain = _plain(text)
    found = {(int(m[2]), MONTH_NAMES[m[1]]) for m in _MONTH_YEAR.finditer(plain)}
    found |= {(int(m[2]), int(m[1])) for m in _NUMERIC_MONTH.finditer(plain) if 0 < int(m[1]) < 13}
    for m in _MONTH_RANGE.finditer(plain):
        found |= {(int(m[3]), MONTH_NAMES[m[1]]), (int(m[3]), MONTH_NAMES[m[2]])}
    return found


def years(text: str) -> set[int]:
    """Years written in the text ("charges 2025", "année scolaire 2026-2027")."""
    return {int(y) for y in _YEAR.findall(_plain(text))}


def compact(value: str) -> str:
    """Letters and digits only, uppercase: "FR76 3000 6000" → "FR7630006000"."""
    return re.sub(r"[^A-Z0-9]", "", _plain(value).upper())


def iban_valid(value: str) -> bool:
    """ISO 13616 check digits (mod 97)."""
    iban = compact(value)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    digits = "".join(str(int(c, 36)) for c in iban[4:] + iban[:4])
    return int(digits) % 97 == 1


def siret_valid(value: str) -> bool:
    """14 digits with a Luhn key (La Poste's establishments use a sum of digits instead)."""
    siret = compact(value)
    if not re.fullmatch(r"\d{14}", siret):
        return False
    if siret.startswith("356000000"):
        return sum(map(int, siret)) % 5 == 0
    total = 0
    for i, c in enumerate(reversed(siret)):
        n = int(c) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def _swapped(d: date) -> date | None:
    return _date(d.year, d.day, d.month) if d.day <= 12 and d.day != d.month else None


def _period_written(
    field: str, d: date, named: set[tuple[int, int]], written_years: set[int]
) -> bool:
    """A period given as months or years ("septembre 2026", "charges 2025", "2026-2027")
    starts on the first day of a month and ends on the last: its month, or failing that its
    year, must be written."""
    boundary = 1 if field == "period_start" else calendar.monthrange(d.year, d.month)[1]
    if d.day != boundary:
        return False
    return (d.year, d.month) in named or d.year in written_years


def check(ext: Extraction, text: str, *, scanned: bool = False) -> list[str]:
    """Checks the values of `ext` against `text`, correcting `ext` in place; returns the doubts
    (consistency() checks the final reading, once merged).

    `scanned`: the model also saw the page images and the text comes from OCR, which may have
    misread a figure: a value not found is kept (the model may be right) but flagged."""
    doubts: list[str] = []

    def not_found(field: str) -> None:
        if scanned:
            doubts.append(f"{OCR_MISMATCH}:{field}")
        else:
            setattr(ext, field, None)
            doubts.append(f"{UNVERIFIED}:{field}")

    found_numbers = numbers(text)
    # Without a breakdown (rules), the main amount is checked itself.
    breakdown = any(getattr(ext, f) is not None for f in AMOUNT_FIELDS)
    for field in AMOUNT_FIELDS if breakdown else ("amount",):
        value = getattr(ext, field)
        if value is None:
            continue
        # A sign is not part of these fields: "-423,48" is an amount of 423,48.
        value = round(abs(float(value)), 2)
        setattr(ext, field, value)
        if value not in found_numbers:
            not_found(field)

    found_dates, named, written_years = dates(text), months(text), years(text)
    for field in DATE_FIELDS:
        d = getattr(ext, field)
        if d is None or d in found_dates:
            continue
        if field in PERIOD_FIELDS and _period_written(field, d, named, written_years):
            continue
        swapped = _swapped(d)
        if swapped is not None and swapped in found_dates:
            # Read month first: the document writes it day first.
            setattr(ext, field, swapped)
            doubts.append(f"{DATE_SWAPPED}:{field}")
            continue
        not_found(field)

    body = compact(text)
    for field in ("reference", "iban", "siret"):
        value = getattr(ext, field)
        if not value:
            continue
        if field == "iban" and not iban_valid(value) or field == "siret" and not siret_valid(value):
            setattr(ext, field, None)
            doubts.append(f"{INVALID}:{field}")
        elif compact(value) not in body:
            not_found(field)

    if breakdown:
        ext.amount = main_amount(ext)
    return doubts


def consistency(ext: Extraction, today: date | None = None) -> list[str]:
    """Amounts that do not add up, dates in an impossible order or out of range."""
    doubts = []
    ht, tva, ttc = ext.amount_ht, ext.amount_tva, ext.amount_ttc
    if (
        ht is not None
        and tva is not None
        and ttc is not None
        and abs(ht + tva - ttc) > AMOUNT_TOLERANCE
    ):
        doubts.append(INCONSISTENT_AMOUNTS)
    today = today or date.today()
    earliest, latest = date(1900, 1, 1), today + timedelta(days=365 * 50)
    wrong = [
        f for f in DATE_FIELDS if (d := getattr(ext, f)) is not None and not earliest <= d <= latest
    ]
    issue = ext.issue_date
    if issue is not None and issue > today + timedelta(days=60):
        wrong.append("issue_date")
    for later in ("due_date", "expiry_date"):
        d = getattr(ext, later)
        if issue is not None and d is not None and d < issue:
            wrong.append(later)
    if ext.period_start and ext.period_end and ext.period_end < ext.period_start:
        wrong.append("period_end")
    doubts += [f"{IMPLAUSIBLE_DATES}:{f}" for f in dict.fromkeys(wrong)]
    return doubts


def main_amount(ext: Extraction) -> float | None:
    """The document's main figure: what is left to pay or received, else its total."""
    for field in ("amount_due", "amount_ttc", "amount_ht"):
        value = getattr(ext, field)
        if value is not None:
            return float(value)
    return None


def disagreements(by_rules: Extraction, by_llm: Extraction) -> list[str]:
    """Amounts and dates the rules and the model both read, differently: the main amount
    (a fine of 135 € the model reads as its 90 € early-payment rate) and each date."""
    doubts = []
    rules_amount, model_amount = by_rules.amount, by_llm.amount
    if (
        rules_amount is not None
        and model_amount is not None
        and abs(rules_amount - model_amount) > 0.01
    ):
        doubts.append(f"{DISAGREEMENT}:amount")
    for field in COMPARED_DATES:
        a, b = getattr(by_rules, field), getattr(by_llm, field)
        if a is not None and b is not None and a != b:
            doubts.append(f"{DISAGREEMENT}:{field}")
    return doubts


def confidence(doubts: list[str], missing: list[str], *, known_category: bool = True) -> float:
    """Confidence of a reading, from the checks: each doubt or missing field lowers it."""
    score = 1.0 - 0.2 * len(doubts) - 0.15 * len(missing) - (0 if known_category else 0.3)
    return round(min(1.0, max(0.0, score)), 2)
