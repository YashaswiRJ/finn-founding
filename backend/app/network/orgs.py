"""Organisations: listed companies FINN tracks, plus employers, universities and ministries named in
profiles and filings. Resolution is deterministic (aliases, normalised names, a strict fuzzy fallback),
so "Tata Motors Ltd", "TATAMOTORS" and "TML" all land on the same organisation.
"""
import difflib
import re

from app.database import db
from app.network.names import norm_org, slug

# Common names for listed companies -> NSE symbol. TATAMOTORS no longer trades after the demerger;
# the passenger-vehicle successor TMPV kept its BSE code, so the old names resolve there.
CURATED_ALIASES: dict[str, str] = {
    "tata motors": "TMPV", "tatamotors": "TMPV", "tml": "TMPV", "tata motors passenger vehicles": "TMPV",
    "tcs": "TCS", "infosys": "INFY", "infy": "INFY", "wipro": "WIPRO",
    "hdfc bank": "HDFCBANK", "hdfcbank": "HDFCBANK", "icici bank": "ICICIBANK", "icici": "ICICIBANK",
    "sbi": "SBIN", "state bank": "SBIN", "state bank of india": "SBIN",
    "reliance": "RELIANCE", "ril": "RELIANCE", "reliance industries": "RELIANCE",
    "ongc": "ONGC", "oil and natural gas corporation": "ONGC", "ntpc": "NTPC",
    "maruti": "MARUTI", "maruti suzuki": "MARUTI", "itc": "ITC",
    "hul": "HINDUNILVR", "hindustan unilever": "HINDUNILVR",
    "sun pharma": "SUNPHARMA", "sun pharmaceutical": "SUNPHARMA", "sun pharmaceutical industries": "SUNPHARMA",
    "cipla": "CIPLA", "l and t": "LT", "lt": "LT", "larsen and toubro": "LT", "larsen": "LT",
    "airtel": "BHARTIARTL", "bharti airtel": "BHARTIARTL", "titan": "TITAN", "suzlon": "SUZLON",
    "mtar": "MTARTECH", "mtar technologies": "MTARTECH", "hal": "HAL", "hindustan aeronautics": "HAL",
    "bel": "BEL", "bharat electronics": "BEL", "asian paints": "ASIANPAINT", "coal india": "COALINDIA",
    "power grid": "POWERGRID", "powergrid": "POWERGRID", "power grid corporation": "POWERGRID",
}
# Aliases too short or too common to look for inside free text (they still resolve when given alone).
NOT_IN_TEXT = {"lt", "it", "hal", "bel", "tml", "ril", "icici", "larsen", "titan", "reliance"}


def org_id_for(name_norm: str) -> str:
    return "org:" + slug(name_norm)


def _add_alias(alias: str, org_id: str, source: str) -> None:
    a = norm_org(alias)
    if a:
        db.execute("INSERT OR IGNORE INTO org_aliases(alias_norm, org_id, source) VALUES (?, ?, ?)", (a, org_id, source))


def ensure_org(name: str, kind: str = "other", symbol: str | None = None, sector: str | None = None,
               size_bucket: str | None = None) -> str:
    """Return the organisation for `name`, creating it if FINN has never seen it."""
    if symbol:
        row = db.query_one("SELECT id FROM organizations WHERE symbol = ?", (symbol,))
        if row:
            return row["id"]
    found = resolve_org(name, fuzzy=False)
    if found:
        if sector or size_bucket:
            db.execute("UPDATE organizations SET sector = COALESCE(sector, ?), size_bucket = COALESCE(size_bucket, ?) "
                       "WHERE id = ?", (sector, size_bucket, found))
        return found
    n = norm_org(name)
    oid = org_id_for(n)
    db.execute(
        "INSERT OR IGNORE INTO organizations(id, name, name_norm, symbol, sector, kind, size_bucket, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (oid, name.strip(), n, symbol, sector, kind, size_bucket, db.now_iso()))
    _add_alias(name, oid, "self")
    return oid


def seed_from_companies() -> int:
    """Every company FINN tracks is also an organisation, with its symbol and common names as aliases."""
    n = 0
    for c in db.query("SELECT symbol, name, sector, size_bucket FROM companies"):
        oid = ensure_org(c["name"], "listed", c["symbol"], c["sector"], c["size_bucket"])
        db.execute("UPDATE organizations SET symbol = ?, kind = 'listed' WHERE id = ?", (c["symbol"], oid))
        _add_alias(c["symbol"], oid, "companies_table")
        _add_alias(c["name"], oid, "companies_table")
        n += 1
    by_symbol = {r["symbol"]: r["id"] for r in db.query("SELECT id, symbol FROM organizations WHERE symbol IS NOT NULL")}
    for alias, sym in CURATED_ALIASES.items():
        if sym in by_symbol:
            _add_alias(alias, by_symbol[sym], "curated")
    return n


def resolve_org(text: str, fuzzy: bool = True) -> str | None:
    """Exact alias -> normalised name -> NSE symbol -> strict fuzzy match (>= 0.92). None when unsure."""
    if not text or not text.strip():
        return None
    n = norm_org(text)
    if not n:
        return None
    row = db.query_one("SELECT org_id FROM org_aliases WHERE alias_norm = ?", (n,))
    if row:
        return row["org_id"]
    row = db.query_one("SELECT id FROM organizations WHERE name_norm = ?", (n,))
    if row:
        return row["id"]
    row = db.query_one("SELECT id FROM organizations WHERE symbol = ?", (text.strip().upper(),))
    if row:
        return row["id"]
    if fuzzy and len(n) >= 6:
        names = db.query("SELECT id, name_norm FROM organizations")
        best = max(names, key=lambda r: difflib.SequenceMatcher(None, n, r["name_norm"]).ratio(), default=None)
        if best and difflib.SequenceMatcher(None, n, best["name_norm"]).ratio() >= 0.92:
            return best["id"]
    return None


def orgs_in_text(text: str) -> list[str]:
    """Organisations named anywhere in free text, by alias or full normalised name. Longest names win
    so 'tata motors passenger vehicles' isn't also read as some shorter alias inside it."""
    low = " " + norm_org(text) + " "
    candidates = [(r["alias_norm"], r["org_id"]) for r in db.query("SELECT alias_norm, org_id FROM org_aliases")]
    candidates += [(r["name_norm"], r["id"]) for r in db.query("SELECT id, name_norm FROM organizations")]
    hits: list[tuple[int, str]] = []
    taken: list[tuple[int, int]] = []
    for alias, oid in sorted(set(candidates), key=lambda x: -len(x[0])):
        if len(alias) < 3 or alias in NOT_IN_TEXT:
            continue
        for m in re.finditer(rf" {re.escape(alias)} ", low):
            span = (m.start(), m.end())
            if any(a < span[1] and span[0] < b for a, b in taken):
                continue
            taken.append(span)
            hits.append((m.start(), oid))
    out: list[str] = []
    for _, oid in sorted(hits):
        if oid not in out:
            out.append(oid)
    return out


def get(org_id: str) -> dict | None:
    return db.query_one("SELECT * FROM organizations WHERE id = ?", (org_id,))


def for_symbol(symbol: str) -> dict | None:
    return db.query_one("SELECT * FROM organizations WHERE symbol = ?", (symbol.upper(),))


def related(org_id: str) -> list[dict]:
    """Competitors, suppliers and customers. Curated links first, then same-sector listed peers."""
    org = get(org_id)
    if not org:
        return []
    out = [dict(r) for r in db.query(
        "SELECT r.related_org_id AS org_id, r.kind, r.provenance, o.name FROM org_relations r "
        "JOIN organizations o ON o.id = r.related_org_id WHERE r.org_id = ? "
        "UNION SELECT r.org_id, CASE r.kind WHEN 'supplier' THEN 'customer' WHEN 'customer' THEN 'supplier' "
        "ELSE r.kind END, r.provenance, o.name FROM org_relations r JOIN organizations o ON o.id = r.org_id "
        "WHERE r.related_org_id = ?", (org_id, org_id))]
    seen = {r["org_id"] for r in out}
    if org.get("sector"):
        for r in db.query("SELECT id, name FROM organizations WHERE sector = ? AND id != ?", (org["sector"], org_id)):
            if r["id"] not in seen:
                out.append({"org_id": r["id"], "kind": "competitor", "provenance": "derived_sector", "name": r["name"]})
    return out
