"""Load the synthetic demo network (seed/network_demo.json) into the demo investor's account.

Runs at boot when the demo investor has no contacts. Idempotent. Every row it writes is labelled
provenance='synthetic' / consent_basis='synthetic', and the UI shows a 'Demo data' chip on it.
"""
import json
import logging

from app.config import settings
from app.database import db
from app.network import graph, orgs, repo, themes
from app.network.names import norm_org

log = logging.getLogger(__name__)
PATH = settings.seed_dir / "network_demo.json"


def _org(name: str, meta: dict[str, dict]) -> str:
    m = meta.get(norm_org(name), {})
    return orgs.ensure_org(name, m.get("kind") or "private", None, m.get("sector"), m.get("size_bucket"))


def load_demo_if_empty(path=PATH) -> dict | None:
    if not settings.network_demo_mode or not path.exists():
        return None
    owner = settings.demo_investor_id
    repo.ensure_investor(owner, "Demo investor")
    if repo.counts(owner)["contacts"]:
        return None
    data = json.loads(path.read_text())
    meta = {norm_org(o["name"]): o for o in data["organizations"]}
    for o in data["organizations"]:
        oid = orgs.ensure_org(o["name"], o["kind"], None, o.get("sector"), o.get("size_bucket"))
        db.execute("UPDATE organizations SET kind = CASE WHEN symbol IS NOT NULL THEN 'listed' ELSE ? END, "
                   "sector = COALESCE(sector, ?), size_bucket = COALESCE(size_bucket, ?) WHERE id = ?",
                   (o["kind"], o.get("sector"), o.get("size_bucket"), oid))
    for r in data.get("org_relations", []):
        a, b = _org(r["org"], meta), _org(r["related"], meta)
        db.execute("INSERT OR IGNORE INTO org_relations(org_id, related_org_id, kind, provenance) "
                   "VALUES (?, ?, ?, 'synthetic')", (a, b, r["kind"]))

    ids = {"self": repo.self_id(owner)}
    db.execute("UPDATE investors SET consent_accepted_at = ? WHERE id = ?", (db.now_iso(), owner))
    me = data["investor"]["self"]
    for e in me.get("employments", []):
        repo.add_employment(owner, ids["self"], _org(e["org"], meta), title=e.get("title"), function=e.get("function"),
                            seniority=e.get("seniority"), start_year=e.get("start_year"), end_year=e.get("end_year"),
                            is_current=1 if e.get("end_year") is None else 0, provenance="synthetic")
    for e in me.get("educations", []):
        repo.add_education(owner, ids["self"], _org(e["org"], {**meta, norm_org(e["org"]): {"kind": "university"}}),
                           degree=e.get("degree"), end_year=e.get("end_year"), provenance="synthetic")

    cy = graph.current_year()
    for p in data["people"]:
        row = repo.create_contact(owner, {"full_name": p["full_name"], "headline": p.get("headline"),
                                          "location": p.get("location"), "notes": p.get("notes"),
                                          "last_interaction_at": p.get("last_interaction_at"),
                                          "provenance": "synthetic", "consent_basis": "synthetic"})
        ids[p["key"]] = row["id"]
        for e in p.get("employments", []):
            repo.add_employment(owner, row["id"], _org(e["org"], meta), title=e.get("title"),
                                function=e.get("function"), seniority=e.get("seniority"),
                                start_year=e.get("start_year"), end_year=e.get("end_year"),
                                is_current=1 if e.get("end_year") is None else 0, provenance="synthetic")
        for e in p.get("educations", []):
            repo.add_education(owner, row["id"],
                               _org(e["org"], {**meta, norm_org(e["org"]): meta.get(norm_org(e["org"]),
                                                                                    {"kind": "university"})}),
                               degree=e.get("degree"), end_year=e.get("end_year"), provenance="synthetic")
        for x in p.get("expertise", []):
            repo.set_expertise(owner, row["id"], x["theme"], x["weight"], "declared", "declared by you")
        derive_expertise(owner, row["id"], cy)
    for r in data["relationships"]:
        try:
            repo.add_relationship(owner, ids[r["from"]], ids[r["to"]], r["kind"], r["strength"], r.get("context"),
                                  r.get("last_interaction_at"), provenance="synthetic")
        except Exception as e:  # duplicate pair in generated data
            log.debug("skip relationship %s: %s", r, e)
    out = repo.counts(owner)
    log.info("Loaded demo network: %s", out)
    return out


def derive_expertise(owner: str, pid: str, current_year: int | None = None) -> None:
    emps = repo.employments(owner, [pid])
    for theme, (w, ev) in themes.derive(emps, current_year or graph.current_year()).items():
        if w >= 0.15:
            repo.set_expertise(owner, pid, theme, w, "derived", ev)
