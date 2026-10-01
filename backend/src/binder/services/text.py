"""Reading a document's text: PyMuPDF for PDFs, OCR for scans and photos.

OCR engines, in order: RapidOCR (a dependency, models bundled in its wheel), then docTR or
Tesseract when installed. Pages are also rendered as images for the vision of the local model.
"""

import io
import logging
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import pymupdf
from PIL import Image, ImageOps

log = logging.getLogger(__name__)

# Below this number of characters, a PDF page is considered scanned.
MIN_TEXT_PER_PAGE = 30
SUPPORTED_MIME = {"application/pdf", "image/jpeg", "image/png"}


@dataclass
class ReadResult:
    text: str
    page_count: int
    ocr_used: bool


def _prepare(image: Image.Image) -> Image.Image:
    """Rotates according to EXIF, converts to greyscale and enlarges small photos."""
    image = ImageOps.exif_transpose(image) or image
    image = image.convert("L")
    if max(image.size) < 1600:
        factor = 1600 / max(image.size)
        image = image.resize((int(image.width * factor), int(image.height * factor)))
    return ImageOps.autocontrast(image)


@lru_cache(maxsize=1)
def _rapidocr() -> Any:
    from rapidocr import RapidOCR

    # Its own logger prints every step at the default "info" level.
    return RapidOCR(params={"Global.log_level": "warning"})


@lru_cache(maxsize=1)
def _doctr_model() -> Any:
    from doctr.models import ocr_predictor

    return ocr_predictor(pretrained=True)


def join_lines(boxes: list[tuple[float, float, float, str]]) -> str:
    """Text fragments (left, top, bottom, text) regrouped into lines of reading order.

    OCR engines return each table cell apart; the rules expect "Total à payer 94,37 €" on one
    line, as in a PDF with text.
    """
    lines: list[tuple[float, float, list[tuple[float, str]]]] = []
    for left, top, bottom, text in sorted(boxes, key=lambda b: (b[1] + b[2]) / 2):
        middle = (top + bottom) / 2
        for i, (line_top, line_bottom, parts) in enumerate(lines):
            if line_top <= middle <= line_bottom:
                parts.append((left, text))
                lines[i] = (min(line_top, top), max(line_bottom, bottom), parts)
                break
        else:
            lines.append((top, bottom, [(left, text)]))
    return "\n".join(" ".join(t for _, t in sorted(parts)) for _, _, parts in lines)


def _rapid(image: Image.Image) -> str:
    import numpy as np

    result = _rapidocr()(np.array(image.convert("RGB")))
    if result.boxes is None:
        return ""
    fragments = [
        (float(box[:, 0].min()), float(box[:, 1].min()), float(box[:, 1].max()), str(text))
        for box, text in zip(result.boxes, result.txts, strict=True)
    ]
    return join_lines(fragments)


def ocr_engine() -> str | None:
    """Name of the OCR engine in use, None when no engine is available."""
    for module, name in (("rapidocr", "RapidOCR"), ("doctr", "docTR")):
        try:
            __import__(module)
            return name
        except ImportError:
            continue
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return "Tesseract"
    except Exception:
        return None


def _doctr(image: Image.Image) -> str:
    import numpy as np

    result = _doctr_model()([np.array(image.convert("RGB"))])
    return str(result.render())


def _tesseract(image: Image.Image) -> str:
    import pytesseract

    return str(pytesseract.image_to_string(image, lang="fra"))


def ocr_image(image: Image.Image) -> str:
    """OCR with RapidOCR, otherwise docTR or Tesseract if installed, otherwise ""."""
    image = _prepare(image)
    for engine in (_rapid, _doctr, _tesseract):
        try:
            return engine(image)
        except ImportError:
            continue
        except Exception:  # pragma: no cover - depends on the local engine
            log.exception("OCR engine %s failed", engine.__name__)
    log.warning("No OCR engine available")
    return ""


def read_document(data: bytes, mime_type: str) -> ReadResult:
    if mime_type == "application/pdf":
        return _read_pdf(data)
    image = Image.open(io.BytesIO(data))
    text = unicodedata.normalize("NFKC", ocr_image(image)).strip()
    return ReadResult(text=text, page_count=1, ocr_used=True)


def _read_pdf(data: bytes) -> ReadResult:
    pages: list[str] = []
    ocr_used = False
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        for page in pdf:
            page_text = page.get_text("text")
            if len(page_text.strip()) < MIN_TEXT_PER_PAGE:
                pix = page.get_pixmap(dpi=200)
                ocr_text = ocr_image(Image.open(io.BytesIO(pix.tobytes("png"))))
                if ocr_text.strip():
                    page_text, ocr_used = ocr_text, True
            pages.append(page_text)
        text = unicodedata.normalize("NFKC", "\n".join(pages)).strip()
        return ReadResult(text=text, page_count=len(pdf), ocr_used=ocr_used)


def render_page(data: bytes, mime_type: str, page_number: int = 0, dpi: int = 110) -> bytes:
    """PNG rendering of a page, for the preview in the interface."""
    filetype = "pdf" if mime_type == "application/pdf" else mime_type.split("/")[-1]
    with pymupdf.open(stream=data, filetype=filetype) as doc:
        page = doc[max(0, min(page_number, len(doc) - 1))]
        return bytes(page.get_pixmap(dpi=dpi).tobytes("png"))


# Longest side of a page shown to the model: enough to read small print, ~1,000 image tokens.
VISION_SIZE = 1400


def page_image(data: bytes, mime_type: str, page_number: int = 0) -> bytes:
    """A page as a JPEG for the vision of the model (upright, at most VISION_SIZE pixels)."""
    image: Image.Image
    if mime_type == "application/pdf":
        image = Image.open(io.BytesIO(render_page(data, mime_type, page_number, dpi=150)))
    else:
        original = Image.open(io.BytesIO(data))
        image = ImageOps.exif_transpose(original) or original
    image = image.convert("RGB")
    image.thumbnail((VISION_SIZE, VISION_SIZE))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85)
    return out.getvalue()


def page_count(data: bytes, mime_type: str) -> int:
    if mime_type != "application/pdf":
        return 1
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return len(doc)
