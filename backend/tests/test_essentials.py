"""First launch: three answers, then the papers to have."""

from fastapi.testclient import TestClient


def save(client: TestClient, **answers: str) -> dict[str, str]:
    current = client.get("/api/profile").json()
    r = client.put("/api/profile", json={**current, **answers})
    assert r.status_code == 200
    saved: dict[str, str] = r.json()
    return saved


def keys(client: TestClient) -> dict[str, bool]:
    return {p["key"]: p["present"] for p in client.get("/api/essentials").json()}


def test_papers_follow_the_three_answers(client: TestClient) -> None:
    # Before any answer: what everyone needs.
    assert set(keys(client)) == {"identity", "rib", "tax_notice", "health"}
    saved = save(client, situation="employee", housing="tenant", vehicle="no")
    assert (saved["situation"], saved["housing"], saved["vehicle"]) == ("employee", "tenant", "no")
    papers = keys(client)
    assert {"contract", "payslips", "lease", "rent_receipts", "home_insurance"} <= set(papers)
    assert "registration" not in papers and "property_tax" not in papers
    assert not any(papers.values())
    save(client, housing="owner", vehicle="yes")
    papers = keys(client)
    assert {"property_tax", "registration", "car_insurance", "licence"} <= set(papers)
    assert "lease" not in papers


def test_present_and_missing_on_the_demo(client: TestClient) -> None:
    save(client, situation="employee", housing="tenant", vehicle="yes")
    client.post("/api/demo")
    rows = client.get("/api/essentials").json()
    papers = {p["key"]: p for p in rows}
    assert papers["identity"]["present"] and papers["identity"]["document_id"]
    assert papers["rent_receipts"]["present"] and papers["payslips"]["present"]
    # The Martins have no bank details yet (the demo story).
    assert not papers["rib"]["present"]
    # Missing first, with why and how long to keep each.
    assert [p["present"] for p in rows] == sorted(p["present"] for p in rows)
    assert papers["payslips"]["keep"] == "Until you claim your pension"
    assert papers["rib"]["why"].startswith("Asked for by employers")


def test_unknown_answers_are_ignored(client: TestClient) -> None:
    saved = save(client, situation="astronaut", housing="tenant")
    assert saved["situation"] == "" and saved["housing"] == "tenant"
