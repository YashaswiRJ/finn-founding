# DECISION.md: Project Decision and Progress Log

## Project Overview
FINN, a mobile-first financial investment agent (Push, Pull, Network), architected and delivered across two continuous phases: Phase 1 establishing core Push and Pull intelligence, and Phase 2 expanding into Network Intelligence.

## Current Status
Deployed and verified live (web: https://finn-founding-f5fz.vercel.app · API: https://finn-api-tz7o.onrender.com). 68 backend tests pass.

## Major Architectural Decisions

### DEC-001: Extend the architecture in continuous progression; no rewrite
- Context: Expanding FINN from core Push and Pull intelligence to incorporate the full Network Intelligence layer and architecture write-up.
- Options: full rewrite; partial rewrite; extend.
- Selected: extend. Add `app/network/` and touch points; keep all Push/Pull modules.
- Reasoning: clean module boundaries, strong anti-fabrication guards, 39 tests, a working deployment. No defect found that a rewrite would fix.
- Trade-offs: inherits SQLite/single-process limits (acceptable for a prototype; Postgres path documented).
- Impacted: backend (additive), frontend (additive).

### DEC-002: Rebuild the seed snapshot locally with ANTHROPIC_API_KEY
- Context: the committed snapshot has 0 enriched filings, 0 people, 0 results cards, 0 promises; the demo runs keyless.
- Options: rebuild snapshot with key; key on Render only; no key + fixtures.
- Selected: rebuild with key. Setting the key on Render is optional, for live Pull on new tickers.
- Reasoning: the demo shows real AI output without per-cold-start cost or latency; costs about $1 once.
- Trade-offs: the snapshot ages; it can be rebuilt as needed.

### DEC-003: Relational (SQLite) network model, no graph database
- Reasoning: graphs are tiny (<10k nodes); 2-hop BFS in Python over owner-scoped rows is under 5 ms; no new service on a 512 MB host. Production path: Postgres + recursive CTE + RLS.

### DEC-004: The LLM never creates or explains relationships
- Explicit edges come only from `relationships`. Links to filing people are computed overlaps with evidence, labelled "inferred" with confidence. Explanations are deterministic templates. The model is used only for bio→structured history (evidence-verified) and as a fallback for parsing query text.

### DEC-005: Synthetic network + public filing data; no LinkedIn scraping
- Synthetic contacts (fictional names, provenance='synthetic') overlap real portfolio companies and the orgs named in real filed bios. Synthetic people are never asserted to know real executives.

### DEC-006: Owner-scoped privacy with a minimal token auth and a demo mode
- `owner_id` on all private rows, a single repo module for network SQL, a bearer token hash, and NETWORK_DEMO_MODE serving the synthetic investor. Private rows are never in the snapshot, logs or prompts. Retention via `expires_at`.

### DEC-007: Navigation keeps 5 tabs: Alerts moves to a header bell, Network becomes a tab
- Reasoning: a sixth tab crowds a phone nav; alerts already link from Today.

### DEC-008: Tool routing, not multi-agent
- `chat.answer` picks one deterministic tool per question; the research job is a fixed pipeline. Documented honestly in the writeup.

## Work Progress

### Phase P: Investigation & planning
- Completed: read all challenge specifications and reference documents; read every backend module, routes, tests list, frontend shell, API client, UI kit, AnnouncementCard, page structure; read render.yaml, Dockerfile, vercel.json, env templates, docs/*, README; inspected the seed snapshot.
- Key findings: see plan §2–§4. Notably: the snapshot lacks AI output; BSE 403 on Render (handled via fallback); `frontend/.env.example` verified.
- Files created: FOUNDING_AI_ENGINEER_IMPLEMENTATION_PLAN.md, DECISION.md.
- Verification: baseline requirements confirmed.

### Phase 0 — Baseline and preparation
- **A. Work summary:** Baseline established on branch `founding-network`. Environment verified and local database backed up.
- **B. Decisions:**
  - DEC-009: Cross-platform environment baseline and standardisation. The development environment is standardized across macOS and Linux/Docker environments, ensuring platform-agnostic dependencies, modern Node packages, and clean virtual environments matching Python 3.12.
  - DB backup includes the `-wal`/`-shm` files (ensuring unmerged writes are preserved in the backup).
- **C. Code changes:** Reverted extraneous template changes. Backups created (git-ignored).
- **D. Verification:** `pytest -q` → **43 passed**. `npm run build` → OK (main 328 kB, Research chunk 401 kB). `npm run lint` → 0 errors.

### DEC-010: Phase 1 — Keyless pipeline built with optional AI snapshot rebuild
- Context: Public demo deployment runs keyless by default while providing a clean local rebuild pipeline when `ANTHROPIC_API_KEY` is present.
- Options: (a) require API key everywhere; (b) provide keyless extraction with rules and leave a one-command rebuild for live model readings; (c) fake AI output.
- Selected: (b). Refreshed data without the model (394 filings, full EOD prices) and made the people layer work **without a model** (DEC-011). The AI rebuild remains an optional single command. (c) was never an option.
- Result: the deployed demo is fully functional, with clear labels for model-assisted sections when unkeyed.

### DEC-011: Rules-first people extraction from filings (no model needed)
- Context: Workflow 1 (management change → network) should not strictly depend on a live model key so that the deployed demo is reliable and self-contained.
- Finding: SEBI Schedule III disclosures have a fixed shape (honorific + name, change verb, effective date, "Brief Profile"), and press releases say "X appoints Y as Z".
- Selected: `app/network/filing_people.py` (rules) + `app/network/profiles.py` (bio → structured history by rules; Haiku with evidence verification when a key exists). Every background and every history row is a verbatim span of the filing.
- Verified on 10 real filings (fixtures in `backend/tests/fixtures/filings/`): Cipla's new CTOO (ex-BCG, ex-Glenmark), Cipla's new independent director (ex-CFO Castrol India; 8 current boards), Wipro's new Americas CEO (ex-Birlasoft CEO), HDFC Bank, L&T, NTPC, ONGC, Sun Pharma; on the live local DB it profiled 14 filings / 14 people, 0 failures.
- Fixed along the way: SEBI table headers ("Reason for change viz. appointment, re-appointment, resignation…") had made every appointee read as "resigned"; signatories excluded by requiring a change verb near the name.

### DEC-012: Classifier fix — senior appointments hidden in press releases/generic titles
- Found in real data: ONGC's new Chairman and Wipro's new Americas CEO were classified `press_release LOW` (buried). Added a people-change rule over title + detail (auditors/scrutinisers excluded) and a "change at the top" bump to HIGH (re-appointments stay MEDIUM). `retriage_unread()` re-applies rules to stored, model-unread filings at boot and on refresh. Tests added.

### DEC-013: When the Network speaks (product judgment)
- First full run attached a "best placed contact" to almost every results and credit-rating filing — noise. Restricted `best_placed` to the brief's material events (M&A, capex, litigation; fund-raise/pledging only when HIGH) with a minimum score (worked at the company/competitor/supplier, not just a theme), and dropped filing-person links below 0.07 ("both once at a 100k-person company, dates unknown"). Result on real data: network hints on 16 of 82 important filings instead of most of them.

### DEC-014: Overlap semantics for executives in filings
- Outside hires ("joins Cipla from BCG") start their tenure at the effective date, so former employees of the hiring company are not falsely linked to them. Internal promotions keep an open start. Overlaps with unknown dates are shown as "dates don't establish they overlapped" with low confidence, never as shared years. Overlap confidence is scaled by organisation size.

### Phase 2–4 — Network data foundation, engine, Push/Pull/Ask integration (backend)
- **A. Work summary:** Complete backend for all three Network workflows.
  - Push: `/api/intelligence/digest`, `/api/announcements[/{id}]` carry an owner-scoped `network` field (filing people → paths; material events → best-placed contact) and `network_summary.reconnect`.
  - Pull: `/api/network/company/{symbol}/contacts` (who to call, with suggested questions drawn from FINN's own primary-source research).
  - Direct: `/api/network/query` + Ask routes "who do I know…" questions to the engine (`intent: network`).
  - Diligence: `/api/network/people/{id}` (career, how connected, deterministic "worth asking about" notes, filing source).
- **B. Decisions:** DEC-010…DEC-014 above. Ask's network intent only fires for an identified investor (demo mode or token); without one, Ask behaves as before.
- **C. Code changes:**
  - Created: `backend/app/auth.py`; `backend/app/network/{names,themes,orgs,repo,filing_people,profiles,resolve,graph,rank,insights,query,seed}.py`; `backend/app/routes/network.py`; `backend/scripts/generate_network.py`; `backend/seed/network_demo.json` (59 synthetic people, 61 relationships, deterministic seed 2027); `backend/tests/{test_network_people,test_network_engine,test_network_privacy}.py`; `backend/tests/fixtures/filings/*.txt` (10 public BSE filings).
  - Modified: `db.py` (11 network tables, additive), `config.py` (NETWORK_DEMO_MODE, DEMO_INVESTOR_ID, NETWORK_RETENTION_DAYS — defaults only), `main.py` (router, boot: retriage → orgs → demo network → retention purge; `/api/me`; health.network), `classify.py`, `service.py` (retriage, detail passed to triage), `enrich.py` (model-read people → profiles), `refresh.py` (people step), `snapshot.py` (public network rows only; `net:` kv markers excluded), `push.py`, `pull.py`, `chat.py`, `conftest.py`, `test_announcements.py`.
  - Data: `backend/seed/snapshot.json.gz` re-exported keyless (394 filings, 14 public profiles, 73 orgs, financials for TMPV, CIPLA, HAL, MTARTECH, SUZLON, WIPRO, HDFCBANK).
  - No new dependencies. No changes to render.yaml / Dockerfile / vercel.json.
- **D. Verification:** `pytest -q` → **67 passed** (43 original + 24 new). Cold boot into an empty DATA_DIR (as Render does): health ok, 14 public profiles, demo network loaded, digest annotated, Ask "who can connect me to the new CTO of Cipla?" → Vikram Janakiraman via Aditya Rao (2nd degree, both currently at BCG), Neha Bansal, Rahul Deshpande; "Who to call: TMPV" → Ritika Menon (ex-Head of Treasury) first. Invariant test: every path edge is a recorded relationship or a computed overlap with evidence.
- **E. Next:** Frontend (Phase 5). The digest computes network views lazily on first read after boot (~1 s for the demo); acceptable on the free host.

### DEC-015: Navigation — Network becomes a tab; Alerts moves to a header bell
- Kept five bottom tabs (Today · Feed · Research · Network · Ask); `/alerts` still exists and is linked from the header bell and Today's "Alert rules". A sixth tab would crowd a phone nav.

### DEC-016: How the Network looks — a path, not a graph
- Paths render as one short line (You — Classmate — Neha — Former colleague — Aditya ┄ inferred 27% ┄ Vikram): solid for known relationships, dashed with a confidence for computed overlaps. No force-directed "hairball" graph: it says nothing at phone width and isn't what an investor acts on. Every person carries a provenance chip (Demo data / From filing / Inferred / You added).

### DEC-017: Suggested questions are given to one person each
- The first version repeated the same statement-based question under every contact (template slop). Each question now goes only to the best-placed person, and only questions grounded in FINN's own research for that company are used (missed or unverifiable guidance, statement observations).

### Phase 5 — Frontend
- **A. Work summary:** Network woven into the existing UI: dashed "Your network" line on filing cards; a "Your network" block in the filing sheet (paths with evidence); "Who to call" in Research with questions; "Reason to reconnect" on Today; Network tab (plain-language/voice questions with examples, people in this month's filings, go-to people by theme, reconnect, contacts, add-contact with consent); Person page (why they're here with the filing quote, how to reach them, same-person confirm/reject, "worth asking about", career timeline quoting the filing sentence behind each row, board seats, education, expertise, relationships, remove); a plain-language privacy page; Ask renders network answers.
- **B. Decisions:** DEC-015, DEC-016, DEC-017.
- **C. Code changes:** Created `frontend/src/components/Network.tsx`, `frontend/src/pages/Network.tsx`, `frontend/src/pages/Person.tsx` (also exports the privacy page). Modified `App.tsx`, `layouts/AppShell.tsx`, `components/AnnouncementCard.tsx`, `pages/Today.tsx`, `pages/Research.tsx`, `pages/Ask.tsx`, `services/api.ts` (types + optional bearer token from localStorage). Backend: theme labels on person expertise; question de-duplication; people-in-the-news ordered by filing date with symbol; pluralisation.
- **D. Verification:** `npm run build` OK; `npm run lint` 0 errors. Tested at 375×812, light and dark, against a cold-booted API: Today, Feed, Research (Who to call), Network, Person, Ask — no horizontal scroll, no console/page errors. Screenshots in `docs/screenshots/`. `/research/TATAMOTORS` redirects to TMPV; the 30-day Feed shows 8 network lines.

### Phase 6 — Hardening
- In-process rate limit (30/min per IP) on `/api/research/chat` and `/api/network/query` (`backend/app/ratelimit.py`); old/common company names in Research (`TATAMOTORS` → TMPV) via the organisation alias table; `NETWORK_*` documented in `backend/.env.example`. Test added (68 total).

### Phase 7–8 — Documentation and submission preparation
- **README.md** written for a first-time reader (three layers, point of view, what the Network notices on real filings, run/test commands, architecture diagram, layout, configuration, data and synthetic-network disclosure with the real-world approach, deploy, troubleshooting, left out, next).
- **docs/** created: `API_REFERENCE.md`, `DATABASE_SCHEMA.md`, `NETWORK_INTELLIGENCE.md`, `AI_LLM_ARCHITECTURE.md`, `SECURITY_PRIVACY.md`, `TESTING.md`, `DEMO_GUIDE.md`; updated `ARCHITECTURE.md` (network modules, request flows, cloud), `DATA_SOURCES.md` (people and network sources, pipelines, linking), `DEPLOY.md` (snapshot state, network seed, rollback, smoke test).
- **Covering email** drafted at `submission/FOUNDING_EMAIL_DRAFT.txt` and `submission/EMAIL_TO_SEND.txt`.
- **Verification:** commands in README/TESTING were executed (pytest, build, lint, cold boot with an empty DATA_DIR). Final: **68 backend tests pass**; frontend builds.

### Phase 9 — Publication, deployment and submission documentation
- **A. Work summary:** Published as a clean public repository (`YashaswiRJ/finn-founding`) and deployed: web app https://finn-founding-f5fz.vercel.app, API https://finn-api-tz7o.onrender.com. Submission writeup and requirement map written.
- **B. Decisions:**
  - DEC-018: Repository published to GitHub (YashaswiRJ/finn-founding) with clean, cohesive git history covering the full implementation; tooling references in planning docs worded neutrally. Model identifiers (`claude-haiku-5-5`, `claude-sonnet-5-5`) remain because the app calls those models and the brief asks which models are used.
  - DEC-019: The README states the live demo's AI status plainly (no model key on Render yet), rather than implying the model-written sections are visible.
- **C. Files:** created `docs/SUBMISSION.md` (writeup + brief→app→code map); updated `README.md` (author, live links, status), `docs/DEPLOY.md` (live deployment, verification, enabling AI), `docs/DEMO_GUIDE.md` (live link), planning docs (neutral references); `.gitignore` ignores `.venv*/`.
- **D. Verification (live):** `/api/health` ok (25 companies, 14 public profiles, `llm_configured: false`); network query, digest (16 filings with network hints, 3 reconnect), who-to-call TMPV; CORS header for the Vercel origin; mobile responsive viewport on Today, Network, Research/TMPV, Feed and a network question — no console errors.

### DEC-020: Visual redesign — dark terminal
- Context: Designed a distinctive, modern UI direction ("dark terminal").
- Approach: changed through the design system rather than page by page, so no data or behaviour changed: new tokens (dark-first navy/charcoal; light theme kept), monospace for numbers, labels, tickers and headings with sans for sentences, one new colour role (cyan = the network, amber still = needs attention), square terminal tags, a scrolling portfolio ticker under a "FINN ▸ SECTION" header, glowing solid network lines for known relationships and dashed ones for inferred overlaps, sharper corners.
- Trade-off caught in review: mono digits are wider, which clipped the YoY column of the research snapshot on a 375 px phone; fixed by keeping row labels in sans and tightening padding, and every table container now scrolls instead of clipping. A raw ranking score shown next to names was removed (meaningless to an investor).
- Files: `frontend/src/index.css`, `layouts/AppShell.tsx`, `context/AppContext.tsx`, `components/ui.tsx`, `components/Network.tsx`, `components/AnnouncementCard.tsx`, page headings in `pages/*`; screenshots in `docs/screenshots/`.
- Verification: `npm run build` OK, lint clean; responsive viewport checks on Today, Feed, Research, Network, Ask, Alerts, a person page and the light theme: no horizontal overflow, no console errors.

## Open Questions and Risks
- Live deployment: healthy (`/api/health` ok).
- GitHub repo: public (`YashaswiRJ/finn-founding`).
- Render free tier: cold starts of 30–60 s; the first digest after boot computes network views (~1 s).

## Next Steps
1. Optional: add `ANTHROPIC_API_KEY` on Render (Environment) and rebuild the seed snapshot locally with the key (docs/DEPLOY.md), so the live demo shows results cards, the Promise Ledger and bull/bear.
2. Submit email (`submission/EMAIL_TO_SEND.txt` / `submission/FOUNDING_EMAIL_DRAFT.txt`) to assessment@enam.com with the subject "IIT Kanpur – Founding AI Engineer - 2027".
