"""Guided journeys: steps built from the documents, letters, feed cards, undo, agent."""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient

from binder.samples import Sample
from tests.conftest import upload


def start(client: TestClient, kind: str, when: date, **details: str) -> dict[str, Any]:
    r = client.post(
        "/api/journeys",
        json={"kind": kind, "event_date": when.isoformat(), "details": details},
    )
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


def steps(journey: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["key"]: s for s in journey["steps"]}


def load(client: TestClient, samples: list[Sample]) -> dict[str, dict[str, Any]]:
    return {s.filename: upload(client, s) for s in samples}


def test_kinds_are_listed_with_what_to_ask(client: TestClient) -> None:
    kinds = {k["kind"]: k for k in client.get("/api/journeys/kinds").json()}
    assert set(kinds) == {"moving", "birth", "death", "tax_return"}
    assert kinds["moving"]["fields"] == {"new_address": "New address"}
    assert kinds["tax_return"]["default_date"].endswith("-06-01")
    assert client.post("/api/journeys", json={"kind": "wedding"}).status_code == 400


def test_moving_lists_the_organisations_of_the_documents(
    client: TestClient, samples: list[Sample]
) -> None:
    docs = load(client, samples)
    day = date.today() + timedelta(days=60)
    journey = start(client, "moving", day, new_address="8 avenue Foch\n75016 Paris")
    found = steps(journey)
    assert journey["title"] == "Moving house" and journey["total"] == len(found)
    # Tenant: notice to the landlord three months before, and the deposit after.
    assert found["notice"]["due"] == (day - timedelta(days=90)).isoformat()
    assert found["notice"]["document_ids"] == [docs["quittance-loyer.pdf"]["id"]]
    assert found["deposit"]["action"]["params"]["kind"] == "formal_notice"
    # Contracts that follow the home, the home insurance, the bank: one letter each.
    assert found["org:edf"]["title"] == "Transfer or end: EDF"
    assert found["org:orange"]["due"] == (day - timedelta(days=15)).isoformat()
    assert found["org:maif"]["title"] == "Insure the new home: MAIF"
    assert found["org:credit agricole"]["title"] == "New address for Crédit Agricole"
    # Public bodies are told by one online form.
    assert "org:caf" not in found and "CAF" in found["public"]["detail"]
    assert "DGFiP" in found["public"]["detail"]
    # A car and school children in the documents.
    assert "vehicle" in found and found["school"]["action"] == {
        "type": "folder",
        "label": "Prepare the file",
        "params": {"kind": "school"},
    }
    # Steps are sorted by date.
    dues = [s["due"] for s in journey["steps"]]
    assert dues == sorted(dues)


def test_a_sent_letter_completes_its_step(client: TestClient, samples: list[Sample]) -> None:
    load(client, samples)
    day = date.today() + timedelta(days=40)
    journey = start(client, "moving", day, new_address="8 avenue Foch\n75016 Paris")
    edf = steps(journey)["org:edf"]
    letter = client.post("/api/letters", json=edf["action"]["params"]).json()
    assert letter["kind"] == "address_change" and letter["recipient"] == "EDF"
    assert "8 avenue Foch" in letter["body"] and "transfer my contract" in letter["body"]
    drafted = steps(client.get(f"/api/journeys/{journey['id']}").json())["org:edf"]
    assert not drafted["done"] and "mark it as sent" in drafted["detail"]
    client.post(f"/api/letters/{letter['id']}/sent")
    sent = steps(client.get(f"/api/journeys/{journey['id']}").json())["org:edf"]
    assert sent["done"] and sent["auto"] and "Letter sent on" in sent["detail"]


def test_tax_return_totals_the_receipts(client: TestClient, samples: list[Sample]) -> None:
    docs = load(client, samples)
    start(client, "birth", date(2026, 3, 1), child="Jade")
    journey = start(client, "tax_return", date(2027, 6, 1))
    found = steps(journey)
    assert found["donations"]["amount"] == 120.0
    assert found["donations"]["title"] == "Donations: $120.00"
    assert "$79.20" in found["donations"]["detail"] and "7UF" in found["donations"]["detail"]
    assert found["donations"]["document_ids"] == [docs["recu-don.pdf"]["id"]]
    assert found["childcare"]["amount"] == 486.0 and "7GA" in found["childcare"]["detail"]
    assert found["salaries"]["document_ids"] == [docs["bulletin-paie.pdf"]["id"]]
    # Life events of the year, from the other journeys.
    assert found["changes"]["title"] == "Changes in 2026"
    assert "one more half share" in found["changes"]["detail"]
    # The 2027 tax notice is not there yet.
    assert not found["notice"]["done"] and found["notice"]["due"] == "2027-09-01"


def test_birth_and_death_steps(client: TestClient, samples: list[Sample]) -> None:
    docs = load(client, samples)
    birth = steps(start(client, "birth", date.today() + timedelta(days=150), child="Jade"))
    assert {"childcare", "leave", "declare", "record", "health", "caf", "tax"} <= set(birth)
    assert birth["declare"]["detail"].startswith("Within 5 days")
    assert birth["caf"]["document_ids"]
    death = start(client, "death", date.today() - timedelta(days=2), person="Camille Martin")
    assert death["title"] == "Death of a relative: Camille Martin"
    found = steps(death)
    # Their contracts and their bank, from the documents that name them.
    assert found["org:edf"]["title"] == "End or transfer: EDF"
    assert "Camille Martin" in found["org:edf"]["action"]["params"]["purpose"]
    assert found["org:credit agricole"]["title"] == "Tell the bank: Crédit Agricole"
    assert "lease" in found and "caf" in found and "contracts" not in found
    assert found["estate"]["due"] == (date.today() + timedelta(days=180)).isoformat()
    assert docs["facture-edf.pdf"]["id"] in found["org:edf"]["document_ids"]
    unknown = steps(start(client, "death", date.today(), person="Someone Else"))
    assert "contracts" in unknown and "bank" in unknown


def test_steps_in_the_feed_ticked_and_undone(client: TestClient, samples: list[Sample]) -> None:
    load(client, samples)
    journey = start(client, "moving", date.today() + timedelta(days=5))
    cards = [i for i in client.get("/api/feed").json()["items"] if i["kind"] == "journey"]
    # The two most pressing steps: the notice to the landlord is already late.
    assert [c["extra"]["step"] for c in cards] == ["notice", "school"]
    notice = cards[0]
    assert notice["tone"] == "urgent" and notice["detail"].startswith("Moving house · ")
    assert "days late" in notice["detail"]
    done = next(a for a in notice["actions"] if a["type"] == "journey_step")
    r = client.post("/api/actions", json={"type": done["type"], "params": done["params"]})
    assert r.status_code == 200 and r.json()["message"] == "Done: Give notice to your landlord"
    token = r.headers["X-Undo"]
    assert steps(client.get(f"/api/journeys/{journey['id']}").json())["notice"]["done"]
    assert client.post(f"/api/undo/{token}").status_code == 204
    assert not steps(client.get(f"/api/journeys/{journey['id']}").json())["notice"]["done"]
    # Ticked from the journey itself, then closed.
    r = client.put(f"/api/journeys/{journey['id']}/steps/electoral", json={"done": True})
    assert steps(r.json())["electoral"]["done"]
    missing = client.put(f"/api/journeys/{journey['id']}/steps/nope", json={"done": True})
    assert missing.status_code == 404
    closed = client.patch(f"/api/journeys/{journey['id']}", json={"closed": True}).json()
    assert closed["closed"]
    assert not [i for i in client.get("/api/feed").json()["items"] if i["kind"] == "journey"]


def test_same_journey_is_not_started_twice(client: TestClient) -> None:
    first = start(client, "moving", date(2026, 11, 15))
    again = start(client, "moving", date(2026, 11, 20), new_address="1 rue Neuve\n69001 Lyon")
    assert again["id"] == first["id"] and again["event_date"] == "2026-11-20"
    assert again["details"] == {"new_address": "1 rue Neuve\n69001 Lyon"}
    assert len(client.get("/api/journeys").json()) == 1


def test_offline_agent_starts_a_journey(client: TestClient, samples: list[Sample]) -> None:
    load(client, samples)
    ask = lambda m: client.post("/api/agent/chat", json={"message": m}).json()  # noqa: E731
    r = ask("We're moving soon, what do I need to do?")
    assert r["answer"] == "What is your moving day? Binder counts every step from it."
    r = ask("On déménage le 15/12/2026, on fait comment ?")
    assert r["journeys"] and r["journeys"][0]["kind"] == "moving" and r["changed"]
    assert r["answer"].startswith("Here is your checklist “Moving house”:")
    assert "Next: Give notice to your landlord" in r["answer"]
    # A birth certificate is a document, not a birth.
    r = ask("Où est l'acte de naissance de Léa ?")
    assert not r.get("journeys")
