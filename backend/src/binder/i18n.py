"""Internationalisation: system locale detection, message catalogs and value formatting.

The user-facing language is English or French. Each module declares its own messages with
`catalog()`; keys are registered globally under the module's namespace so that a message stored
now (activity log) can be rendered later, in whatever language is current at that time.

Template placeholders accept a few format specs on top of Python's own:
`{x:money}`, `{x:date}`, `{x:category}`, `{x:doc_type}`, `{x:field}` and `{x:value:<field>}`
(a field value displayed according to the field's kind). Dates may be `date` objects or
ISO strings, so that parameters survive a JSON round trip.
"""

import contextlib
import locale
import os
import re
import string
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Literal, get_args

Language = Literal["en", "fr"]
LANGUAGES: tuple[Language, ...] = get_args(Language)
DEFAULT_LANGUAGE: Language = "en"

LANGUAGE_NAMES: dict[Language, dict[Language, str]] = {
    "en": {"en": "English", "fr": "French"},
    "fr": {"en": "anglais", "fr": "français"},
}

# Countries whose administrations write in French: letters to them are written in French.
FRENCH_SPEAKING_COUNTRIES = {"FR", "BE", "LU", "MC"}

_EURO = {
    "AD", "AT", "BE", "CY", "DE", "EE", "ES", "FI", "FR", "GF", "GP", "GR", "HR", "IE", "IT",
    "LT", "LU", "LV", "MC", "ME", "MQ", "MT", "NL", "PM", "PT", "RE", "SI", "SK", "SM", "VA", "YT",
}  # fmt: skip
CURRENCIES: dict[str, str] = {
    **dict.fromkeys(_EURO, "EUR"),
    "AU": "AUD", "BR": "BRL", "CA": "CAD", "CH": "CHF", "CN": "CNY", "CZ": "CZK", "DK": "DKK",
    "DZ": "DZD", "GB": "GBP", "HU": "HUF", "IN": "INR", "JP": "JPY", "LI": "CHF", "MA": "MAD",
    "MX": "MXN", "NO": "NOK", "NZ": "NZD", "PL": "PLN", "RO": "RON", "SE": "SEK", "SN": "XOF",
    "CI": "XOF", "TN": "TND", "US": "USD",
}  # fmt: skip
DEFAULT_CURRENCY = "EUR"
SYMBOLS = {
    "EUR": "€", "USD": "$", "GBP": "£", "CAD": "$", "AUD": "$", "NZD": "$", "JPY": "¥",
    "CNY": "¥", "INR": "₹", "BRL": "R$", "MXN": "$",
}  # fmt: skip


# --- System locale --------------------------------------------------------------------------

_LOCALE = re.compile(r"^([A-Za-z]{2,3})(?:[-_]([A-Za-z]{4}))?(?:[-_]([A-Za-z]{2}))?")


def parse_locale(value: str | None) -> tuple[str | None, str | None]:
    """'fr_FR.UTF-8', 'fr-FR', 'en_US', 'fr' → (language, COUNTRY)."""
    if not value or value in ("C", "POSIX"):
        return None, None
    m = _LOCALE.match(value.strip())
    if not m:
        return None, None
    return m[1].lower(), (m[3].upper() if m[3] else None)


def _windows_locales() -> list[str]:
    # Lets mypy skip the Windows-only `ctypes.windll` when checking on Linux and macOS.
    if sys.platform != "win32":
        return []
    import ctypes

    kernel32 = ctypes.windll.kernel32
    found: list[str] = []
    buf = ctypes.create_unicode_buffer(85)
    # Display language first (what the user reads), then regional format (gives the country).
    if kernel32.LCIDToLocaleName(kernel32.GetUserDefaultUILanguage(), buf, 85, 0):
        found.append(buf.value)
    if kernel32.GetUserDefaultLocaleName(buf, 85):
        found.append(buf.value)
    return found


def _macos_locales() -> list[str]:
    found: list[str] = []
    for key in ("AppleLanguages", "AppleLocale"):
        try:
            out = subprocess.run(
                ["defaults", "read", "-g", key], capture_output=True, text=True, timeout=2
            ).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        first = re.search(r"[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]+)*", out)
        if first:
            found.append(first[0])
    return found


def _posix_locales() -> list[str]:
    found = [os.environ.get(k, "") for k in ("LC_ALL", "LC_MESSAGES", "LANG")]
    found += os.environ.get("LANGUAGE", "").split(":")
    with contextlib.suppress(ValueError):
        found.append(locale.getlocale()[0] or "")
    return [f for f in found if f]


@lru_cache
def system_locale() -> tuple[Language, str | None]:
    """Language and country of the operating system (English if the language is unsupported).

    BINDER_LOCALE (e.g. "fr_FR") overrides detection, for tests and packaged builds.
    """
    from binder.config import get_settings

    override = get_settings().locale
    if override:
        candidates = [override]
    else:
        try:
            if sys.platform == "win32":
                candidates = _windows_locales()
            elif sys.platform == "darwin":
                candidates = _macos_locales()
            else:
                candidates = []
        except Exception:  # detection must never prevent the app from starting
            candidates = []
        candidates += _posix_locales()
    language: Language | None = None
    country: str | None = None
    for candidate in candidates:
        lang, region = parse_locale(candidate)
        if language is None and lang in LANGUAGES:
            language = lang
        country = country or region
    return language or DEFAULT_LANGUAGE, country


# --- Current language -----------------------------------------------------------------------


@dataclass(frozen=True)
class Locale:
    language: Language
    country: str | None

    @property
    def currency(self) -> str:
        return currency_for(self.country)


def _system_resolver() -> Locale:
    return Locale(*system_locale())


# Replaced by binder.services.preferences with the user's saved choice.
_resolver: Callable[[], Locale] = _system_resolver
_override: ContextVar[Language | None] = ContextVar("binder_language", default=None)


def set_resolver(resolver: Callable[[], Locale]) -> None:
    global _resolver
    _resolver = resolver


def current() -> Locale:
    loc = _resolver()
    forced = _override.get()
    return Locale(forced, loc.country) if forced else loc


def current_language() -> Language:
    return current().language


def current_country() -> str | None:
    return current().country


@contextlib.contextmanager
def using(language: Language) -> Iterator[None]:
    """Render messages in `language` within the block (e.g. a letter written in French)."""
    token = _override.set(language)
    try:
        yield
    finally:
        _override.reset(token)


def currency_for(country: str | None) -> str:
    return CURRENCIES.get((country or "").upper(), DEFAULT_CURRENCY)


def language_name(language: Language, in_language: Language = "en") -> str:
    return LANGUAGE_NAMES[in_language][language]


def letter_language(country: str | None, ui_language: Language) -> Language:
    """Language of a letter sent to an administration of `country`."""
    return "fr" if (country or "").upper() in FRENCH_SPEAKING_COUNTRIES else ui_language


# --- Formatting -----------------------------------------------------------------------------

_MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
NBSP = " "  # narrow no-break space, French thousands separator


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def format_date(value: object, language: Language | None = None) -> str:
    """15 Oct 2026 (English) or 15/10/2026 (French)."""
    d = _as_date(value)
    if d is None:
        return "—" if value in (None, "") else str(value)
    if (language or current_language()) == "fr":
        return d.strftime("%d/%m/%Y")
    return f"{d.day} {_MONTHS_EN[d.month - 1]} {d.year}"


def format_money(
    value: float | int | None, language: Language | None = None, currency: str | None = None
) -> str:
    """€1,240.00 (English) or 1 240,00 € (French)."""
    if value is None:
        return "—"
    language = language or current_language()
    currency = currency or current().currency
    symbol = SYMBOLS.get(currency, currency)
    number = f"{float(value):,.2f}"
    if language == "fr":
        number = number.replace(",", NBSP).replace(".", ",")
        return f"{number} {symbol}"
    sign, digits = ("-", number[1:]) if number.startswith("-") else ("", number)
    return f"{sign}{symbol}{digits}" if len(symbol) == 1 else f"{sign}{symbol} {digits}"


# --- Catalogs -------------------------------------------------------------------------------

Messages = dict[str, dict[Language, str]]
_registry: dict[str, dict[Language, str]] = {}


@dataclass(frozen=True)
class Msg:
    """A message to render later: its global key and JSON-serializable parameters."""

    key: str
    params: dict[str, Any] = field(default_factory=dict)

    def render(self, language: Language | None = None) -> str:
        return render(self.key, self.params, language)

    def to_json(self) -> dict[str, Any]:
        return {"key": self.key, "params": self.params}

    def __str__(self) -> str:
        return self.render()


class Catalog:
    """Messages of one namespace. `T("key", **params)` renders in the current language."""

    def __init__(self, namespace: str, messages: Messages) -> None:
        self.namespace = namespace
        for key, texts in messages.items():
            missing = set(LANGUAGES) - texts.keys()
            if missing:
                raise ValueError(f"{namespace}.{key}: missing {sorted(missing)}")
            _registry[f"{namespace}.{key}"] = texts
        self.keys = frozenset(messages)

    def _full(self, key: str) -> str:
        if key not in self.keys:
            raise KeyError(f"{self.namespace}.{key}")
        return f"{self.namespace}.{key}"

    def __call__(self, key: str, /, **params: Any) -> str:
        return render(self._full(key), params)

    def msg(self, key: str, /, **params: Any) -> Msg:
        """Deferred message (stored as key + parameters, rendered when displayed)."""
        return Msg(self._full(key), jsonable(params))

    def plural(self, key: str, count: int, /, **params: Any) -> str:
        """Picks `key_one` or `key_other` according to `count` (also passed as `n`)."""
        return self(_plural_key(key, count, current_language()), n=count, **params)

    def plural_msg(self, key: str, count: int, /, **params: Any) -> Msg:
        """Deferred plural: the form is chosen when rendering, by the display language's rule."""
        self._full(_plural_key(key, count, current_language()))
        return Msg(f"{self.namespace}.{key}", jsonable({"n": count, **params}))

    def get(self, key: str, language: Language | None = None) -> str:
        """Raw template, without formatting (e.g. a label used as data)."""
        return _registry[self._full(key)][language or current_language()]


def catalog(namespace: str, messages: Messages) -> Catalog:
    return Catalog(namespace, messages)


def _plural_key(key: str, count: int, language: Language) -> str:
    # French treats 0 and 1 as singular, English only 1.
    one = count in (0, 1) if language == "fr" else count == 1
    return f"{key}_{'one' if one else 'other'}"


def jsonable(value: Any) -> Any:
    """Message parameters as JSON values (dates as ISO strings, enums as their value)."""
    if isinstance(value, Msg):
        return value.to_json()
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, date | datetime):
        return value.isoformat()
    if hasattr(value, "value") and isinstance(value.value, str):  # StrEnum
        return value.value
    return value


DATE_FIELDS = {"issue_date", "due_date", "expiry_date"}


def format_field_value(name: str, value: object, language: Language | None = None) -> str:
    """A document field value as shown to the user (amount, dates, category, type…)."""
    if value in (None, ""):
        return "—"
    if name == "amount" and isinstance(value, int | float):
        return format_money(value, language)
    if name in DATE_FIELDS:
        return format_date(value, language)
    if name == "category":
        return category_label(str(getattr(value, "value", value)), language)
    if name == "doc_type":
        return doc_type_label(str(getattr(value, "value", value)), language)
    if isinstance(value, float):
        return format_money(value, language)
    if isinstance(value, date):
        return format_date(value, language)
    return str(getattr(value, "value", value))


class _Formatter(string.Formatter):
    def __init__(self, language: Language) -> None:
        self.language = language

    def format_field(self, value: Any, format_spec: str) -> str:
        lang = self.language
        if format_spec == "money":
            return format_money(value, lang)
        if format_spec == "date":
            return format_date(value, lang)
        if format_spec == "category":
            return category_label(value, lang)
        if format_spec == "doc_type":
            return doc_type_label(value, lang)
        if format_spec == "field":
            return field_label(value, lang)
        if format_spec.startswith("value:"):
            return format_field_value(format_spec[6:], value, lang)
        if isinstance(value, dict) and "key" in value and "params" in value:
            return render(str(value["key"]), value["params"], lang)
        return str(super().format_field(value, format_spec))


# Parameters rendered by a function before formatting, by parameter name (e.g. a list of
# field changes in the activity log).
_param_renderers: dict[str, Callable[[Any, Language], str]] = {}


def register_param_renderer(name: str, renderer: Callable[[Any, Language], str]) -> None:
    _param_renderers[name] = renderer


def render(key: str, params: dict[str, Any] | None = None, language: Language | None = None) -> str:
    language = language or current_language()
    texts = _registry.get(key)
    if texts is None and params and isinstance(params.get("n"), int):
        texts = _registry.get(_plural_key(key, params["n"], language))
    if texts is None:
        return key
    values = {
        name: _param_renderers[name](value, language) if name in _param_renderers else value
        for name, value in (params or {}).items()
    }
    return _Formatter(language).format(texts[language], **values)


def is_known(key: str) -> bool:
    return key in _registry or f"{key}_other" in _registry


# --- Shared labels --------------------------------------------------------------------------

CATEGORIES = catalog(
    "category",
    {
        "taxes": {"en": "Taxes", "fr": "Impôts"},
        "energy": {"en": "Energy", "fr": "Énergie"},
        "insurance": {"en": "Insurance", "fr": "Assurance"},
        "bank": {"en": "Bank", "fr": "Banque"},
        "housing": {"en": "Housing", "fr": "Logement"},
        "health": {"en": "Health", "fr": "Santé"},
        "social": {"en": "Social benefits", "fr": "Social"},
        "work": {"en": "Work", "fr": "Travail"},
        "telecom": {"en": "Telecom", "fr": "Télécom"},
        "identity": {"en": "Identity", "fr": "Identité"},
        "vehicle": {"en": "Vehicle", "fr": "Véhicule"},
        "other": {"en": "Other", "fr": "Autre"},
    },
)

DOC_TYPES = catalog(
    "doc_type",
    {
        "identity_card": {"en": "Identity card", "fr": "Carte d'identité"},
        "passport": {"en": "Passport", "fr": "Passeport"},
        "driving_licence": {"en": "Driving licence", "fr": "Permis de conduire"},
        "residence_permit": {"en": "Residence permit", "fr": "Titre de séjour"},
        "roadworthiness_test": {"en": "Roadworthiness test", "fr": "Contrôle technique"},
        "vehicle_registration": {"en": "Vehicle registration", "fr": "Carte grise"},
        "bank_details": {"en": "Bank details (RIB)", "fr": "RIB"},
        "employment_contract": {"en": "Employment contract", "fr": "Contrat de travail"},
        "lease": {"en": "Lease", "fr": "Bail"},
        "property_tax": {"en": "Property tax", "fr": "Taxe foncière"},
        "housing_tax": {"en": "Housing tax", "fr": "Taxe d'habitation"},
        "tax_notice": {"en": "Tax notice", "fr": "Avis d'imposition"},
        "rent_receipt": {"en": "Rent receipt", "fr": "Quittance de loyer"},
        "payment_notice": {"en": "Payment notice", "fr": "Avis d'échéance"},
        "insurance_certificate": {"en": "Insurance certificate", "fr": "Attestation d'assurance"},
        "bank_statement": {"en": "Bank statement", "fr": "Relevé bancaire"},
        "payslip": {"en": "Payslip", "fr": "Bulletin de paie"},
        "reimbursement_statement": {
            "en": "Reimbursement statement",
            "fr": "Décompte de remboursement",
        },
        "certificate": {"en": "Certificate", "fr": "Attestation"},
        "quote": {"en": "Quote", "fr": "Devis"},
        "payment_schedule": {"en": "Payment schedule", "fr": "Échéancier"},
        "invoice": {"en": "Invoice", "fr": "Facture"},
        "contract": {"en": "Contract", "fr": "Contrat"},
    },
)

FIELDS = catalog(
    "field",
    {
        "title": {"en": "title", "fr": "le titre"},
        "category": {"en": "category", "fr": "la catégorie"},
        "issuer": {"en": "issuer", "fr": "l'émetteur"},
        "amount": {"en": "amount", "fr": "le montant"},
        "issue_date": {"en": "issue date", "fr": "la date d'émission"},
        "due_date": {"en": "due date", "fr": "l'échéance"},
        "expiry_date": {"en": "expiry date", "fr": "la date d'expiration"},
        "reference": {"en": "reference", "fr": "la référence"},
        "doc_type": {"en": "document type", "fr": "le type de document"},
    },
)


def category_label(value: str, language: Language | None = None) -> str:
    return CATEGORIES.get(value, language) if value in CATEGORIES.keys else str(value)


def doc_type_label(value: str | None, language: Language | None = None) -> str:
    if not value:
        return "—"
    return DOC_TYPES.get(value, language) if value in DOC_TYPES.keys else value


def field_label(name: str, language: Language | None = None) -> str:
    return FIELDS.get(name, language) if name in FIELDS.keys else name
