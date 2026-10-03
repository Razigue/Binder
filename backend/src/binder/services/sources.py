"""Where each figure comes from: the boxes of the page where the amount, the dates, the reference
or the sender are written, to highlight them on the preview.

PDFs with text are searched directly; scans and photos through the boxes of the text
recognition. The values are searched the way French documents write them ("1 240,00",
"15/10/2026", "15 octobre 2026").
"""

import io
from collections import OrderedDict

import pymupdf
from PIL import Image
from pydantic import BaseModel

from binder.models import Document
from binder.services import learning
from binder.services.missing import MONTH_NAMES
from binder.services.rules import normalize
from binder.services.text import MIN_TEXT_PER_PAGE, ocr_boxes, rendered

FIELDS = ("amount", "due_date", "issue_date", "expiry_date", "reference", "issuer", "person")
# Pages searched: what matters is written up front.
MAX_PAGES = 5


class Box(BaseModel):
    page: int
    x0: float
    y0: float
    x1: float
    y1: float


class FieldSource(BaseModel):
    field: str
    boxes: list[Box]


def variants(doc: Document, field: str) -> list[str]:
    value = getattr(doc, field)
    if value is None or value == "":
        return []
    if field == "amount":
        found = learning.amount_variants(value)
        if float(value).is_integer():
            found += [f"{int(value):,}".replace(",", " "), str(int(value))]
        return found
    if field.endswith("_date"):
        month = MONTH_NAMES["fr"][value.month - 1]
        return [*filter(None, learning.date_variants(value)), f"{value.day} {month} {value.year}"]
    return [str(value)]


def _squash(text: str) -> str:
    return "".join(normalize(text).split())


def _pdf_sources(doc: Document, data: bytes) -> list[FieldSource]:
    found = []
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        pages = list(pdf)[:MAX_PAGES]
        scanned = [len(p.get_text("text").strip()) < MIN_TEXT_PER_PAGE for p in pages]
        ocr: dict[int, list[tuple[float, float, float, float, str]]] = {}
        for field in FIELDS:
            boxes: list[Box] = []
            for needle in variants(doc, field):
                for n, page in enumerate(pages):
                    if scanned[n]:
                        if n not in ocr:
                            ocr[n] = ocr_boxes(rendered(page, 150))
                        boxes += _in_ocr(ocr[n], needle, n)
                        continue
                    width, height = page.rect.width, page.rect.height
                    for r in page.search_for(needle):
                        boxes.append(
                            Box(
                                page=n,
                                x0=r.x0 / width,
                                y0=r.y0 / height,
                                x1=r.x1 / width,
                                y1=r.y1 / height,
                            )
                        )
                if boxes:
                    break
            if boxes:
                found.append(FieldSource(field=field, boxes=boxes[:4]))
    return found


def _in_ocr(
    boxes: list[tuple[float, float, float, float, str]], needle: str, page: int
) -> list[Box]:
    target = _squash(needle)
    return [
        Box(page=page, x0=x0, y0=y0, x1=x1, y1=y1)
        for x0, y0, x1, y1, text in boxes
        if target and target in _squash(text)
    ]


def _image_sources(doc: Document, data: bytes) -> list[FieldSource]:
    boxes = ocr_boxes(Image.open(io.BytesIO(data)))
    found = []
    for field in FIELDS:
        for needle in variants(doc, field):
            hits = _in_ocr(boxes, needle, 0)
            if hits:
                found.append(FieldSource(field=field, boxes=hits[:4]))
                break
    return found


_cache: OrderedDict[tuple[int | None, str], list[FieldSource]] = OrderedDict()
CACHE_SIZE = 32


def locate(doc: Document, data: bytes) -> list[FieldSource]:
    """Boxes of each field found on the pages (cached until the document changes)."""
    key = (doc.id, f"{doc.updated_at.isoformat()}|{doc.sha256}")
    if key not in _cache:
        if doc.mime_type == "application/pdf":
            _cache[key] = _pdf_sources(doc, data)
        else:
            _cache[key] = _image_sources(doc, data)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    _cache.move_to_end(key)
    return _cache[key]
