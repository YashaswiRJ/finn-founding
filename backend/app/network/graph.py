"""The investor's network as a small in-memory graph, loaded per request from owner-scoped rows.

Two kinds of link, never confused:
- KNOWN edges: rows in `relationships` the investor (or the demo dataset) recorded. Only these say
  "A knows B".
- OVERLAPS: computed here from employment and education histories ("both at Glenmark 2009-2014").
  An overlap is evidence that two people may have crossed paths, labelled with a confidence. It is
  never stored as a relationship and never shown as one.

Networks are small (hundreds of people), so a 2-hop search in Python is instant; see DECISION.md DEC-003.
"""
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from app.config import IST
from app.network import repo

KIND_LABEL = {"knows": "Knows", "former_colleague": "Former colleague", "classmate": "Classmate", "friend": "Friend",
              "met_at_event": "Met at an event", "family": "Family"}
SIZE_FACTOR = {"small": 1.0, "mid": 0.85, "large": 0.6}
HOP_DECAY = 0.85
UNLINKED_STRENGTH = 0.4  # a contact the investor added without recording how well they know them


def current_year() -> int:
    return datetime.now(IST).year


@dataclass
class Graph:
    owner: str
    self_id: str
    people: dict[str, dict]
    adj: dict[str, list[dict]]
    emps: dict[str, list[dict]] = field(default_factory=dict)
    edus: dict[str, list[dict]] = field(default_factory=dict)


def load(owner: str) -> Graph:
    ids = repo.contact_ids(owner)
    people = repo.people_by_ids(owner, ids)
    adj: dict[str, list[dict]] = defaultdict(list)
    for r in repo.relationships(owner):
        if r["from_person_id"] not in people or r["to_person_id"] not in people:
            continue
        e = {k: r[k] for k in ("kind", "strength", "context", "last_interaction_at", "provenance")}
        e["rel_id"] = r["id"]
        adj[r["from_person_id"]].append({**e, "to": r["to_person_id"]})
        adj[r["to_person_id"]].append({**e, "to": r["from_person_id"]})
    g = Graph(owner, repo.self_id(owner), people, adj)
    for row in repo.employments(owner, ids):
        g.emps.setdefault(row["person_id"], []).append(row)
    for row in repo.educations(owner, ids):
        g.edus.setdefault(row["person_id"], []).append(row)
    return g


def histories(owner: str, pid: str) -> tuple[list[dict], list[dict]]:
    return repo.employments(owner, [pid]), repo.educations(owner, [pid])


# ---------- reach: how the investor gets to each person they hold ----------

def reach(g: Graph) -> dict[str, dict]:
    """Best path from the investor to every contact, at most two known hops.
    {pid: {"nodes": [self, (via,) pid], "edges": [edge, ...], "strength": 0..1}}"""
    best: dict[str, dict] = {}
    for e1 in g.adj.get(g.self_id, []):
        s = e1["strength"] / 5
        if e1["to"] not in best or best[e1["to"]]["strength"] < s:
            best[e1["to"]] = {"nodes": [g.self_id, e1["to"]], "edges": [e1], "strength": s}
    for e1 in g.adj.get(g.self_id, []):
        for e2 in g.adj.get(e1["to"], []):
            t = e2["to"]
            if t == g.self_id:
                continue
            s = (e1["strength"] / 5) * (e2["strength"] / 5) * HOP_DECAY
            if t not in best or best[t]["strength"] < s:
                best[t] = {"nodes": [g.self_id, e1["to"], t], "edges": [e1, e2], "strength": s}
    for pid, p in g.people.items():
        if p["kind"] == "contact" and pid not in best:
            best[pid] = {"nodes": [g.self_id, pid], "edges": [{"kind": "knows", "strength": 2, "provenance":
                                                              p["provenance"], "context": None, "unlinked": True,
                                                              "last_interaction_at": p.get("last_interaction_at")}],
                         "strength": UNLINKED_STRENGTH}
    return best


def warmth(g: Graph, pid: str, path: dict) -> tuple[float, str | None]:
    """Recent contact makes a call easier. Uses the most recent interaction on the path's first edge or person."""
    dates = [path["edges"][0].get("last_interaction_at"), g.people.get(path["nodes"][1], {}).get("last_interaction_at")]
    dates = [d for d in dates if d]
    if not dates:
        return 0.85, None
    last = max(dates)
    try:
        days = (datetime.now(IST) - datetime.fromisoformat(last[:10]).replace(tzinfo=IST)).days
    except ValueError:
        return 0.85, None
    return (1.0 if days < 180 else 0.9 if days < 730 else 0.8), last[:10]


# ---------- overlaps: where two careers crossed ----------

def _interval(e: dict) -> tuple[int | None, int | None]:
    cy = current_year()
    s, en, cur = e.get("start_year"), e.get("end_year"), e.get("is_current")
    if en is None and (cur == 1 or (s and cur is None)):
        en = cy
    return s, en


def _span(e: dict) -> str:
    s, en = e.get("start_year"), e.get("end_year")
    if s and en:
        return f"{s}–{en}"
    if s:
        return f"since {s}" if e.get("is_current") != 0 else f"from {s}"
    if e.get("is_current") == 1:
        return "currently"
    if e.get("is_current") == 0:
        return "previously, dates not stated"
    return "dates not stated"


def _who(e: dict) -> str:
    return f"{e.get('title') or 'role not stated'} at {e['org_name']} ({_span(e)})"


def overlaps(a_emps: list[dict], a_edus: list[dict], b_emps: list[dict], b_edus: list[dict]) -> list[dict]:
    """Every place two histories meet, strongest first. Confidence reflects how likely they actually met:
    shared years at a small firm count far more than 'both once worked at a 600,000-person company'."""
    out: list[dict] = []
    for ea in a_emps:
        for eb in b_emps:
            if ea["org_id"] != eb["org_id"]:
                continue
            size = SIZE_FACTOR.get(ea.get("size_bucket") or "", 0.75)
            same_fn = bool(ea.get("function") and ea.get("function") == eb.get("function"))
            (sa, xa), (sb, xb) = _interval(ea), _interval(eb)
            if sa and xa and sb and xb:
                inter = min(xa, xb) - max(sa, sb)
                if inter >= 0:
                    yrs = max(inter, 1) if inter == 0 else inter
                    conf = min(0.85, (0.45 + 0.1 * min(yrs, 3)) * size + (0.1 if same_fn else 0))
                    kind, label = "worked_together", f"Both at {ea['org_name']} {max(sa, sb)}–{min(xa, xb)}"
                else:
                    conf, kind = 0.12 * size, "same_employer_different_times"
                    label = f"Both worked at {ea['org_name']}, at different times"
            elif ea.get("is_current") == 1 and eb.get("is_current") == 1:
                board = "board" in (ea.get("seniority"), eb.get("seniority"))
                conf = (0.5 if board else 0.45) * size + (0.1 if same_fn else 0)
                kind = "board_and_staff" if board else "both_current"
                label = (f"{ea['org_name']}: one sits on the board, the other works there" if board
                         else f"Both currently at {ea['org_name']}")
            else:
                conf, kind = 0.25 * size + (0.05 if same_fn else 0), "same_employer_dates_unknown"
                label = f"Both worked at {ea['org_name']}; dates don't establish they overlapped"
            out.append({"type": kind, "org_id": ea["org_id"], "org": ea["org_name"], "label": label,
                        "confidence": round(conf, 2), "a": _who(ea), "b": _who(eb),
                        "a_provenance": ea["provenance"], "b_provenance": eb["provenance"],
                        "b_evidence": eb.get("evidence")})
    for ea in a_edus:
        for eb in b_edus:
            if ea["org_id"] != eb["org_id"]:
                continue
            ya, yb = ea.get("end_year"), eb.get("end_year")
            if ya and yb and abs(ya - yb) <= 1:
                conf, kind, label = 0.6, "batchmates", f"Likely batchmates at {ea['org_name']} ({ya} / {yb})"
            elif ya and yb and abs(ya - yb) <= 3:
                conf, kind, label = 0.4, "overlapping_years", f"At {ea['org_name']} in overlapping years ({ya} / {yb})"
            else:
                conf, kind, label = 0.18, "same_alma_mater", f"Same alma mater: {ea['org_name']}"
            out.append({"type": kind, "org_id": ea["org_id"], "org": ea["org_name"], "label": label,
                        "confidence": conf, "a": f"studied at {ea['org_name']}" + (f" ({ya})" if ya else ""),
                        "b": f"studied at {eb['org_name']}" + (f" ({yb})" if yb else ""),
                        "a_provenance": ea["provenance"], "b_provenance": eb["provenance"],
                        "b_evidence": eb.get("evidence")})
    out.sort(key=lambda o: -o["confidence"])
    return out


def decay(years_since: float) -> float:
    return math.exp(-max(0.0, years_since) / 8.0)
