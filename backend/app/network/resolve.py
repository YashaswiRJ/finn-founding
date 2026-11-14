"""Is the person in this filing someone the investor already knows?

Deterministic and conservative: names are compared after normalisation, then evidence from shared
employers raises or lowers the confidence. A match is only ever *suggested*; the investor confirms or
rejects it (rejections are remembered). Rows are never merged automatically, because two different
people called 'Rajesh Kumar' is the common case, not the edge case.
"""
from app.database import db
from app.network import repo
from app.network.names import initials_key

AUTO_LABEL = [(0.9, "very likely the same person"), (0.6, "possibly the same person")]


def label(conf: float) -> str | None:
    return next((t for c, t in AUTO_LABEL if conf >= c), None)


def candidates(owner: str, public_id: str) -> list[dict]:
    pub = repo.person(owner, public_id)
    if not pub or pub["owner_id"] is not None:
        return []
    ik = initials_key(pub["name_norm"])
    pub_orgs = {e["org_id"]: e for e in repo.employments(owner, [public_id])}
    out = []
    for c in db.query("SELECT * FROM people WHERE owner_id = ? AND kind = 'contact'", (owner,)):
        if c["name_norm"] == pub["name_norm"]:
            base, method = 0.7, "exact_name"
        elif ik and initials_key(c["name_norm"]) == ik:
            base, method = 0.5, "initials"
        else:
            continue
        shared = [e for e in repo.employments(owner, [c["id"]]) if e["org_id"] in pub_orgs]
        conf = base
        if shared:
            conf += 0.25
            method += "+org"
            pe = pub_orgs[shared[0]["org_id"]]
            if shared[0].get("start_year") and pe.get("start_year"):
                conf += 0.05
        conf = round(min(conf, 0.99), 2)
        if conf >= 0.6:
            out.append({"contact_id": c["id"], "contact_name": c["full_name"], "confidence": conf, "method": method,
                        "label": label(conf)})
    return sorted(out, key=lambda x: -x["confidence"])


def match_public_person(owner: str, public_id: str) -> list[dict]:
    """Record suggestions (never overriding the investor's own confirm/reject decision)."""
    found = candidates(owner, public_id)
    for m in found:
        repo.upsert_match(owner, public_id, m["contact_id"], m["confidence"], m["method"])
    return found
