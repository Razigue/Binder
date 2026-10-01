"""Phone scans: page outline detection, perspective correction, clean-up and PDF assembly.

Corners are exchanged normalised to the image size (0 to 1), in the order top-left, top-right,
bottom-right, bottom-left, so that the phone can draw them over its viewfinder whatever the
resolution of the frame it sent.
"""

from dataclasses import dataclass

import cv2
import numpy as np
import pymupdf

Quad = list[tuple[float, float]]

# Outline detection works on a reduced image: faster, and paper texture disappears.
WORK_SIZE = 500
# Below this share of the frame, a quadrilateral is not taken for the page.
MIN_AREA = 0.12
MAX_AREA = 0.97
# Long side of a stored page: about 200 dpi for an A4 sheet, plenty for reading and OCR.
PAGE_SIZE = 2400
THUMB_SIZE = 360
JPEG_QUALITY = 85
# Long side of a PDF page, in points (A4: 842).
PDF_LONG_SIDE = 842


class InvalidImage(ValueError):
    pass


@dataclass
class Page:
    image: bytes
    thumb: bytes
    detected: bool


def decode(data: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise InvalidImage("Unreadable image")
    return image


def _order(points: np.ndarray) -> np.ndarray:
    """Four points as top-left, top-right, bottom-right, bottom-left."""
    total = points.sum(axis=1)
    diff = points[:, 1] - points[:, 0]
    return np.array(
        [
            points[np.argmin(total)],
            points[np.argmin(diff)],
            points[np.argmax(total)],
            points[np.argmax(diff)],
        ],
        dtype=np.float32,
    )


def _quadrilateral(mask: np.ndarray, min_area: float) -> np.ndarray | None:
    """Largest convex quadrilateral outlined in a binary image."""
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    hulls = sorted((cv2.convexHull(c) for c in contours), key=cv2.contourArea, reverse=True)
    # The image's own border (a uniform frame thresholded as a whole) is not a page.
    frame = MAX_AREA * mask.shape[0] * mask.shape[1]
    for hull in hulls[:8]:
        area = cv2.contourArea(hull)
        if area > frame:
            continue
        if area < min_area:
            break
        perimeter = cv2.arcLength(hull, True)
        # Rounded or slightly curled corners need a looser approximation.
        for epsilon in (0.02, 0.03, 0.05):
            approx = cv2.approxPolyDP(hull, epsilon * perimeter, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                return _order(approx.reshape(4, 2).astype(np.float32))
    return None


def detect(image: np.ndarray) -> Quad | None:
    """Corners of the page in the image, or None when no clear outline is found."""
    height, width = image.shape[:2]
    scale = min(1.0, WORK_SIZE / max(height, width))
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    # Closing erases the text: only the edge of the sheet remains.
    gray = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    min_area = MIN_AREA * gray.shape[0] * gray.shape[1]

    median = float(np.median(gray))
    edges = cv2.Canny(gray, max(10.0, 0.5 * median), min(255.0, 1.2 * median + 20))
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    quad = _quadrilateral(edges, min_area)
    if quad is None:
        # Light sheet on a darker background with soft edges: brightness separates them.
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        quad = _quadrilateral(mask, min_area)
    if quad is None:
        return None
    size = np.array([small.shape[1], small.shape[0]], dtype=np.float32)
    return [(round(float(x), 4), round(float(y), 4)) for x, y in quad / size]


def valid_quad(quad: Quad) -> bool:
    if len(quad) != 4 or not all(-0.05 <= v <= 1.05 for point in quad for v in point):
        return False
    return bool(cv2.isContourConvex(np.array(quad, dtype=np.float32).reshape(4, 1, 2)))


def warp(image: np.ndarray, quad: Quad) -> np.ndarray:
    """Straightens the page outlined by `quad` into a rectangle."""
    height, width = image.shape[:2]
    corners = np.clip(np.array(quad, dtype=np.float32), 0, 1) * np.array(
        [width, height], dtype=np.float32
    )
    tl, tr, br, bl = corners
    out_w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    out_h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    if out_w < 50 or out_h < 50:
        return image
    target = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], np.float32)
    matrix = cv2.getPerspectiveTransform(corners, target)
    return cv2.warpPerspective(image, matrix, (out_w, out_h), flags=cv2.INTER_CUBIC)


def enhance(image: np.ndarray) -> np.ndarray:
    """Even, white background: divides out the lighting (shadows, phone light falloff)."""
    height, width = image.shape[:2]
    reduced = (max(1, width // 4), max(1, height // 4))
    small = cv2.resize(image, reduced, interpolation=cv2.INTER_AREA)
    # Dilation swallows the strokes, the median smooths what is left: the bare paper.
    kernel = np.ones((5, 5), np.uint8)
    background = cv2.medianBlur(cv2.dilate(small, kernel), 15)
    background = cv2.resize(background, (width, height), interpolation=cv2.INTER_LINEAR)
    flat = cv2.divide(image, background, scale=255)
    # Levels: a light grey paper becomes white, the ink gets deeper.
    lut = np.clip((np.arange(256, dtype=np.float32) - 30) * 255 / (235 - 30), 0, 255)
    return cv2.LUT(flat, lut.astype(np.uint8))


def _resize(image: np.ndarray, long_side: int) -> np.ndarray:
    height, width = image.shape[:2]
    scale = long_side / max(height, width)
    if scale >= 1:
        return image
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def _jpeg(image: np.ndarray, quality: int = JPEG_QUALITY) -> bytes:
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise InvalidImage("Could not encode the page")
    return buffer.tobytes()


def process(data: bytes, hint: Quad | None = None) -> Page:
    """A photo from the phone becomes a page: cropped, straightened and cleaned up.

    `hint` is the outline the viewfinder showed when the photo was taken: used when detection on
    the full photo fails. Without any outline, the whole photo is kept, simply cleaned up.
    """
    image = decode(data)
    quad = detect(image)
    if quad is None and hint is not None and valid_quad(hint):
        quad = hint
    if quad is not None:
        image = warp(image, quad)
    page = enhance(_resize(image, PAGE_SIZE))
    return Page(
        image=_jpeg(page), thumb=_jpeg(_resize(page, THUMB_SIZE), 75), detected=quad is not None
    )


def build_pdf(pages: list[bytes]) -> bytes:
    """One PDF page per JPEG image, sized to the image's proportions."""
    pdf = pymupdf.open()
    for jpeg in pages:
        height, width = decode(jpeg).shape[:2]
        if height >= width:
            size = (PDF_LONG_SIDE * width / height, PDF_LONG_SIDE)
        else:
            size = (PDF_LONG_SIDE, PDF_LONG_SIDE * height / width)
        page = pdf.new_page(width=size[0], height=size[1])
        page.insert_image(page.rect, stream=jpeg)
    data: bytes = pdf.tobytes(garbage=3, deflate=True)
    pdf.close()
    return data
