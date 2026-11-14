import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import db  # noqa: E402


@pytest.fixture()
def fresh_db(tmp_path):
    db._conn = None
    db.connect(tmp_path / "test.sqlite3")
    yield db
    db._conn.close()
    db._conn = None


def make_bars(closes, volumes, start="2026-09-01"):
    from datetime import date, timedelta
    d0 = date.fromisoformat(start)
    return [{"date": (d0 + timedelta(days=i)).isoformat(), "open": c, "high": c, "low": c, "close": c,
             "adj_close": c, "volume": v} for i, (c, v) in enumerate(zip(closes, volumes))]


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "filings"

# (announcement id, symbol, fixture, title, detail) — real BSE filings, Oct-Nov 2026
REAL_FILINGS = [
    ("t-cipla-cto", "CIPLA", "CIPLA_cto.txt", "Announcement under Regulation 30 (LODR)-Change in Management",
     "Appointment of Mr Vikram Janakiraman, as the Global Chief Technical Operating Officer"),
    ("t-cipla-dir", "CIPLA", "CIPLA.txt", "Announcement under Regulation 30 (LODR)-Change in Directorate",
     "Appointment of Ms Rashmi Joshi as an additional and independent director"),
    ("t-wipro", "WIPRO", "WIPRO.txt", "Announcement under Regulation 30 (LODR)-Press Release / Media Release",
     "Wipro Appoints Angan Guha as President and Chief Executive Officer for Americas 2 Strategic Market Unit"),
    ("t-hdfc", "HDFCBANK", "HDFCBANK.txt", "Announcement under Regulation 30 (LODR)-Change in Management", ""),
    ("t-lt", "LT", "LT.txt", "Announcement under Regulation 30 (LODR)-Change in Management", ""),
    ("t-ntpc", "NTPC", "NTPC_dir.txt", "Announcement under Regulation 30 (LODR)-Change in Directorate", ""),
    ("t-ongc", "ONGC", "ONGC.txt", "Letter From Administrative Ministry Regarding Appointment Of Chairman", ""),
]


@pytest.fixture()
def demo_net(fresh_db):
    """Fresh DB with FINN's companies, the synthetic demo network, and the real filings profiled."""
    from app.network import orgs, profiles, seed
    from app.services import companies
    companies.seed_defaults()
    orgs.seed_from_companies()
    seed.load_demo_if_empty()
    for aid, sym, fx, title, detail in REAL_FILINGS:
        fresh_db.execute(
            "INSERT INTO announcements(id, symbol, title, detail, published_at, source, category, category_method, "
            "priority, priority_score, card_json, ingested_at) VALUES (?, ?, ?, ?, '2026-11-04T15:00:00+05:30', 'BSE', "
            "'management_change', 'rules', 'HIGH', 80, '{}', 'x')", (aid, sym, title, detail))
        a = fresh_db.query_one("SELECT * FROM announcements WHERE id = ?", (aid,))
        profiles.process_announcement(a, (FIXTURES / fx).read_text())
    return fresh_db
