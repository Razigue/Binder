"""Lecture du texte d'un document : PyMuPDF pour les PDF, OCR pour les scans et photos."""

import io
import logging
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import pymupdf
from PIL import Image, ImageOps

log = logging.getLogger(__name__)

# En dessous de ce nombre de caractères, une page PDF est considérée comme scannée.
MIN_TEXT_PER_PAGE = 30
SUPPORTED_MIME = {"application/pdf", "image/jpeg", "image/png"}


@dataclass
class ReadResult:
    text: str
    page_count: int
    ocr_used: bool


def _prepare(image: Image.Image) -> Image.Image:
    """Redresse selon l'EXIF, passe en niveaux de gris et agrandit les petites photos."""
    image = ImageOps.exif_transpose(image) or image
    image = image.convert("L")
    if max(image.size) < 1600:
        factor = 1600 / max(image.size)
        image = image.resize((int(image.width * factor), int(image.height * factor)))
    return ImageOps.autocontrast(image)


@lru_cache(maxsize=1)
def _doctr_model() -> Any:
    from doctr.models import ocr_predictor

    return ocr_predictor(pretrained=True)


def ocr_image(image: Image.Image) -> str:
    """OCR avec docTR si installé, sinon Tesseract, sinon chaîne vide."""
    image = _prepare(image)
    try:
        import numpy as np

        result = _doctr_model()([np.array(image.convert("RGB"))])
        return str(result.render())
    except ImportError:
        pass
    except Exception:  # pragma: no cover - dépend du modèle local
        log.exception("docTR a échoué")
    try:
        import pytesseract

        return str(pytesseract.image_to_string(image, lang="fra"))
    except Exception:
        log.warning("Aucun moteur OCR disponible (installez l'extra 'ocr' ou tesseract)")
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
    """Rendu PNG d'une page, pour l'aperçu dans l'interface."""
    filetype = "pdf" if mime_type == "application/pdf" else mime_type.split("/")[-1]
    with pymupdf.open(stream=data, filetype=filetype) as doc:
        page = doc[max(0, min(page_number, len(doc) - 1))]
        return bytes(page.get_pixmap(dpi=dpi).tobytes("png"))
