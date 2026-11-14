"""The only module that reads or writes an investor's private network rows.

Every function takes `owner` and filters by it. A person is visible to an owner when it is theirs
(their contacts and their own 'self' node) or public (disclosed in an exchange filing, owner_id NULL).
Keep it that way: isolation tests call every public function here with a second investor.
"""
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta

from app.config import IST, settings
from app.database import db
from app.network.names import norm_person

VISIBLE = "(p.owner_id = ? OR p.owner_id IS NULL)"


# ---------- investors ----------

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ensure_investor(investor_id: str, display_name: str, self_name: str = "You") -> dict:
    inv = db.query_one("SELECT * FROM investors WHERE id = ?", (investor_id,))
    if inv:
        return inv
    pid = "self:" + investor_id
    now = db.now_iso()
    with db.tx() as c:
        c.execute("INSERT INTO investors(id, display_name, self_person_id, retention_days, created_at) "
                  "VALUES (?, ?, ?, ?, ?)", (investor_id, display_name, pid, settings.network_retention_days, now))
        c.execute("INSERT INTO people(id, owner_id, kind, full_name, name_norm, provenance, consent_basis, "
                  "created_at, updated_at) VALUES (?, ?, 'self', ?, ?, 'user_entered', 'self', ?, ?)",
                  (pid, investor_id, self_name, norm_person(self_name), now, now))
    return db.query_one("SELECT * FROM investors WHERE id = ?", (investor_id,))


def issue_token(investor_id: str) -> str:
    """A new bearer token for an investor. Only its hash is stored."""
    token = secrets.token_urlsafe(32)
    db.execute("UPDATE investors SET token_hash = ? WHERE id = ?", (hash_token(token), investor_id))
    return token


def investor_by_token(token: str) -> dict | None:
    return db.query_one("SELECT * FROM investors WHERE token_hash = ?", (hash_token(token),))


def investor(owner: str) -> dict | None:
    return db.query_one("SELECT * FROM investors WHERE id = ?", (owner,))


def self_id(owner: str) -> str:
    return "self:" + owner


def all_investor_ids() -> list[str]:
    return [r["id"] for r in db.query("SELECT id FROM investors")]


# ---------- people ----------

def person(owner: str, pid: str) -> dict | None:
    return db.query_one(f"SELECT p.* FROM people p WHERE p.id = ? AND {VISIBLE}", (pid, owner))


def people_by_ids(owner: str, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    return {r["id"]: r for r in db.query(f"SELECT p.* FROM people p WHERE p.id IN ({q}) AND {VISIBLE}", (*ids, owner))}


def contacts(owner: str, q: str | None = None, limit: int = 500) -> list[dict]:
    sql = "SELECT p.* FROM people p WHERE p.owner_id = ? AND p.kind = 'contact'"
    params: list = [owner]
    if q:
        sql += " AND (p.name_norm LIKE ? OR LOWER(COALESCE(p.headline,'')) LIKE ?)"
        params += [f"%{norm_person(q)}%", f"%{q.lower()}%"]
    sql += " ORDER BY p.full_name LIMIT ?"
    return db.query(sql, (*params, limit))


def contacts_named(owner: str, name_norm: str) -> list[dict]:
    return db.query("SELECT * FROM people WHERE owner_id = ? AND kind = 'contact' AND name_norm = ?", (owner, name_norm))


def contact_ids(owner: str) -> list[str]:
    return [r["id"] for r in db.query("SELECT id FROM people WHERE owner_id = ? AND kind IN ('contact','self')", (owner,))]


def create_contact(owner: str, data: dict) -> dict:
    inv = investor(owner)
    now = datetime.now(IST)
    pid = "p:" + uuid.uuid4().hex[:16]
    expires = (now + timedelta(days=(inv or {}).get("retention_days") or settings.network_retention_days))
    db.execute(
        "INSERT INTO people(id, owner_id, kind, full_name, name_norm, headline, location, provenance, notes, "
        "last_interaction_at, consent_basis, expires_at, created_at, updated_at) "
        "VALUES (?, ?, 'contact', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (pid, owner, data["full_name"].strip(), norm_person(data["full_name"]), data.get("headline"),
         data.get("location"), data.get("provenance", "user_entered"), data.get("notes"),
         data.get("last_interaction_at"), data.get("consent_basis", "investor_attested"),
         expires.isoformat(timespec="seconds"), db.now_iso(), db.now_iso()))
    return person(owner, pid)


def update_contact(owner: str, pid: str, fields: dict) -> dict | None:
    allowed = {k: v for k, v in fields.items() if k in ("headline", "location", "notes", "last_interaction_at")}
    if not allowed:
        return person(owner, pid)
    sets = ", ".join(f"{k} = ?" for k in allowed)
    n = db.execute(f"UPDATE people SET {sets}, updated_at = ? WHERE id = ? AND owner_id = ? AND kind = 'contact'",
                   (*allowed.values(), db.now_iso(), pid, owner))
    return person(owner, pid) if n else None


def delete_contact(owner: str, pid: str) -> bool:
    return db.execute("DELETE FROM people WHERE id = ? AND owner_id = ? AND kind = 'contact'", (pid, owner)) > 0


def purge_expired() -> int:
    return db.execute("DELETE FROM people WHERE owner_id IS NOT NULL AND kind = 'contact' AND expires_at IS NOT NULL "
                      "AND expires_at < ?", (db.now_iso(),))


def delete_all(owner: str) -> dict:
    """Right to erasure: every private row for this investor (people cascade to histories)."""
    out = {}
    with db.tx() as c:
        for t in ("network_insights", "person_matches", "relationships"):
            out[t] = c.execute(f"DELETE FROM {t} WHERE owner_id = ?", (owner,)).rowcount
        out["people"] = c.execute("DELETE FROM people WHERE owner_id = ? AND kind = 'contact'", (owner,)).rowcount
    return out


# ---------- histories (visibility enforced through the person) ----------

def _rows_for(table: str, owner: str, ids: list[str], extra_cols: str = "") -> list[dict]:
    if not ids:
        return []
    q = ",".join("?" * len(ids))
    return db.query(
        f"SELECT t.*, o.name AS org_name, o.symbol, o.sector, o.kind AS org_kind, o.size_bucket{extra_cols} "
        f"FROM {table} t JOIN people p ON p.id = t.person_id JOIN organizations o ON o.id = t.org_id "
        f"WHERE t.person_id IN ({q}) AND {VISIBLE}", (*ids, owner))


def employments(owner: str, ids: list[str]) -> list[dict]:
    return _rows_for("employments", owner, ids)


def educations(owner: str, ids: list[str]) -> list[dict]:
    return _rows_for("educations", owner, ids)


def expertise(owner: str, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    q = ",".join("?" * len(ids))
    return db.query(f"SELECT e.* FROM expertise e JOIN people p ON p.id = e.person_id "
                    f"WHERE e.person_id IN ({q}) AND {VISIBLE} ORDER BY e.weight DESC", (*ids, owner))


def add_employment(owner: str, pid: str, org_id: str, **f) -> None:
    if not person(owner, pid):
        raise PermissionError("Not your contact")
    db.execute("INSERT INTO employments(person_id, org_id, title, function, seniority, start_year, end_year, "
               "is_current, provenance, evidence, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (pid, org_id, f.get("title"), f.get("function"), f.get("seniority"), f.get("start_year"),
                f.get("end_year"), f.get("is_current"), f.get("provenance", "user_entered"), f.get("evidence"),
                f.get("confidence", 1.0)))


def add_education(owner: str, pid: str, org_id: str, **f) -> None:
    if not person(owner, pid):
        raise PermissionError("Not your contact")
    db.execute("INSERT INTO educations(person_id, org_id, degree, field, start_year, end_year, provenance, evidence, "
               "confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (pid, org_id, f.get("degree"), f.get("field"), f.get("start_year"), f.get("end_year"),
                f.get("provenance", "user_entered"), f.get("evidence"), f.get("confidence", 1.0)))


def set_expertise(owner: str, pid: str, theme: str, weight: float, method: str, evidence: str) -> None:
    if not person(owner, pid):
        raise PermissionError("Not your contact")
    # A declared theme is never overwritten by a derived one.
    db.execute("INSERT INTO expertise(person_id, theme, weight, method, evidence) VALUES (?, ?, ?, ?, ?) "
               "ON CONFLICT(person_id, theme) DO UPDATE SET weight = excluded.weight, evidence = excluded.evidence, "
               "method = excluded.method WHERE expertise.method = 'derived'",
               (pid, theme, max(0.0, min(1.0, weight)), method, evidence))


def people_with_theme(owner: str, themes: list[str], limit: int = 50) -> list[dict]:
    if not themes:
        return []
    q = ",".join("?" * len(themes))
    return db.query(f"SELECT e.person_id, e.theme, e.weight, e.method, e.evidence FROM expertise e "
                    f"JOIN people p ON p.id = e.person_id WHERE p.owner_id = ? AND p.kind = 'contact' "
                    f"AND e.theme IN ({q}) ORDER BY e.weight DESC LIMIT ?", (owner, *themes, limit))


def theme_counts(owner: str) -> list[dict]:
    return db.query("SELECT e.theme, COUNT(*) n, MAX(e.weight) top FROM expertise e JOIN people p ON p.id = e.person_id "
                    "WHERE p.owner_id = ? AND p.kind = 'contact' AND e.weight >= 0.3 GROUP BY e.theme "
                    "ORDER BY n DESC", (owner,))


def contacts_at_orgs(owner: str, org_ids: list[str]) -> list[dict]:
    """Employment rows of the owner's contacts at any of these organisations."""
    if not org_ids:
        return []
    q = ",".join("?" * len(org_ids))
    return db.query(f"SELECT e.*, o.name AS org_name, o.symbol, o.sector, o.size_bucket FROM employments e "
                    f"JOIN people p ON p.id = e.person_id JOIN organizations o ON o.id = e.org_id "
                    f"WHERE p.owner_id = ? AND p.kind = 'contact' AND e.org_id IN ({q})", (owner, *org_ids))


def public_figures_at(org_id: str) -> list[dict]:
    """People disclosed in filings as working at (or joining/leaving) an organisation. Public data."""
    return db.query("SELECT p.*, e.title, e.start_year, e.end_year FROM people p JOIN employments e ON e.person_id = p.id "
                    "WHERE p.owner_id IS NULL AND e.org_id = ? ORDER BY p.updated_at DESC", (org_id,))


# ---------- relationships ----------

def relationships(owner: str) -> list[dict]:
    return db.query("SELECT * FROM relationships WHERE owner_id = ?", (owner,))


def add_relationship(owner: str, from_id: str, to_id: str, kind: str, strength: int, context: str | None = None,
                     last_interaction_at: str | None = None, provenance: str = "user_entered") -> dict:
    vis = people_by_ids(owner, [from_id, to_id])
    if len(vis) != len({from_id, to_id}) or any(v["owner_id"] != owner for v in vis.values()):
        raise PermissionError("Relationships can only join your own contacts")
    db.execute("INSERT INTO relationships(owner_id, from_person_id, to_person_id, kind, strength, context, "
               "last_interaction_at, provenance, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (owner, from_id, to_id, kind, strength, context, last_interaction_at, provenance, db.now_iso()))
    return db.query_one("SELECT * FROM relationships WHERE owner_id = ? AND from_person_id = ? AND to_person_id = ? "
                        "AND kind = ?", (owner, from_id, to_id, kind))


def delete_relationship(owner: str, rel_id: int) -> bool:
    return db.execute("DELETE FROM relationships WHERE id = ? AND owner_id = ?", (rel_id, owner)) > 0


# ---------- entity-resolution decisions ----------

def upsert_match(owner: str, public_id: str, contact_id: str, confidence: float, method: str) -> None:
    db.execute("INSERT INTO person_matches(owner_id, public_person_id, contact_person_id, confidence, method) "
               "VALUES (?, ?, ?, ?, ?) ON CONFLICT(owner_id, public_person_id, contact_person_id) DO UPDATE SET "
               "confidence = excluded.confidence, method = excluded.method WHERE person_matches.status = 'suggested'",
               (owner, public_id, contact_id, confidence, method))


def matches_for(owner: str, public_id: str) -> list[dict]:
    return db.query("SELECT m.*, p.full_name AS contact_name FROM person_matches m JOIN people p "
                    "ON p.id = m.contact_person_id WHERE m.owner_id = ? AND m.public_person_id = ? "
                    "AND m.status != 'rejected' ORDER BY m.confidence DESC", (owner, public_id))


def decide_match(owner: str, public_id: str, contact_id: str, status: str) -> bool:
    return db.execute("UPDATE person_matches SET status = ?, decided_at = ? WHERE owner_id = ? AND public_person_id = ? "
                      "AND contact_person_id = ?", (status, db.now_iso(), owner, public_id, contact_id)) > 0


# ---------- insights ----------

def save_insight(owner: str, kind: str, subject_type: str, subject_id: str, person_id: str, score: float,
                 payload: dict) -> None:
    db.execute("INSERT INTO network_insights(owner_id, kind, subject_type, subject_id, person_id, score, payload_json, "
               "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(owner_id, kind, subject_id, person_id) DO UPDATE "
               "SET score = excluded.score, payload_json = excluded.payload_json",
               (owner, kind, subject_type, subject_id, person_id, score, json.dumps(payload), db.now_iso()))


def insights(owner: str, kind: str | None = None, subject_ids: list[str] | None = None,
             include_dismissed: bool = False) -> list[dict]:
    sql = "SELECT * FROM network_insights WHERE owner_id = ?"
    params: list = [owner]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if subject_ids is not None:
        if not subject_ids:
            return []
        sql += f" AND subject_id IN ({','.join('?' * len(subject_ids))})"
        params += subject_ids
    if not include_dismissed:
        sql += " AND dismissed_at IS NULL"
    rows = db.query(sql + " ORDER BY score DESC", tuple(params))
    for r in rows:
        r["payload"] = json.loads(r.pop("payload_json"))
    return rows


def clear_insights(owner: str, kind: str, subject_id: str | None = None) -> None:
    if subject_id is None:
        db.execute("DELETE FROM network_insights WHERE owner_id = ? AND kind = ? AND dismissed_at IS NULL", (owner, kind))
    else:
        db.execute("DELETE FROM network_insights WHERE owner_id = ? AND kind = ? AND subject_id = ? "
                   "AND dismissed_at IS NULL", (owner, kind, subject_id))


def dismiss_insight(owner: str, insight_id: int) -> bool:
    return db.execute("UPDATE network_insights SET dismissed_at = ? WHERE id = ? AND owner_id = ?",
                      (db.now_iso(), insight_id, owner)) > 0


def counts(owner: str) -> dict:
    return {
        "contacts": db.query_one("SELECT COUNT(*) n FROM people WHERE owner_id = ? AND kind = 'contact'", (owner,))["n"],
        "relationships": db.query_one("SELECT COUNT(*) n FROM relationships WHERE owner_id = ?", (owner,))["n"],
        "organizations": db.query_one(
            "SELECT COUNT(DISTINCT e.org_id) n FROM employments e JOIN people p ON p.id = e.person_id "
            "WHERE p.owner_id = ?", (owner,))["n"],
    }
