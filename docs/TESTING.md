# Testing

```bash
cd backend && pytest -q                     # 68 tests, ~5 s, no network access, no API key
cd frontend && npm run build && npm run lint  # type-check + production build; oxlint
```

## What the tests cover

| File | Area | Examples |
|---|---|---|
| `test_market_and_alerts.py` | Push arithmetic | returns vs previous close; 20-session volume excluding today; thresholds at boundaries; no duplicate alerts; provisional sessions; dead tickers |
| `test_announcements.py` | Classification and digest | results HIGH and read; routine paperwork never reaches the model; BSE critical flag; related filings fold; **senior appointments in press releases become management changes; re-appointments aren't "top" changes; auditor rotation isn't management** |
| `test_feed_fallback.py` | Data resilience | BSE refusal falls back to screener index without duplicates; a failure never erases the last success |
| `test_pull.py` | Pull grounding | Indian number formats; figures must be on the page; derived EBITDA; unit conversion; fabricated quotes rejected; period alignment; uncited bull/bear points dropped; chat routing without a model |
| `test_snapshot.py` | Seed data | round-trip; never overwrites live data |
| `test_network_people.py` | People in filings (10 real BSE filings in `fixtures/filings/`) | name normalisation; SEBI table headers don't flip appointments to resignations; outside hire vs press release; signatories and quoted executives excluded; multi-person promotions; date parsing |
| `test_network_engine.py` | Network engine (demo network + real filings) | career rows cite the filing; rules never invent organisations; model rows without evidence dropped; 2nd-degree path with inferred last hop; shared years beat unknown dates; outside hire not linked to the hiring company's alumni; **no invented links**; who-to-call ordering; current-insider flag; the five example questions parse by rules; insights stored per owner; reach ≤ 2 hops |
| `test_network_privacy.py` | Privacy and API boundary | investors can't see each other's contacts; matches suggested, never merged, rejections remembered; retention purge; erase-all; snapshot exports public people only; demo mode vs token vs 401; Push works without sign-in; attestation and duplicate warning; rate limit; TATAMOTORS → TMPV |

## Acceptance checks for the three workflows

| Workflow | Check |
|---|---|
| Push: management change → network | `GET /api/announcements/{cipla CTOO filing}` → `network.people[0].hits[0]` is Aditya Rao, degree 2, last edge `overlap` with evidence |
| Push: material event → best placed | an M&A filing at Cipla → `network.best_placed` = Sameer Kulkarni (ex-Cipla BD) |
| Pull: who to call | `GET /api/network/company/TMPV/contacts` → Ritika Menon first; supplier and competitor reasons present |
| Direct | "Who previously worked at Tata Motors?" → exactly Ritika Menon; "…semiconductor manufacturing?" → Ananya Sharma / Siddharth Rao |

## Manual mobile check (done for this release, 375 × 812, light and dark)

Today, Feed, Research (Who to call), Network (ask, themes, reconnect, contacts), Person, Ask: no horizontal scroll, no
console errors, loading skeletons, empty and error states present. Screenshots in `docs/screenshots/`. Reproduce with
Playwright (in `requirements-dev.txt`): `python -m playwright install chromium`, run the API and `npm run dev`, then
capture `http://localhost:5173/...` at a 375 px viewport.

## Cold-boot check (what Render does on every restart)

```bash
cd backend && DATA_DIR=$(mktemp -d) uvicorn app.main:app --port 8000
curl localhost:8000/api/health        # ok, companies 25, network.public_profiles > 0
```
