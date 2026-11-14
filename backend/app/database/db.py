"""SQLite persistence.

Plain SQL behind small repository functions keeps a later move to Postgres mechanical:
everything except the FTS5 table (search, see rag/) is portable SQL.
"""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from app.config import IST, settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    symbol TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT,
    size_bucket TEXT,
    bse_code TEXT,
    bse_url TEXT,
    in_portfolio INTEGER NOT NULL DEFAULT 0,
    is_research_pick INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, adj_close REAL,
    volume INTEGER,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS fetch_log (
    source TEXT NOT NULL,
    key TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    ok INTEGER NOT NULL,
    detail TEXT,
    last_ok_at TEXT,
    PRIMARY KEY (source, key)
);

CREATE TABLE IF NOT EXISTS announcements (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT,
    bse_category TEXT,
    bse_subcategory TEXT,
    published_at TEXT NOT NULL,
    source TEXT NOT NULL,
    filing_page_url TEXT,
    pdf_url TEXT,
    category TEXT,
    category_confidence REAL,
    category_method TEXT,
    priority TEXT,
    priority_score REAL,
    priority_reason TEXT,
    summary_json TEXT,
    card_json TEXT,
    enriched_at TEXT,
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ann_time ON announcements(published_at);
CREATE INDEX IF NOT EXISTS ix_ann_symbol ON announcements(symbol, published_at);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    rule TEXT NOT NULL,
    value REAL,
    threshold REAL,
    details_json TEXT,
    created_at TEXT NOT NULL,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    UNIQUE (symbol, trade_date, rule)
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    period TEXT,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    published_at TEXT,
    pages INTEGER,
    chars INTEGER,
    text_quality TEXT,
    status TEXT NOT NULL,
    error TEXT,
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_docs_symbol ON documents(symbol, doc_type);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    page INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chunks_doc ON chunks(doc_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='rowid', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;

CREATE TABLE IF NOT EXISTS research (
    symbol TEXT NOT NULL,
    section TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (symbol, section)
);

CREATE TABLE IF NOT EXISTS promises (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    doc_id TEXT NOT NULL,
    page INTEGER NOT NULL,
    said_in TEXT NOT NULL,
    quote TEXT NOT NULL,
    metric TEXT NOT NULL,
    target_text TEXT NOT NULL,
    target_low REAL,
    target_high REAL,
    unit TEXT,
    due_period TEXT,
    outcome TEXT NOT NULL,
    actual_value REAL,
    actual_text TEXT,
    actual_source_json TEXT,
    explanation TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_promises_symbol ON promises(symbol);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    purpose TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    cache_hit INTEGER NOT NULL DEFAULT 0,
    batch INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    purpose TEXT NOT NULL,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- ---------------------------------------------------------------------------------------------
-- Network. Public rows (organisations, people disclosed in exchange filings) are shared; everything
-- an investor tells FINN about their own network carries owner_id and is only read through
-- app/network/repo.py, which always filters by owner.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS investors (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    token_hash TEXT UNIQUE,
    self_person_id TEXT,
    consent_accepted_at TEXT,
    retention_days INTEGER NOT NULL DEFAULT 730,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    name_norm TEXT NOT NULL UNIQUE,
    symbol TEXT,
    sector TEXT,
    kind TEXT NOT NULL CHECK (kind IN ('listed','private','university','government','other')),
    size_bucket TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_org_symbol ON organizations(symbol);

CREATE TABLE IF NOT EXISTS org_aliases (
    alias_norm TEXT PRIMARY KEY,
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS org_relations (
    org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    related_org_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('competitor','supplier','customer','group')),
    provenance TEXT NOT NULL,
    PRIMARY KEY (org_id, related_org_id, kind)
);

CREATE TABLE IF NOT EXISTS people (
    id TEXT PRIMARY KEY,
    owner_id TEXT REFERENCES investors(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('self','contact','public_figure')),
    full_name TEXT NOT NULL,
    name_norm TEXT NOT NULL,
    headline TEXT,
    location TEXT,
    provenance TEXT NOT NULL CHECK (provenance IN ('synthetic','user_entered','filing','public_dataset')),
    source_url TEXT,
    source_ref TEXT,
    notes TEXT,
    last_interaction_at TEXT,
    consent_basis TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_people_owner_name ON people(owner_id, name_norm);
CREATE INDEX IF NOT EXISTS ix_people_name ON people(name_norm);

CREATE TABLE IF NOT EXISTS employments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    org_id TEXT NOT NULL REFERENCES organizations(id),
    title TEXT,
    function TEXT,
    seniority TEXT,
    start_year INTEGER,
    end_year INTEGER,
    is_current INTEGER,                 -- 1 current, 0 past, NULL not stated (filings often give no dates)
    provenance TEXT NOT NULL,
    evidence TEXT,
    confidence REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS ix_emp_org ON employments(org_id, start_year, end_year);
CREATE INDEX IF NOT EXISTS ix_emp_person ON employments(person_id);

CREATE TABLE IF NOT EXISTS educations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    org_id TEXT NOT NULL REFERENCES organizations(id),
    degree TEXT,
    field TEXT,
    start_year INTEGER,
    end_year INTEGER,
    provenance TEXT NOT NULL,
    evidence TEXT,
    confidence REAL NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS ix_edu_org ON educations(org_id, end_year);
CREATE INDEX IF NOT EXISTS ix_edu_person ON educations(person_id);

CREATE TABLE IF NOT EXISTS expertise (
    person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    theme TEXT NOT NULL,
    weight REAL NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('declared','derived')),
    evidence TEXT NOT NULL,
    PRIMARY KEY (person_id, theme)
);
CREATE INDEX IF NOT EXISTS ix_expertise_theme ON expertise(theme, weight);

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL REFERENCES investors(id) ON DELETE CASCADE,
    from_person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    to_person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('knows','former_colleague','classmate','friend','met_at_event','family')),
    strength INTEGER NOT NULL CHECK (strength BETWEEN 1 AND 5),
    context TEXT,
    last_interaction_at TEXT,
    provenance TEXT NOT NULL CHECK (provenance IN ('synthetic','user_entered')),
    created_at TEXT NOT NULL,
    UNIQUE (owner_id, from_person_id, to_person_id, kind)
);
CREATE INDEX IF NOT EXISTS ix_rel_owner_from ON relationships(owner_id, from_person_id);
CREATE INDEX IF NOT EXISTS ix_rel_owner_to ON relationships(owner_id, to_person_id);

CREATE TABLE IF NOT EXISTS person_matches (
    owner_id TEXT NOT NULL REFERENCES investors(id) ON DELETE CASCADE,
    public_person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    contact_person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    confidence REAL NOT NULL,
    method TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'suggested' CHECK (status IN ('suggested','confirmed','rejected')),
    decided_at TEXT,
    PRIMARY KEY (owner_id, public_person_id, contact_person_id)
);

CREATE TABLE IF NOT EXISTS network_insights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL REFERENCES investors(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('filing_person','material_event','reconnect')),
    subject_type TEXT NOT NULL CHECK (subject_type IN ('announcement','company','person')),
    subject_id TEXT NOT NULL,
    person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    score REAL NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    dismissed_at TEXT,
    UNIQUE (owner_id, kind, subject_id, person_id)
);
CREATE INDEX IF NOT EXISTS ix_insights_owner ON network_insights(owner_id, kind, created_at);
"""

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def now_iso() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    """One shared connection; SQLite serialises writes and the app is single-process."""
    global _conn
    if _conn is None or path is not None:
        p = path or settings.db_path
        conn = sqlite3.connect(p, check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        _migrate(conn)
        _conn = conn
    return _conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive column changes for databases created by earlier versions."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(fetch_log)")}
    if "last_ok_at" not in cols:
        conn.execute("ALTER TABLE fetch_log ADD COLUMN last_ok_at TEXT")
        conn.execute("UPDATE fetch_log SET last_ok_at = fetched_at WHERE ok = 1")


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    conn = connect()
    with _lock:
        conn.execute("BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise


def query(sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
    with _lock:
        return [dict(r) for r in connect().execute(sql, params).fetchall()]


def query_one(sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | dict = ()) -> int:
    with _lock:
        cur = connect().execute(sql, params)
        return cur.rowcount


def kv_get(key: str, default: Any = None) -> Any:
    row = query_one("SELECT value FROM kv WHERE key = ?", (key,))
    return json.loads(row["value"]) if row else default


def kv_set(key: str, value: Any) -> None:
    execute(
        "INSERT INTO kv(key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, json.dumps(value), now_iso()),
    )


def log_fetch(source: str, key: str, ok: bool, detail: str | None = None) -> None:
    """A failure never erases when the source last worked, so freshness labels stay truthful."""
    t = now_iso()
    execute(
        "INSERT INTO fetch_log(source, key, fetched_at, ok, detail, last_ok_at) VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(source, key) DO UPDATE SET fetched_at = excluded.fetched_at, ok = excluded.ok, "
        "detail = excluded.detail, last_ok_at = COALESCE(excluded.last_ok_at, fetch_log.last_ok_at)",
        (source, key, t, int(ok), detail, t if ok else None),
    )


def last_fetch(source: str, key: str) -> dict[str, Any] | None:
    return query_one("SELECT * FROM fetch_log WHERE source = ? AND key = ?", (source, key))
