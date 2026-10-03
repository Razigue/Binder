from collections.abc import Iterator

import cv2
import httpx
import numpy as np
import pymupdf
import pytest
from fastapi.testclient import TestClient

from binder.scan_app import create_scan_app
from binder.services import scan, scan_image

# Corners of the sheet in the synthetic photo, normalised.
SHEET = [(0.36, 0.11), (0.68, 0.17), (0.65, 0.93), (0.32, 0.88)]


def photo(width: int = 1920, height: int = 1080) -> bytes:
    """A light sheet with lines of "text", askew on a darker, noisy table."""
    image = np.full((height, width, 3), (60, 80, 70), np.uint8)
    noise = np.random.default_rng(0).integers(0, 40, image.shape, dtype=np.uint8)
    image = cv2.add(image, noise)
    corners = np.array([(x * width, y * height) for x, y in SHEET], np.int32)
    cv2.fillConvexPoly(image, corners, (235, 235, 240))
    for y in range(int(0.25 * height), int(0.8 * height), 40):
        cv2.line(image, (int(0.4 * width), y), (int(0.6 * width), y + 10), (30, 30, 30), 3)
    ok, buffer = cv2.imencode(".jpg", image)
    assert ok
    return buffer.tobytes()


def blank(width: int = 800, height: int = 600) -> bytes:
    ok, buffer = cv2.imencode(".jpg", np.full((height, width, 3), 128, np.uint8))
    assert ok
    return buffer.tobytes()


# --- Image processing -----------------------------------------------------------------------


def test_detects_the_sheet_corners() -> None:
    quad = scan_image.detect(scan_image.decode(photo()))
    assert quad is not None
    for (x, y), (ex, ey) in zip(quad, SHEET, strict=True):
        assert abs(x - ex) < 0.02 and abs(y - ey) < 0.02


def test_no_outline_on_a_plain_image() -> None:
    assert scan_image.detect(scan_image.decode(blank())) is None


def test_process_straightens_the_page() -> None:
    page = scan_image.process(photo())
    assert page.detected
    height, width = scan_image.decode(page.image).shape[:2]
    # The sheet is taller than wide once straightened (about 0.62 × 0.78 of the photo).
    assert height > width
    assert max(scan_image.decode(page.thumb).shape[:2]) <= scan_image.THUMB_SIZE


def test_process_falls_back_on_the_viewfinder_outline() -> None:
    hint = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
    assert scan_image.process(blank(), hint).detected
    assert not scan_image.process(blank()).detected
    # A crossed outline is not a page.
    crossed = [(0.1, 0.1), (0.9, 0.9), (0.9, 0.1), (0.1, 0.9)]
    assert not scan_image.process(blank(), crossed).detected


def test_unreadable_image() -> None:
    with pytest.raises(scan_image.InvalidImage):
        scan_image.process(b"not an image")


def test_build_pdf_one_page_per_image() -> None:
    pages = [scan_image.process(photo()).image, scan_image.process(blank(1200, 800)).image]
    pdf = pymupdf.open(stream=scan_image.build_pdf(pages))
    assert pdf.page_count == 2
    assert pdf[0].rect.height == scan_image.PDF_LONG_SIDE  # portrait
    assert pdf[1].rect.width == scan_image.PDF_LONG_SIDE  # landscape


# --- Phone application ----------------------------------------------------------------------


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> Iterator[scan.ScanSession]:
    monkeypatch.setattr(scan, "_session", scan.ScanSession(token="secret", url="https://x/"))
    yield scan._session  # type: ignore[misc]
    monkeypatch.setattr(scan, "_session", None)


@pytest.fixture
def phone() -> Iterator[TestClient]:
    with TestClient(create_scan_app(), base_url="https://192.168.1.20:8766") as c:
        yield c


AUTH = {"X-Scan-Token": "secret"}


def test_phone_page_is_served_with_strict_headers(phone: TestClient) -> None:
    r = phone.get("/?t=whatever")
    assert r.status_code == 200 and "scan.js" in r.text
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert phone.get("/scan.js").headers["content-type"].startswith("text/javascript")
    assert phone.get("/secret.txt").status_code == 404


def test_phone_api_requires_the_token(phone: TestClient, session: scan.ScanSession) -> None:
    assert phone.get("/api/state").status_code == 403
    assert phone.get("/api/state", headers={"X-Scan-Token": "wrong"}).status_code == 403
    r = phone.get("/api/state", headers=AUTH)
    assert r.status_code == 200 and r.json() == {"pages": [], "imported": None}
    assert session.phone_connected


def test_phone_api_without_session(phone: TestClient) -> None:
    assert phone.get("/api/state", headers=AUTH).status_code == 403


def test_phone_scans_and_sends_two_documents(
    phone: TestClient, session: scan.ScanSession, client: TestClient
) -> None:
    r = phone.post("/api/detect", content=photo(400, 225), headers=AUTH)
    assert r.status_code == 200 and r.json()["quad"] is not None

    ids = []
    for document in (1, 1, 2):
        r = phone.post(f"/api/pages?document={document}", content=photo(), headers=AUTH)
        assert r.status_code == 201, r.text
        assert r.json()["detected"]
        ids.append(r.json()["id"])
    thumb = phone.get(f"/api/pages/{ids[0]}/thumb?t=secret")
    assert thumb.headers["content-type"] == "image/jpeg"
    assert phone.get(f"/api/pages/{ids[0]}/thumb?t=nope").status_code == 403

    # The computer follows along, and may drop a page.
    seen = client.get("/api/scan/session").json()
    assert [len(d) for d in seen["documents"]] == [2, 1]
    assert client.get(f"/api/scan/pages/{ids[1]}/thumb").status_code == 200
    assert client.delete(f"/api/scan/pages/{ids[1]}").status_code == 204

    r = phone.post("/api/finish", headers=AUTH)
    assert r.json() == {"imported": 2}
    assert phone.get("/api/state", headers=AUTH).json()["imported"] == 2
    # Nothing more can be added to an imported session.
    assert phone.post("/api/pages?document=3", content=photo(), headers=AUTH).status_code == 409

    docs = client.get("/api/documents").json()
    scanned = sorted(d["filename"] for d in docs)
    assert len(scanned) == 2 and all(n.startswith("Scan ") and n.endswith(".pdf") for n in scanned)
    assert {d["page_count"] for d in docs} <= {0, 1}


def test_phone_rejects_bad_uploads(phone: TestClient, session: scan.ScanSession) -> None:
    assert phone.post("/api/pages?document=1", content=b"", headers=AUTH).status_code == 400
    assert phone.post("/api/pages?document=1", content=b"junk", headers=AUTH).status_code == 400
    assert phone.post("/api/pages?document=0", content=photo(), headers=AUTH).status_code == 422
    assert phone.post("/api/finish", headers=AUTH).status_code == 400


# --- Real server ----------------------------------------------------------------------------


def test_session_opens_an_https_server(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setenv("BINDER_SCAN_PORT", "0")
    from binder.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(scan, "lan_address", lambda: "127.0.0.1")
    try:
        r = client.post("/api/scan/session")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["url"].startswith("https://127.0.0.1:")
        assert body["qr_code"].startswith("data:image/svg+xml")
        # Same session while it is open.
        assert client.post("/api/scan/session").json()["url"] == body["url"]

        base, token = body["url"].split("/?t=")
        with httpx.Client(verify=False) as phone_client:
            r = phone_client.get(f"{base}/api/state", headers={"X-Scan-Token": token})
            assert r.status_code == 200
        assert client.get("/api/scan/session").json()["phone_connected"]
        # The certificate is kept for the next session.
        assert scan.certificate("127.0.0.1") == scan.certificate("127.0.0.1")
    finally:
        assert client.delete("/api/scan/session").status_code == 204
    assert client.get("/api/scan/session").status_code == 404
    with pytest.raises(httpx.HTTPError), httpx.Client(verify=False, timeout=1) as c:
        c.get(f"{base}/api/state")


def test_no_network(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    monkeypatch.setattr(scan, "lan_address", lambda: None)
    r = client.post("/api/scan/session")
    assert r.status_code == 503 and "local network" in r.json()["detail"]


def test_phone_rejects_a_malformed_length(phone: TestClient, session: scan.ScanSession) -> None:
    headers = {**AUTH, "Content-Length": "abc"}
    r = phone.post("/api/pages?document=1", content=photo(), headers=headers)
    assert r.status_code in (400, 413)
    accented = {"X-Scan-Token": "é".encode("latin-1")}
    assert phone.get("/api/state", headers=accented).status_code == 403


def test_no_page_lands_in_a_session_imported_meanwhile(
    monkeypatch: pytest.MonkeyPatch, session: scan.ScanSession
) -> None:
    def process(data: bytes, hint: scan_image.Quad | None = None) -> scan_image.Page:
        # The import runs while this photo is being straightened.
        session.imported = []
        return scan_image.Page(image=b"", thumb=b"", detected=False)

    monkeypatch.setattr(scan_image, "process", process)
    with pytest.raises(scan.ScanError):
        scan.add_page(session, 1, b"photo")
    assert session.pages == []
