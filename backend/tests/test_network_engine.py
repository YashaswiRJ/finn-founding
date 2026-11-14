"""Network engine on the synthetic demo network + real filings."""
from app.network import graph, insights, profiles, query, rank, repo
from app.network.names import norm_person
from app.database import db


def _filing_person(name):
    return db.query_one("SELECT id FROM people WHERE owner_id IS NULL AND name_norm = ?", (norm_person(name),))["id"]


def test_filing_bios_become_evidence_backed_histories(demo_net):
    pid = _filing_person("Rashmi Joshi")
    emps = {e["org_name"]: e for e in repo.employments("demo", [pid])}
    assert emps["Castrol India Limited"]["title"] == "Executive Director & Chief Financial Officer"
    assert emps["Castrol India Limited"]["is_current"] == 0
    assert emps["Bharat Forge Limited"]["seniority"] == "board" and emps["Bharat Forge Limited"]["is_current"] == 1
    for e in emps.values():  # every row cites the filing
        assert e["provenance"] == "filing" and e["evidence"]


def test_rules_history_never_invents_organisations():
    bio = "Mr X has 20 years of experience. He previously served as CFO of Acme Widgets Limited."
    h = profiles.rules_history(bio)
    assert [e["org"] for e in h["employments"]] == ["Acme Widgets Limited"]
    for e in h["employments"]:
        assert e["org"] in bio and e["evidence"] in bio


def test_model_history_drops_unverifiable_rows(monkeypatch):
    from app.llm import client as llm
    bio = "He joins Cipla from the Boston Consulting Group (BCG) as Managing Director."
    monkeypatch.setattr(llm, "structured", lambda *a, **k: {
        "employments": [
            {"org": "Boston Consulting Group", "title": "Managing Director", "start_year": "", "end_year": "",
             "is_current": "yes", "evidence": "joins Cipla from the Boston Consulting Group (BCG) as Managing Director"},
            {"org": "Goldman Sachs", "title": "VP", "start_year": "2001", "end_year": "2005", "is_current": "no",
             "evidence": "He was a VP at Goldman Sachs"}],
        "educations": []})
    h = profiles.model_history(bio)
    assert [e["org"] for e in h["employments"]] == ["Boston Consulting Group"] and h["dropped"] == 1


def test_new_cto_reachable_through_known_contacts_with_inferred_last_hop(demo_net):
    hits = rank.for_person("demo", _filing_person("Vikram Janakiraman"))
    names = [h["person"]["full_name"] for h in hits]
    assert names[0] == "Aditya Rao"  # both currently at BCG, reached through Neha
    assert hits[0]["degree"] == 2 and hits[0]["path"][1]["name"] == "Neha Bansal"
    assert hits[0]["path"][-1]["edge"]["kind"] == "overlap" and hits[0]["path"][-1]["edge"]["known"] is False
    assert "Sameer Kulkarni" not in names  # left Cipla before this outside hire arrives: no overlap


def test_overlap_with_shared_years_beats_dates_unknown(demo_net):
    hits = rank.for_person("demo", _filing_person("Sanjay D’Souza"))
    top = hits[0]
    assert top["person"]["full_name"] == "Farhan Qureshi"
    assert "Both at HDFC Bank 2010–2020" in top["why"][0]["text"]


def test_no_invented_links(demo_net):
    """Every edge in every path is a recorded relationship, or a computed overlap carrying its evidence."""
    known = {(r["from_person_id"], r["to_person_id"]) for r in repo.relationships("demo")}
    known |= {(b, a) for a, b in known}
    all_hits = rank.for_company("demo", "TMPV") + rank.for_company("demo", "CIPLA")
    for name in ("Vikram Janakiraman", "Rashmi Joshi", "Angan Guha", "Sanjay D’Souza"):
        all_hits += rank.for_person("demo", _filing_person(name))
    assert all_hits
    for h in all_hits:
        nodes = h["path"]
        for prev, node in zip(nodes, nodes[1:]):
            e = node["edge"]
            if e["kind"] == "overlap":
                assert not e["known"] and e["evidence"] and 0 < e["confidence"] <= 0.85
            elif e.get("label") != "Unrecorded":
                assert (prev["id"], node["id"]) in known


def test_who_to_call_ranks_former_employee_above_supplier_and_competitor(demo_net):
    hits = rank.for_company("demo", "TMPV")
    assert hits[0]["person"]["full_name"] == "Ritika Menon"
    texts = " ".join(w["text"] for h in hits for w in h["why"])
    assert "a supplier of Tata Motors" in texts and "a competitor of Tata Motors" in texts


def test_current_insider_is_flagged(demo_net):
    from app.network import orgs
    p = repo.create_contact("demo", {"full_name": "Insider Person"})
    repo.add_relationship("demo", repo.self_id("demo"), p["id"], "friend", 5)
    repo.add_employment("demo", p["id"], orgs.for_symbol("CIPLA")["id"], title="VP Finance", seniority="vp",
                        start_year=2020, is_current=1, provenance="user_entered")
    hit = next(h for h in rank.for_company("demo", "CIPLA") if h["person"]["id"] == p["id"])
    assert "mnpi" in hit["flags"]


def repo_org(name):
    from app.network import orgs
    return orgs.resolve_org(name)


def test_direct_queries_parse_by_rules(demo_net):
    cases = {
        "Who in my network understands semiconductor manufacturing?": ("theme", None),
        "Who previously worked at Tata Motors?": ("employer", "TMPV"),
        "Who can connect me to Cipla's new chief technical operating officer?": ("person_at_company", "CIPLA"),
        "Which contacts have automobile industry experience?": ("theme", None),
        "Who haven't I spoken to lately?": ("reconnect", None),
    }
    for q, (kind, sym) in cases.items():
        f = query.parse(q)
        assert f["kind"] == kind, q
        assert f["via"] == "rules"
        if sym:
            assert f["symbol"] == sym, q
    r = query.run("demo", "Who in my network understands semiconductor manufacturing?")
    assert r["people"][0]["person"]["full_name"] in ("Ananya Sharma", "Siddharth Rao")
    r = query.run("demo", "Who previously worked at Tata Motors?")
    assert [h["person"]["full_name"] for h in r["people"]] == ["Ritika Menon"]
    r = query.run("demo", "Who can connect me to Cipla's new chief technical operating officer?")
    assert r["target"]["full_name"] == "Vikram Janakiraman" and r["people"]


def test_filing_insights_are_stored_per_owner_and_annotated(demo_net):
    a = db.query_one("SELECT * FROM announcements WHERE id = 't-cipla-cto'")
    items = insights.annotate("demo", [dict(a)])
    net = items[0]["network"]
    assert net["people"][0]["filing_person"]["name"] == "Vikram Janakiraman"
    assert net["people"][0]["hits"][0]["person"]["full_name"] == "Aditya Rao"
    assert net["best_placed"] is None  # a management change speaks through its people
    assert insights.annotate(None, [dict(a)])[0]["network"] is None
    # A material event at a company the investor knows people at points to the best-placed person
    db.execute("INSERT INTO announcements(id, symbol, title, published_at, source, category, priority, priority_score, "
               "card_json, ingested_at) VALUES ('t-ma', 'CIPLA', 'Acquisition', '2026-11-05T10:00:00+05:30', 'BSE', "
               "'M&A', 'HIGH', 80, '{}', 'x')")
    m = insights.annotate("demo", [db.query_one("SELECT * FROM announcements WHERE id = 't-ma'")])[0]["network"]
    assert m["best_placed"]["person"]["full_name"] == "Sameer Kulkarni"  # ex-Cipla business development


def test_reach_is_at_most_two_known_hops(demo_net):
    g = graph.load("demo")
    for pid, p in graph.reach(g).items():
        assert len(p["nodes"]) <= 3 and p["nodes"][0] == g.self_id
