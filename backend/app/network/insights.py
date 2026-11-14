"""Where the Network meets Push: network hints on filings, and reasons to reconnect.

Computed per investor and stored in network_insights (owner-scoped), so the digest can attach them with
one query and the investor can dismiss one. Filing data is shared; these rows are private.
"""
import json
import re
from datetime import datetime, timedelta

from app.config import IST
from app.database import db
from app.network import graph, rank, repo, resolve

# Events where a person who knows the company is worth a call (the brief: M&A, large capex, litigation).
# Results speak through their numbers card; routine ratings and paperwork don't need a phone call.
MATERIAL = {"M&A", "capex", "litigation", "fund_raise", "pledging"}
MATERIAL_NEEDS_HIGH = {"fund_raise", "pledging"}
MIN_FILING_PERSON_SCORE = 0.07  # below this the link is 'both once worked at a big company': noise
MIN_MATERIAL_SCORE = 0.15       # worked at the company, a competitor or a supplier; a theme alone isn't enough


def _people_on(a: dict) -> list[dict]:
    card = a.get("card") if isinstance(a.get("card"), dict) else json.loads(a.get("card_json") or "{}")
    return [p for p in (card.get("people") or []) if p.get("person_id")]


def for_announcement(owner: str, a: dict, g: graph.Graph | None = None) -> dict:
    """Compute and store this investor's network view of one filing."""
    g = g or graph.load(owner)
    repo.clear_insights(owner, "filing_person", a["id"])
    repo.clear_insights(owner, "material_event", a["id"])
    for p in _people_on(a):
        resolve.match_public_person(owner, p["person_id"])
        for h in rank.for_person(owner, p["person_id"], limit=3, g=g):
            if h["score"] >= MIN_FILING_PERSON_SCORE:
                repo.save_insight(owner, "filing_person", "announcement", a["id"], h["person"]["id"], h["score"],
                                  {**h, "filing_person_id": p["person_id"], "filing_person": p["name"]})
    if _is_material(a):
        hits = rank.for_company(owner, a["symbol"], limit=1, g=g)
        if hits and hits[0]["score"] >= MIN_MATERIAL_SCORE:
            repo.save_insight(owner, "material_event", "announcement", a["id"], hits[0]["person"]["id"],
                              hits[0]["score"], hits[0])
    db.execute("INSERT INTO kv(key, value, updated_at) VALUES (?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
               "value = excluded.value, updated_at = excluded.updated_at",
               (f"net:{owner}:{a['id']}", json.dumps(db.now_iso()), db.now_iso()))
    return view(owner, a)


def _is_material(a: dict) -> bool:
    cat, pri = a.get("category"), a.get("priority")
    return cat in MATERIAL and (pri == "HIGH" or (pri == "MEDIUM" and cat not in MATERIAL_NEEDS_HIGH))


def _computed(owner: str, ann_ids: list[str]) -> set[str]:
    if not ann_ids:
        return set()
    keys = [f"net:{owner}:{i}" for i in ann_ids]
    rows = db.query(f"SELECT key FROM kv WHERE key IN ({','.join('?' * len(keys))})", tuple(keys))
    return {r["key"].split(":", 2)[2] for r in rows}


def view(owner: str, a: dict, rows: list[dict] | None = None) -> dict | None:
    rows = rows if rows is not None else repo.insights(owner, subject_ids=[a["id"]])
    people = []
    for p in _people_on(a):
        hits = [r["payload"] for r in rows if r["kind"] == "filing_person"
                and r["payload"].get("filing_person_id") == p["person_id"]]
        for r in rows:
            if r["kind"] == "filing_person" and r["payload"].get("filing_person_id") == p["person_id"]:
                r["payload"]["insight_id"] = r["id"]
        people.append({"filing_person": {k: p.get(k) for k in ("name", "role", "change", "background_source")},
                       "person_id": p["person_id"], "hits": sorted(hits, key=lambda h: -h["score"])})
    best = next((dict(r["payload"], insight_id=r["id"]) for r in rows if r["kind"] == "material_event"), None)
    if not any(x["hits"] for x in people) and not best:
        return {"people": people, "best_placed": None} if people else None
    return {"people": people, "best_placed": best}


def annotate(owner: str | None, items: list[dict]) -> list[dict]:
    """Attach `network` to each filing for this investor. Computes lazily for filings never seen before
    (e.g. a server that just booted from the seed snapshot), then reads stored insights in one query."""
    if not owner or not items:
        for it in items:
            it["network"] = None
        return items
    ids = [it["id"] for it in items]
    done = _computed(owner, ids)
    todo = [it for it in items if it["id"] not in done and (_people_on(it) or _is_material(it))]
    if todo:
        g = graph.load(owner)
        for it in todo:
            for_announcement(owner, it, g)
    rows = repo.insights(owner, subject_ids=ids)
    by_subject: dict[str, list[dict]] = {}
    for r in rows:
        by_subject.setdefault(r["subject_id"], []).append(r)
    for it in items:
        it["network"] = view(owner, it, by_subject.get(it["id"], []))
    return items


BOILER = re.compile(r"^(pursuant|disclosure under|intimation under|please find|in terms of|we wish|this is to)", re.I)


def headline(f: dict) -> str:
    """The most informative short line for a filing: its detail unless that's regulatory boilerplate."""
    title = re.sub(r"^Announcement under Regulation 30 \(LODR\)-", "", f.get("title") or "").strip()
    d = (f.get("detail") or "").strip()
    text = d if d and not BOILER.match(d) and len(d) > len(title) else title
    return text[:140]


def reconnect(owner: str, quiet_days: int = 120, window_days: int = 21, limit: int = 5) -> list[dict]:
    """Keeping the network warm: contacts you haven't spoken to in a while whose current or former
    employer just filed something that matters. A natural reason to call."""
    g = graph.load(owner)
    paths = graph.reach(g)
    cutoff = (datetime.now(IST) - timedelta(days=quiet_days)).date().isoformat()
    since = (datetime.now(IST) - timedelta(days=window_days)).isoformat(timespec="seconds")
    out = []
    for pid, path in paths.items():
        p = g.people.get(pid)
        if not p or p["kind"] != "contact" or path["edges"][0].get("unlinked"):
            continue
        _, last = graph.warmth(g, pid, path)
        if last and last >= cutoff:
            continue
        for e in g.emps.get(pid, []):
            if not e.get("symbol"):
                continue
            f = db.query_one("SELECT id, title, detail, category, priority, published_at FROM announcements "
                             "WHERE symbol = ? AND published_at >= ? AND priority IN ('HIGH','MEDIUM') "
                             "ORDER BY CASE priority WHEN 'HIGH' THEN 0 ELSE 1 END, published_at DESC LIMIT 1",
                             (e["symbol"], since))
            if not f:
                continue
            former = e.get("is_current") == 0 or bool(e.get("end_year"))
            what = headline(f)
            why = [{"text": f"{'Former employer' if former else 'Their employer'} {e['org_name']} filed "
                            f"{f['published_at'][:10]}: {what}", "provenance": "filing"},
                   {"text": f"Last spoke {last}" if last else "No recent conversation recorded",
                    "provenance": p["provenance"]}]
            score = (1.0 if f["priority"] == "HIGH" else 0.7) * path["strength"]
            hit = rank._hit(g, pid, path, score, why,
                            f"You haven't spoken to {p['full_name']} {'since ' + last if last else 'in a while'}. "
                            f"{e['org_name']}, where they {'used to work' if former else 'work'}, just filed: {what}. "
                            "A natural reason to reconnect.")
            hit["announcement_id"] = f["id"]
            out.append(hit)
            break
    out.sort(key=lambda h: -h["score"])
    return out[:limit]
