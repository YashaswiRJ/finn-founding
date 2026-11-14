"""Owner isolation, retention, snapshot privacy, and the API's auth boundary."""
import gzip
import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.database import db
from app.network import rank, repo, resolve


@pytest.fixture()
def two_owners(demo_net):
    repo.ensure_investor("alice", "Alice")
    p = repo.create_contact("alice", {"full_name": "Secret Contact", "headline": "Alice only"})
    repo.add_relationship("alice", repo.self_id("alice"), p["id"], "friend", 5)
    return p["id"]


def test_investors_never_see_each_others_contacts(two_owners):
    secret = two_owners
    assert repo.person("demo", secret) is None
    assert all(c["id"] != secret for c in repo.contacts("demo"))
    assert repo.people_by_ids("demo", [secret]) == {}
    assert repo.employments("demo", [secret]) == []
    assert all(r["owner_id"] == "demo" for r in repo.relationships("demo"))
    assert not repo.delete_contact("demo", secret) and repo.person("alice", secret)
    with pytest.raises(PermissionError):
        repo.add_relationship("demo", repo.self_id("demo"), secret, "friend", 3)
    assert repo.counts("alice")["contacts"] == 1
    # public figures from filings are visible to everyone
    pub = db.query_one("SELECT id FROM people WHERE owner_id IS NULL LIMIT 1")["id"]
    assert repo.person("alice", pub) and repo.person("demo", pub)


def test_matches_are_suggested_never_merged(two_owners):
    pub = db.query_one("SELECT * FROM people WHERE owner_id IS NULL AND name_norm = 'rashmi joshi'")
    twin = repo.create_contact("demo", {"full_name": "Rashmi Joshi"})
    from app.network import orgs
    repo.add_employment("demo", twin["id"], orgs.resolve_org("Castrol India Limited"), title="CFO",
                        provenance="user_entered")
    m = resolve.match_public_person("demo", pub["id"])
    assert m and m[0]["contact_id"] == twin["id"] and m[0]["confidence"] >= 0.9
    assert resolve.match_public_person("alice", pub["id"]) == []  # alice has no such contact
    assert db.query_one("SELECT COUNT(*) n FROM people WHERE name_norm = 'rashmi joshi'")["n"] == 2  # not merged
    repo.decide_match("demo", pub["id"], twin["id"], "rejected")
    resolve.match_public_person("demo", pub["id"])
    assert repo.matches_for("demo", pub["id"]) == []  # a rejection is remembered


def test_retention_purges_expired_contacts(two_owners):
    db.execute("UPDATE people SET expires_at = '2000-01-01' WHERE id = ?", (two_owners,))
    assert repo.purge_expired() == 1 and repo.person("alice", two_owners) is None
    assert repo.delete_all("demo")["people"] > 0 and repo.counts("demo")["contacts"] == 0


def test_snapshot_exports_public_people_only(two_owners, tmp_path, monkeypatch):
    from app.services import snapshot
    monkeypatch.setattr(snapshot, "PATH", tmp_path / "s.json.gz")
    monkeypatch.setattr(settings, "seed_dir", tmp_path)
    snapshot.export()
    data = json.load(gzip.open(tmp_path / "s.json.gz", "rt"))
    people = data["tables"]["people"]
    assert people and all(p["owner_id"] is None for p in people)
    owner_ids = {p["id"] for p in people}
    assert all(e["person_id"] in owner_ids for e in data["tables"]["employments"])
    for t in ("relationships", "network_insights", "person_matches", "investors", "expertise"):
        assert t not in data["tables"]
    assert not any(r["key"].startswith("net:") for r in data["tables"]["kv"])


def test_api_demo_mode_and_auth_boundary(two_owners, monkeypatch):
    from app.main import app
    c = TestClient(app)  # no lifespan: the fixture already prepared the database
    r = c.get("/api/network/summary")
    assert r.status_code == 200 and r.json()["contacts"] > 50
    r = c.post("/api/network/query", json={"q": "Who previously worked at Tata Motors?"})
    assert r.json()["people"][0]["person"]["full_name"] == "Ritika Menon"
    tmpv = c.get("/api/network/company/TMPV/contacts").json()
    assert tmpv["people"][0]["person"]["full_name"] == "Ritika Menon"
    ann = c.get("/api/announcements/t-cipla-cto").json()
    assert ann["network"]["people"][0]["hits"]

    token = repo.issue_token("alice")
    r = c.get("/api/network/people", headers={"Authorization": f"Bearer {token}"})
    assert [p["full_name"] for p in r.json()["people"]] == ["Secret Contact"]
    assert c.get("/api/network/people", headers={"Authorization": "Bearer nope"}).status_code == 401

    monkeypatch.setattr(settings, "network_demo_mode", False)
    assert c.get("/api/network/summary").status_code == 401
    r = c.get("/api/announcements/t-cipla-cto")  # Push keeps working without a sign-in, minus the network
    assert r.status_code == 200 and r.json()["network"] is None
    ask = c.post("/api/research/chat", json={"message": "Who previously worked at Tata Motors?"})
    assert ask.status_code == 200 and ask.json()["intent"] != "network"


def test_contact_creation_requires_attestation_and_warns_on_duplicates(two_owners):
    from app.main import app
    c = TestClient(app)
    body = {"full_name": "Ritika Menon", "employer": "Tata Motors", "relationship": "friend", "strength": 4}
    assert c.post("/api/network/people", json=body).status_code == 422
    r = c.post("/api/network/people", json={**body, "attest": True}).json()
    assert r["created"] is False and r["duplicates_warning"]
    r = c.post("/api/network/people", json={**body, "full_name": "New Person", "attest": True}).json()
    assert r["created"] and r["person"]["employments"][0]["symbol"] == "TMPV"
    assert c.delete(f"/api/network/people/{r['person']['id']}").status_code == 200


def test_rate_limit_and_old_ticker_alias(two_owners, monkeypatch):
    from app import ratelimit
    from app.main import app
    from app.research import financials
    c = TestClient(app)
    monkeypatch.setattr(financials, "build", lambda s: {"symbol": s, "stub": True})
    r = c.get("/api/company/TATAMOTORS")
    assert r.status_code == 200 and r.json()["company"]["symbol"] == "TMPV"
    monkeypatch.setattr(ratelimit, "PER_MINUTE", 2)
    ratelimit._buckets.clear()
    codes = [c.post("/api/network/query", json={"q": "who knows Wipro"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    ratelimit._buckets.clear()
