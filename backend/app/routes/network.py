"""Network API. Every endpoint is scoped to the calling investor (app/auth.py)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.announcements import service as announcements
from app.auth import current_investor
from app.database import db
from app.network import graph, insights, orgs, query, rank, repo, resolve, seed, themes
from app.ratelimit import limit

router = APIRouter(prefix="/api/network")

REL_KINDS = ("knows", "former_colleague", "classmate", "friend", "met_at_event", "family")


def _brief(p: dict) -> dict:
    return {k: p.get(k) for k in ("id", "full_name", "headline", "location", "kind", "provenance",
                                  "last_interaction_at", "source_url", "source_ref")}


@router.get("/summary")
def summary(owner: str = Depends(current_investor)):
    tc = repo.theme_counts(owner)
    g = graph.load(owner)
    top_themes = []
    for r in tc[:10]:
        hits = rank.for_theme(owner, [r["theme"]], limit=3, g=g)
        top_themes.append({"theme": r["theme"], "label": themes.THEMES.get(r["theme"], r["theme"]), "count": r["n"],
                           "top": hits})
    inv = repo.investor(owner) or {}
    return {"investor": {"id": owner, "display_name": inv.get("display_name"),
                         "demo": owner == "demo"},
            **repo.counts(owner), "themes": top_themes, "reconnect": insights.reconnect(owner, limit=3),
            "in_the_news": [_brief(p) | {"symbol": p["symbol"], "published_at": p["published_at"]}
                            for p in query.recent_filing_people(6)]}


@router.get("/people")
def people(q: str | None = Query(None, max_length=80), theme: str | None = None, org: str | None = None,
           limit: int = Query(200, ge=1, le=500), owner: str = Depends(current_investor)):
    if theme:
        if theme not in themes.THEMES:
            raise HTTPException(422, "Unknown theme")
        return {"people": rank.for_theme(owner, [theme], limit=limit)}
    if org:
        oid = orgs.resolve_org(org)
        if not oid:
            return {"people": []}
        return {"people": rank.for_employer(owner, oid, limit=limit)}
    return {"people": [_brief(p) for p in repo.contacts(owner, q, limit)]}


@router.get("/people/{pid}")
def person(pid: str, owner: str = Depends(current_investor)):
    p = repo.person(owner, pid)
    if not p:
        raise HTTPException(404, "No such person in your network")
    emps, edus = graph.histories(owner, pid)
    rels = []
    if p["owner_id"] == owner:
        g = graph.load(owner)
        for e in g.adj.get(pid, []):
            other = g.people.get(e["to"])
            if other:
                rels.append({"id": e["rel_id"], "person": _brief(other) | {"name": "You" if other["kind"] == "self"
                                                                         else other["full_name"]},
                             "kind": e["kind"], "label": graph.KIND_LABEL.get(e["kind"]), "strength": e["strength"],
                             "context": e.get("context"), "provenance": e["provenance"]})
    paths = rank.for_person(owner, pid, limit=5) if p["kind"] != "self" else []
    out = {**_brief(p), "notes": p.get("notes") if p["owner_id"] == owner else None,
           "employments": sorted(emps, key=lambda e: -(e.get("start_year") or e.get("end_year") or 0)),
           "educations": edus, "relationships": rels,
           "expertise": [{**x, "label": themes.THEMES.get(x["theme"], x["theme"])} for x in repo.expertise(owner, [pid])],
           "paths": paths, "diligence": diligence(emps), "matches": resolve.candidates(owner, pid)
           if p["owner_id"] is None else []}
    if p["owner_id"] is None and p.get("source_ref"):
        a = announcements.get(p["source_ref"])
        if a:
            out["filing"] = {"id": a["id"], "title": a["title"], "published_at": a["published_at"],
                             "pdf_url": a["pdf_url"], "symbol": a["symbol"], "company_name": a.get("company_name"),
                             "person": next((x for x in a["card"].get("people", []) if x.get("person_id") == pid), None)}
    return out


def diligence(emps: list[dict]) -> list[str]:
    """Things worth asking about, from the career itself. Phrased as questions, never as conclusions."""
    notes = []
    dated = sorted([e for e in emps if e.get("start_year") and e.get("end_year")], key=lambda e: e["start_year"])
    for e in dated:
        if e["end_year"] - e["start_year"] < 2 and e.get("seniority") in ("cxo", "vp", "board"):
            notes.append(f"Short senior stint at {e['org_name']} ({e['start_year']}–{e['end_year']}): why did it end?")
    for a, b in zip(dated, dated[1:]):
        if b["start_year"] - a["end_year"] > 2:
            notes.append(f"A {b['start_year'] - a['end_year']}-year gap between {a['org_name']} and {b['org_name']}.")
        if a.get("sector") and a.get("sector") == b.get("sector") and a["org_id"] != b["org_id"]:
            notes.append(f"Moved between {a['sector']} peers ({a['org_name']} → {b['org_name']}): what did they see "
                         "that made them switch?")
    boards = [e for e in emps if e.get("seniority") == "board" and e.get("is_current") == 1]
    if len(boards) >= 5:
        notes.append(f"Sits on {len(boards)} boards: how much time can they give this one?")
    return notes[:4]


class PersonCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    headline: str | None = Field(None, max_length=160)
    location: str | None = Field(None, max_length=80)
    notes: str | None = Field(None, max_length=1000)
    last_interaction_at: str | None = Field(None, max_length=10)
    employer: str | None = Field(None, max_length=120)
    title: str | None = Field(None, max_length=120)
    start_year: int | None = Field(None, ge=1950, le=2100)
    end_year: int | None = Field(None, ge=1950, le=2100)
    relationship: str = "knows"
    strength: int = Field(3, ge=1, le=5)
    attest: bool = Field(False, description="I have a professional relationship with this person")
    allow_duplicate: bool = False


@router.post("/people")
def create_person(body: PersonCreate, owner: str = Depends(current_investor)):
    if not body.attest:
        raise HTTPException(422, "Confirm you have a professional relationship with this person")
    if body.relationship not in REL_KINDS:
        raise HTTPException(422, f"relationship must be one of {', '.join(REL_KINDS)}")
    from app.network.names import norm_person
    dups = repo.contacts_named(owner, norm_person(body.full_name))
    if dups and not body.allow_duplicate:
        return {"created": False, "duplicates_warning": [_brief(d) for d in dups]}
    p = repo.create_contact(owner, {**body.model_dump(), "provenance": "user_entered",
                                    "consent_basis": "investor_attested"})
    if body.employer:
        oid = orgs.ensure_org(body.employer, "private")
        repo.add_employment(owner, p["id"], oid, title=body.title, start_year=body.start_year, end_year=body.end_year,
                            is_current=1 if body.end_year is None else 0, provenance="user_entered")
        seed.derive_expertise(owner, p["id"])
    repo.add_relationship(owner, repo.self_id(owner), p["id"], body.relationship, body.strength,
                          last_interaction_at=body.last_interaction_at)
    return {"created": True, "person": person(p["id"], owner)}


class PersonPatch(BaseModel):
    headline: str | None = Field(None, max_length=160)
    location: str | None = Field(None, max_length=80)
    notes: str | None = Field(None, max_length=1000)
    last_interaction_at: str | None = Field(None, max_length=10)


@router.patch("/people/{pid}")
def patch_person(pid: str, body: PersonPatch, owner: str = Depends(current_investor)):
    p = repo.update_contact(owner, pid, body.model_dump(exclude_none=True))
    if not p:
        raise HTTPException(404, "No such contact")
    return _brief(p)


@router.delete("/people/{pid}")
def delete_person(pid: str, owner: str = Depends(current_investor)):
    if not repo.delete_contact(owner, pid):
        raise HTTPException(404, "No such contact")
    return {"ok": True}


class RelCreate(BaseModel):
    to_person_id: str
    from_person_id: str | None = None
    kind: str = "knows"
    strength: int = Field(3, ge=1, le=5)
    context: str | None = Field(None, max_length=200)
    last_interaction_at: str | None = Field(None, max_length=10)


@router.post("/relationships")
def add_relationship(body: RelCreate, owner: str = Depends(current_investor)):
    if body.kind not in REL_KINDS:
        raise HTTPException(422, f"kind must be one of {', '.join(REL_KINDS)}")
    try:
        return repo.add_relationship(owner, body.from_person_id or repo.self_id(owner), body.to_person_id, body.kind,
                                     body.strength, body.context, body.last_interaction_at)
    except PermissionError as e:
        raise HTTPException(404, str(e))
    except Exception:
        raise HTTPException(409, "That relationship already exists")


@router.delete("/relationships/{rel_id}")
def delete_relationship(rel_id: int, owner: str = Depends(current_investor)):
    if not repo.delete_relationship(owner, rel_id):
        raise HTTPException(404, "No such relationship")
    return {"ok": True}


@router.get("/paths")
def paths(to: str, owner: str = Depends(current_investor)):
    if not repo.person(owner, to):
        raise HTTPException(404, "No such person")
    return {"paths": rank.for_person(owner, to)}


@router.get("/company/{symbol}/contacts")
def company_contacts(symbol: str, limit: int = Query(5, ge=1, le=10), owner: str = Depends(current_investor)):
    symbol = symbol.upper()
    org = orgs.for_symbol(symbol)
    if not org:
        c = db.query_one("SELECT * FROM companies WHERE symbol = ?", (symbol,))
        if not c:
            raise HTTPException(404, "Unknown company")
        orgs.ensure_org(c["name"], "listed", symbol, c.get("sector"), c.get("size_bucket"))
        org = orgs.for_symbol(symbol)
    g = graph.load(owner)
    hits = rank.for_company(owner, symbol, limit=limit, g=g)
    fallback = []
    if not hits:
        fallback = rank.for_theme(owner, themes.themes_for_sector(org.get("sector")), limit=3, g=g)
    fns = sorted({e.get("function") for h in hits for e in g.emps.get(h["person"]["id"], []) if e.get("function")})
    used: set[str] = set()
    for h in hits:  # each question goes to the best-placed person only; no repeated boilerplate
        qs = rank.questions(symbol, [e.get("function") for e in g.emps.get(h["person"]["id"], []) if e.get("function")],
                            limit=6)
        h["suggested_questions"] = [q for q in qs if q not in used][:2]
        used.update(h["suggested_questions"])
    news = [_brief(p) | {"title": p.get("title")} for p in repo.public_figures_at(org["id"])[:4]]
    return {"symbol": symbol, "organization": org["name"], "people": hits, "theme_fallback": fallback,
            "in_the_news": news, "functions": fns,
            "basis": f"Your network ({repo.counts(owner)['contacts']} contacts) matched on employers, competitors, "
                     "suppliers and expertise. No model call."}


@router.get("/announcement/{ann_id}")
def announcement_network(ann_id: str, owner: str = Depends(current_investor)):
    a = announcements.get(ann_id)
    if not a:
        raise HTTPException(404, "Unknown announcement")
    insights.annotate(owner, [a])
    return a["network"] or {"people": [], "best_placed": None}


@router.get("/expertise")
def expertise(owner: str = Depends(current_investor)):
    g = graph.load(owner)
    return {"themes": [{"theme": r["theme"], "label": themes.THEMES.get(r["theme"], r["theme"]), "count": r["n"],
                        "people": rank.for_theme(owner, [r["theme"]], limit=5, g=g)}
                       for r in repo.theme_counts(owner)]}


@router.get("/reconnect")
def reconnect(days: int = Query(120, ge=14, le=1000), owner: str = Depends(current_investor)):
    return {"people": insights.reconnect(owner, quiet_days=days)}


class Q(BaseModel):
    q: str = Field(min_length=2, max_length=300)


@router.post("/query", dependencies=[Depends(limit)])
def network_query(body: Q, owner: str = Depends(current_investor)):
    return query.run(owner, body.q)


class Decision(BaseModel):
    status: str


@router.post("/matches/{public_id}/{contact_id}")
def decide(public_id: str, contact_id: str, body: Decision, owner: str = Depends(current_investor)):
    if body.status not in ("confirmed", "rejected"):
        raise HTTPException(422, "status must be confirmed or rejected")
    if not repo.decide_match(owner, public_id, contact_id, body.status):
        raise HTTPException(404, "No such suggestion")
    return {"ok": True}


@router.post("/insights/{insight_id}/dismiss")
def dismiss(insight_id: int, owner: str = Depends(current_investor)):
    if not repo.dismiss_insight(owner, insight_id):
        raise HTTPException(404, "No such suggestion")
    return {"ok": True}


@router.delete("/me/data")
def delete_my_data(owner: str = Depends(current_investor)):
    """Right to erasure: removes every private network row for this investor."""
    return {"deleted": repo.delete_all(owner)}
