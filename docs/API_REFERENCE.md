# API reference

Base URL: `http://localhost:8000` locally, the Render URL in production. JSON everywhere. Errors are
`{"detail": "<message>"}` with the HTTP status (the web app shows `detail`).

**Who is asking.** Network endpoints need an investor: `Authorization: Bearer <token>`, or — with
`NETWORK_DEMO_MODE=true` (the default) — no header, which reads the synthetic demo investor. Push/Pull endpoints never
require sign-in; they add an owner-scoped `network` field only when an investor is identified.

## Health and identity

| Method | Path | Returns |
|---|---|---|
| GET | `/api/health` | `{ok, llm_configured, companies, snapshot, auto_refresh_minutes, network: {demo_mode, public_profiles}}` |
| GET | `/api/me` | `{investor_id, display_name, demo, consent_accepted_at, retention_days, contacts, relationships, organizations}` · 401 without an investor |
| GET | `/api/costs` | Model spend by purpose, cache hits, filings settled by rules |

## Portfolio, companies, market data

| Method | Path | Notes |
|---|---|---|
| GET | `/api/portfolio` | Companies with latest EOD stats and 7-day HIGH filing count |
| POST | `/api/portfolio` | `{symbol, in_portfolio=true}` · validated against Yahoo · 422 if unknown |
| DELETE | `/api/portfolio/{symbol}` | 404 if not in portfolio |
| GET | `/api/companies/search?q=` | Local companies first, then screener.in search |
| GET | `/api/market-data/{symbol}?sessions=130` | Daily bars + latest stats |
| POST | `/api/market-data/refresh?days=7&enrich=true` | Background refresh: prices → alerts → filings → reading → people |
| GET | `/api/refresh/status` | `{state, step, started_at, finished_at, errors}` |

## Filings (Push)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/announcements?hours=&since=&until=&symbols=&categories=&priorities=&limit=` | Filings with triage, summaries, cards; non-LOW items carry `network` |
| GET | `/api/announcements/{id}` | One filing, with `network` |
| GET | `/api/intelligence/digest?hours=24&symbols=&categories=&priorities=` | `{counts, must_read, worth_a_look, buried, freshness, network_summary: {reconnect: PersonHit[]}}`; must-read and worth-a-look items carry `network`, buried ones `null` |

Filing `card.people[]` (from the model or rules):
```json
{"name": "Vikram Janakiraman", "role": "Global Chief Technical Operating Officer, …", "change": "appointed",
 "effective": "2026-12-07", "background": "Mr Vikram Janakiraman brings around 30 years …",
 "background_source": "filing", "method": "rules", "person_id": "pf:343969931f18f084",
 "linkedin_search_url": "https://www.linkedin.com/search/results/people/?keywords=…"}
```

Filing `network`:
```json
{"people": [{"filing_person": {"name": "Vikram Janakiraman", "role": "…", "change": "appointed", "background_source": "filing"},
             "person_id": "pf:343969931f18f084",
             "hits": [PersonHit, …]}],
 "best_placed": PersonHit | null}
```

## Alerts

| Method | Path | Notes |
|---|---|---|
| GET | `/api/alerts?limit=&symbol=` | History + settings |
| GET/POST | `/api/alerts/settings` | Thresholds (price ±%, volume ×, categories, minimum priority); saving re-scans; 422 on out-of-range |
| POST | `/api/alerts/{id}/ack` | Mark read |

## Research (Pull)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/company/{symbol}` | Sections, documents, latest job. Any NSE ticker; old names resolve (`TATAMOTORS` → TMPV, response `company.symbol` says which) |
| POST | `/api/research/{symbol}/generate?force=` | Background job: statements → AR + transcripts → ledger → business → bull/bear |
| GET | `/api/research/jobs/{id}` · `/api/research/{symbol}` | Job steps · sections |
| POST | `/api/research/chat` | `{message, symbol?}` → `{intent: portfolio|move|numbers|documents|network, segments, cards, moves?, table?, people?, filter?, target?, basis, model?}` · rate-limited (30/min per IP) |
| POST | `/api/documents/upload` · `/api/documents/import` · GET `/api/documents/{symbol}` | Manual primary-source fallback (PDF ≤ 60 MB, https only) |

## Network

All require an investor (see top). Bodies are validated (lengths, enums, strength 1–5); 422 on invalid input.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/network/summary` | Counts, top themes (with top people), reconnect (3), people in recent filings |
| GET | `/api/network/people?q=&theme=&org=&limit=` | Contacts; or ranked people for a theme or employer |
| GET | `/api/network/people/{id}` | `PersonDetail`: career, education, expertise, relationships, paths, diligence notes, filing source, same-person suggestions · 404 if not yours and not public |
| POST | `/api/network/people` | Add a contact. `attest: true` required (422 otherwise). Same name as an existing contact → `{created: false, duplicates_warning}` unless `allow_duplicate` |
| PATCH | `/api/network/people/{id}` | `headline, location, notes, last_interaction_at` |
| DELETE | `/api/network/people/{id}` | Hard delete (histories cascade) |
| POST | `/api/network/relationships` | `{to_person_id, from_person_id?=self, kind, strength, context?, last_interaction_at?}` · 404 if either person isn't yours · 409 duplicate |
| DELETE | `/api/network/relationships/{id}` | |
| GET | `/api/network/paths?to={person_id}` | Ranked ways to reach a person |
| GET | `/api/network/company/{symbol}/contacts?limit=5` | Who to call, with `suggested_questions`; `theme_fallback` when nobody connects; `in_the_news` |
| GET | `/api/network/announcement/{id}` | The `network` view of one filing |
| GET | `/api/network/expertise` | Every theme with its top people |
| GET | `/api/network/reconnect?days=120` | Keep-warm suggestions |
| POST | `/api/network/query` | `{q}` → `{filter, target, people, summary, basis}` · rate-limited |
| POST | `/api/network/matches/{public_id}/{contact_id}` | `{status: confirmed|rejected}` |
| POST | `/api/network/insights/{id}/dismiss` | Hide a suggestion |
| DELETE | `/api/network/me/data` | Erase every private network row for this investor |

`PersonHit` — one ranked person with the reason:
```json
{"person": {"id": "p:…", "full_name": "Aditya Rao", "headline": "Partner, BCG (operations & industrial goods)",
            "kind": "contact", "provenance": "synthetic"},
 "score": 0.147, "degree": 2,
 "path": [{"id": "self:demo", "name": "You"},
          {"id": "p:…", "name": "Neha Bansal", "edge": {"kind": "classmate", "label": "Classmate", "strength": 4,
                                                       "provenance": "synthetic", "context": "IIM Ahmedabad, PGP 2016", "known": true}},
          {"id": "p:…", "name": "Aditya Rao", "edge": {"kind": "former_colleague", "label": "Former colleague", "known": true, …}},
          {"id": "pf:…", "name": "Vikram Janakiraman", "edge": {"kind": "overlap", "label": "Inferred overlap", "known": false,
                                                              "confidence": 0.27, "evidence": "Both currently at Boston Consulting Group",
                                                              "provenance": "inferred"}}],
 "why": [{"text": "Both currently at Boston Consulting Group: …", "provenance": "inferred", "confidence": 0.27}],
 "explanation": "You don't know Vikram Janakiraman. Both currently at Boston Consulting Group. … verify before relying on it.",
 "flags": ["inferred"],
 "suggested_questions": []}
```
Flags: `mnpi` (current insider), `inferred`, `possibly_same_person`, `unrecorded_strength`.

`POST /api/network/query` example:
```json
// request
{"q": "Who can connect me to Cipla's new chief technical operating officer?"}
// response
{"filter": {"kind": "person_at_company", "symbol": "CIPLA", "themes": [], "role": "chief technical operating officer",
            "employment": "any", "via": "rules", "organization": "Cipla"},
 "target": {"id": "pf:…", "full_name": "Vikram Janakiraman", "headline": "Global Chief Technical Operating Officer, …, Cipla"},
 "people": [PersonHit, …],
 "summary": "Vikram Janakiraman (…): 3 ways in through your network.",
 "basis": "Read by rules; results from your own network (59 contacts). No model saw your contacts."}
```

Compatibility: every change to existing endpoints is an added field, so an older web app keeps working.
