"""Who can help with X, ranked, with the reasons spelled out.

Targets: a company (who should I call), a person (who can get me to the new CFO), a theme (who are my
go-to people for specialty chemicals). Scores multiply three things:
  relevance  how much this person is likely to know about the target
  path       how strong the investor's link to them is (known edges only; 2nd degree decays)
  warmth     whether the investor has spoken to them recently
Explanations are built from the same evidence by templates. No model writes them, so nothing can
appear in an explanation that isn't in the data.
"""
from app.database import db
from app.network import graph, orgs, repo, themes
from app.network.graph import KIND_LABEL, Graph

MATERIAL_FLAGS = {"mnpi": "Current insider: talk context and industry, not unpublished numbers"}
SENIORITY_WEIGHT = {"board": 1.1, "cxo": 1.15, "vp": 1.0, "manager": 0.85, "ic": 0.7}


def _node(g: Graph, pid: str, edge: dict | None = None) -> dict:
    p = g.people.get(pid) or {}
    n = {"id": pid, "name": "You" if pid == g.self_id else p.get("full_name", "?")}
    if edge is not None:
        n["edge"] = edge
    return n


def _known_edge(e: dict) -> dict:
    return {"kind": e["kind"], "label": "Unrecorded" if e.get("unlinked") else KIND_LABEL.get(e["kind"], "Knows"),
            "strength": e["strength"], "provenance": e["provenance"], "context": e.get("context"), "known": True}


def path_nodes(g: Graph, path: dict) -> list[dict]:
    nodes = [_node(g, path["nodes"][0])]
    for pid, e in zip(path["nodes"][1:], path["edges"]):
        nodes.append(_node(g, pid, _known_edge(e)))
    return nodes


def _person_brief(p: dict) -> dict:
    return {"id": p["id"], "full_name": p["full_name"], "headline": p.get("headline"), "kind": p["kind"],
            "provenance": p["provenance"]}


def _hit(g: Graph, pid: str, path: dict, score: float, why: list[dict], explanation: str,
         flags: list[str] | None = None, extra_nodes: list[dict] | None = None) -> dict:
    nodes = path_nodes(g, path) + (extra_nodes or [])
    return {"person": _person_brief(g.people[pid]), "score": round(score, 3), "path": nodes, "why": why,
            "explanation": explanation, "flags": flags or [], "degree": len(path["nodes"]) - 1}


def _how_known(g: Graph, path: dict) -> str:
    e = path["edges"][0]
    if len(path["nodes"]) == 2:
        if e.get("unlinked"):
            return "They're in your contacts (no relationship strength recorded)."
        kind = KIND_LABEL.get(e["kind"], "Knows").lower()
        ctx = f", {e['context']}" if e.get("context") else ""
        return f"You know them directly ({kind}{ctx})."
    via = g.people[path["nodes"][1]]["full_name"]
    return f"You'd reach them through {via} ({KIND_LABEL.get(path['edges'][1]['kind'], 'knows').lower()})."


def _span(e: dict) -> str:
    return graph._span(e)


# ---------- company ----------

def for_company(owner: str, symbol: str, limit: int = 5, g: Graph | None = None) -> list[dict]:
    org = orgs.for_symbol(symbol)
    if not org:
        return []
    g = g or graph.load(owner)
    paths = graph.reach(g)
    related = {r["org_id"]: r for r in orgs.related(org["id"])}
    sector_themes = themes.themes_for_sector(org.get("sector"))
    cy = graph.current_year()
    news_people = repo.public_figures_at(org["id"])[:6]
    news_hist = {p["id"]: graph.histories(owner, p["id"]) for p in news_people}
    expertise = {}
    for r in repo.expertise(owner, list(paths)):
        expertise.setdefault(r["person_id"], []).append(r)

    hits = []
    for pid, path in paths.items():
        if pid not in g.people or g.people[pid]["kind"] != "contact":
            continue
        best = (0.0, None, None)  # relevance, why, flag
        whys: list[dict] = []
        for e in g.emps.get(pid, []):
            sen = SENIORITY_WEIGHT.get(e.get("seniority") or "", 0.9)
            prov = e["provenance"]
            if e["org_id"] == org["id"]:
                current = e.get("is_current") == 1 or (e.get("end_year") is None and e.get("start_year"))
                if current:
                    rel = 0.9 * min(sen, 1.0)
                    w = {"text": f"Works at {org['name']} now: {e.get('title') or 'role not recorded'} ({_span(e)})",
                         "provenance": prov}
                    cand = (rel, w, "mnpi")
                else:
                    yrs = cy - (e.get("end_year") or cy)
                    rel = min(1.0, graph.decay(yrs) * sen)
                    w = {"text": f"{e.get('title') or 'Worked'} at {org['name']} ({_span(e)}), "
                                 f"left {yrs} yr{'s' if yrs != 1 else ''} ago", "provenance": prov}
                    cand = (rel, w, None)
            elif e["org_id"] in related:
                r = related[e["org_id"]]
                base = {"competitor": 0.6, "supplier": 0.55, "customer": 0.55, "group": 0.5}[r["kind"]]
                yrs = 0 if (e.get("is_current") == 1 or not e.get("end_year")) else cy - e["end_year"]
                rel = base * graph.decay(yrs) * min(sen, 1.0)
                noun = {"competitor": "a competitor", "supplier": "a supplier", "customer": "a customer",
                        "group": "a group company"}[r["kind"]]
                how = "" if r["provenance"] != "derived_sector" else " (same sector)"
                w = {"text": f"{e.get('title') or 'Worked'} at {e['org_name']}, {noun} of {org['name']}{how} "
                             f"({_span(e)})", "provenance": prov}
                cand = (rel, w, None)
            else:
                continue
            whys.append(cand[1])
            if cand[0] > best[0]:
                best = cand
        for x in expertise.get(pid, []):
            if x["theme"] in sector_themes and 0.4 * x["weight"] > best[0]:
                w = {"text": f"{themes.THEMES.get(x['theme'], x['theme'])} expertise: {x['evidence']}",
                     "provenance": "declared" if x["method"] == "declared" else "derived"}
                best = (0.4 * x["weight"], w, None)
                whys.append(w)
        # Crossed paths with someone in this company's recent filings (e.g. the new CFO)
        crossed = None
        for np_ in news_people:
            ov = graph.overlaps(g.emps.get(pid, []), g.edus.get(pid, []), *news_hist[np_["id"]])
            ov = [o for o in ov if o["org_id"] != org["id"] and o["confidence"] >= 0.3]
            if ov:
                crossed = (np_, ov[0])
                whys.append({"text": f"{ov[0]['label']}, with {np_['full_name']} ({np_.get('headline') or 'in the news'})",
                             "provenance": "inferred", "confidence": ov[0]["confidence"]})
                rel = 0.5 * ov[0]["confidence"]
                if rel > best[0]:
                    best = (rel, whys[-1], None)
                break
        if best[0] <= 0:
            continue
        wm, last = graph.warmth(g, pid, path)
        score = best[0] * path["strength"] * wm
        if last:
            whys.append({"text": f"Last spoke {last}", "provenance": g.people[pid]["provenance"]})
        name = g.people[pid]["full_name"]
        expl = f"{name} — {best[1]['text']}. {_how_known(g, path)}"
        if crossed:
            expl += f" Also crossed paths with {crossed[0]['full_name']} ({crossed[1]['org']})."
        flags = [best[2]] if best[2] else []
        if path["edges"][-1].get("unlinked"):
            flags.append("unrecorded_strength")
        hits.append(_hit(g, pid, path, score, _dedupe(whys), expl, flags))
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


def _dedupe(whys: list[dict]) -> list[dict]:
    seen, out = set(), []
    for w in whys:
        if w["text"] not in seen:
            seen.add(w["text"])
            out.append(w)
    return out[:4]


# ---------- person (incoming CFO, a promoter before a meeting) ----------

def for_person(owner: str, target_id: str, limit: int = 5, g: Graph | None = None) -> list[dict]:
    """Who in the network can get the investor to this person, and how strong is that link.
    Order: a known path to the person themselves > a contact whose career crossed theirs."""
    target = repo.person(owner, target_id)
    if not target:
        return []
    g = g or graph.load(owner)
    paths = graph.reach(g)
    hits = []
    if target_id in paths:  # the target is already in the network
        path = paths[target_id]
        wm, _ = graph.warmth(g, target_id, path)
        hits.append(_hit(g, target_id, path, path["strength"] * wm,
                         [{"text": _how_known(g, path), "provenance": g.people[target_id]["provenance"]}],
                         f"{target['full_name']} is in your network. {_how_known(g, path)}"))
    t_emps, t_edus = graph.histories(owner, target_id)
    for pid, path in paths.items():
        if pid == target_id or g.people.get(pid, {}).get("kind") != "contact":
            continue
        ov = graph.overlaps(g.emps.get(pid, []), g.edus.get(pid, []), t_emps, t_edus)
        ov = [o for o in ov if o["confidence"] >= 0.15]
        if not ov:
            continue
        top = ov[0]
        wm, last = graph.warmth(g, pid, path)
        score = path["strength"] * top["confidence"] * wm
        name = g.people[pid]["full_name"]
        tnode = {"id": target_id, "name": target["full_name"],
                 "edge": {"kind": "overlap", "label": "Inferred overlap", "confidence": top["confidence"],
                          "evidence": top["label"], "provenance": "inferred", "known": False}}
        whys = [{"text": f"{top['label']}: {name} {top['a']}; {target['full_name']} {top['b']}",
                 "provenance": "inferred", "confidence": top["confidence"]}]
        whys += [{"text": o["label"], "provenance": "inferred", "confidence": o["confidence"]} for o in ov[1:3]]
        if last:
            whys.append({"text": f"Last spoke {last}", "provenance": g.people[pid]["provenance"]})
        intro = "You don't know " + target["full_name"] + ". " if target_id not in paths else ""
        expl = (f"{intro}{top['label']}. {name}: {top['a']}. Per the filing, {target['full_name']}: {top['b']}. "
                f"{_how_known(g, path)} Inferred from careers, not a known relationship: verify before relying on it.")
        hits.append(_hit(g, pid, path, score, whys, expl, ["inferred"], [tnode]))
    for m in repo.matches_for(owner, target_id):
        for h in hits:
            if h["person"]["id"] == m["contact_person_id"]:
                h["flags"].append("possibly_same_person")
                h["match"] = {"confidence": m["confidence"], "method": m["method"], "status": m["status"]}
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


# ---------- theme (expertise map) ----------

def for_theme(owner: str, theme_list: list[str], limit: int = 8, g: Graph | None = None) -> list[dict]:
    g = g or graph.load(owner)
    paths = graph.reach(g)
    best: dict[str, tuple[float, dict]] = {}
    for r in repo.people_with_theme(owner, theme_list, 200):
        if r["person_id"] not in paths:
            continue
        cur = best.get(r["person_id"])
        if not cur or r["weight"] > cur[0]:
            best[r["person_id"]] = (r["weight"], r)
    hits = []
    for pid, (w, r) in best.items():
        path = paths[pid]
        wm, last = graph.warmth(g, pid, path)
        label = themes.THEMES.get(r["theme"], r["theme"])
        whys = [{"text": f"{label}: {r['evidence']}", "provenance": "declared" if r["method"] == "declared" else "derived"}]
        if last:
            whys.append({"text": f"Last spoke {last}", "provenance": g.people[pid]["provenance"]})
        expl = f"{g.people[pid]['full_name']} — {label}: {r['evidence']}. {_how_known(g, path)}"
        hits.append(_hit(g, pid, path, w * path["strength"] * wm, whys, expl))
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


# ---------- employer lookup ("who previously worked at Tata Motors?") ----------

def for_employer(owner: str, org_id: str, current: bool | None = None, limit: int = 10,
                 g: Graph | None = None) -> list[dict]:
    g = g or graph.load(owner)
    paths = graph.reach(g)
    org = orgs.get(org_id) or {"name": "?"}
    hits = []
    for e in repo.contacts_at_orgs(owner, [org_id]):
        is_cur = e.get("is_current") == 1 or (e.get("end_year") is None and bool(e.get("start_year")))
        if current is True and not is_cur or current is False and is_cur:
            continue
        pid = e["person_id"]
        if pid not in paths:
            continue
        path = paths[pid]
        wm, last = graph.warmth(g, pid, path)
        whys = [{"text": f"{e.get('title') or 'Worked'} at {org['name']} ({_span(e)})", "provenance": e["provenance"]}]
        if last:
            whys.append({"text": f"Last spoke {last}", "provenance": g.people[pid]["provenance"]})
        flags = ["mnpi"] if is_cur and org.get("symbol") else []
        expl = f"{g.people[pid]['full_name']} — {whys[0]['text']}. {_how_known(g, path)}"
        hits.append(_hit(g, pid, path, path["strength"] * wm * SENIORITY_WEIGHT.get(e.get("seniority") or "", 0.9),
                         whys, expl, flags))
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


# ---------- what to ask them (from FINN's own primary-source research) ----------

FUNCTION_TOPICS = {
    "finance": ("cash_quality", "balance_sheet"),
    "operations": ("trajectory",),
    "leadership": ("trajectory", "balance_sheet"),
    "sales": ("trajectory",),
    "strategy": ("trajectory",),
}


def questions(symbol: str, functions: list[str], limit: int = 3) -> list[str]:
    """Questions grounded in what FINN found in the company's own documents: guidance management missed
    or that can't be verified, and the observations its statements raised. No model call."""
    out: list[str] = []
    for r in db.query("SELECT metric, target_text, due_period, outcome FROM promises WHERE symbol = ? "
                      "AND outcome IN ('Missed', 'Can''t verify') ORDER BY updated_at DESC LIMIT 4", (symbol,)):
        detail = r["metric"].replace("_", " ")
        verb = "missed" if r["outcome"] == "Missed" else "couldn't be checked against reported numbers"
        out.append(f"Management guided {detail} of {r['target_text']} for {r['due_period']}, and it {verb}. What happened?")
    sec = db.query_one("SELECT payload_json FROM research WHERE symbol = ? AND section = 'financials'", (symbol,))
    if sec:
        import json
        obs = json.loads(sec["payload_json"]).get("observations", {})
        keys = []
        for f in functions or ["leadership"]:
            keys += [k for k in FUNCTION_TOPICS.get(f, ("trajectory",)) if k not in keys]
        for k in keys:
            for line in obs.get(k, [])[:1]:
                out.append(f"FINN's read of the statements: “{line}” Does that match what they saw inside?")
    return out[:limit]
