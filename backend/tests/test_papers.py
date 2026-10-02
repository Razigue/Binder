"""My papers: the state of each area in words, and the administrative year."""

from typing import Any

from fastapi.testclient import TestClient

from binder.services import calendar


def areas(client: TestClient) -> dict[str, dict[str, Any]]:
    return {a["area"]: a for a in client.get("/api/areas").json()}


def test_area_tiles_say_their_state_in_words(client: TestClient) -> None:
    empty = areas(client)
    assert set(empty) == {"housing", "money", "work", "family", "health", "identity", "vehicle"}
    assert all(a["state"] == "Nothing here yet" and a["tone"] == "empty" for a in empty.values())

    client.post("/api/demo")
    state = areas(client)
    # The identity card is due for renewal: the tile says so.
    assert state["identity"]["state"] == "Identity card: renew it"
    assert state["identity"]["tone"] in ("urgent", "soon")
    # A payment says when.
    assert " · Due " in state["money"]["state"]
    # Questions are asked in To do, never on a tile.
    assert all("?" not in a["state"] for a in state.values())
    assert state["health"] == {**state["health"], "state": "Up to date", "tone": "ok"}


def test_administrative_year_for_france_only(client: TestClient) -> None:
    client.put("/api/preferences", json={"language": "auto", "country": "FR", "theme": "system"})
    year = client.get("/api/calendar").json()
    assert [e["month"] for e in year] == sorted(e["month"] for e in year)
    assert {e["key"] for e in year} == {key for _, key, _ in calendar.YEAR}
    assert not any(e["concerns_you"] for e in year)
    client.post("/api/demo")
    concerns = {e["key"] for e in client.get("/api/calendar").json() if e["concerns_you"]}
    assert {"return_opens", "donations"} <= concerns
    assert "property_tax_due" not in concerns
    client.put("/api/preferences", json={"language": "auto", "country": "US", "theme": "system"})
    assert client.get("/api/calendar").json() == []
