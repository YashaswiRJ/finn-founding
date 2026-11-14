# Deploying FINN

## Live deployment

| Piece | URL | Host |
|---|---|---|
| Web app | https://finn-founding-f5fz.vercel.app | Vercel (root directory `frontend`, env `VITE_API_URL`) |
| API | https://finn-api-tz7o.onrender.com | Render free web service from `render.yaml` (Docker) |
| Repository | https://github.com/YashaswiRJ/finn-founding | GitHub (public); pushing `main` redeploys both |

Verified on 15 November 2026: `/api/health` ok with 25 companies and 14 public profiles; the BSE feed falls back to the
screener.in index on Render as designed; the digest carries network hints on 16 important filings with 3 reconnect
suggestions; "Who to call: TMPV" returns Ritika Menon first; CORS allows the Vercel origin; the web app loads Today,
Feed, Research and Network on a 375 px screen with no console errors, and answers "Who can connect me to Cipla's new
chief technical operating officer?". The API runs **without** `ANTHROPIC_API_KEY`, so model-written sections are
labelled off (see "Turning on the AI sections" below).

## Turning on the AI sections

1. Render dashboard → `finn-api` → **Environment** → add `ANTHROPIC_API_KEY` → **Save** (the service redeploys).
   New research jobs and filing reading then use the model live.
2. To ship model output in the seed (so the demo shows results cards, the Promise Ledger and bull/bear immediately
   after every cold start), rebuild the snapshot locally with the key (step 1 below), commit and push.


Two pieces: the API (Docker) and the web app (static). Each step that creates an account or pushes code is yours to run.

## 1. Build a seed snapshot (local)

Free hosts lose files when they restart, and BSE or Yahoo may refuse cloud IP addresses. A snapshot lets the deployed app show real, dated data immediately:

```bash
cd backend
source .venv/bin/activate
# With ANTHROPIC_API_KEY in backend/.env the snapshot carries AI readings, results cards, the ledger and bull/bear.
python scripts/build_snapshot.py --days 30 --research TMPV CIPLA MTARTECH HAL SUZLON
```

This writes `backend/seed/snapshot.json.gz`: prices, triaged filings with FINN's readings, alerts, research sections, the
ledger, organisations, and **people disclosed in filings** (public rows only). It contains no PDFs, no document text and
never the investor's network. Commit it with the code. Expect roughly $1 of model spend with a key; without one the
build still refreshes data and reads people by rules.

The demo network is a separate committed file, `backend/seed/network_demo.json`; regenerate it with
`python scripts/generate_network.py` (deterministic).

**State of the committed snapshot (15 Nov 2026):** built **without** a key (none was available during the build), so
the demo shows prices, rules triage, people and careers from filings, the Network and statement-based research; AI
summaries, results cards, the ledger and bull/bear appear after a rebuild with a key.

## 2. API on Render

1. Push the repository to GitHub.
2. Render dashboard → **New → Blueprint** → pick the repo. It reads `render.yaml`.
3. Set `ANTHROPIC_API_KEY` and `CORS_ORIGINS` (your Vercel URL) in the service's environment.
4. Wait for `/api/health` to return `{"ok": true}`.

Free Render instances sleep after inactivity; the first request after a sleep takes 30–60 s, and the app shows a "waking up" retry state. Their disk is wiped on restart, so the app re-boots from the seed snapshot each time.

**Memory.** Indexing a 300–400 page annual report with the local embedding model needs about 1 GB RAM and crashed the free 512 MB instance in testing. `render.yaml` therefore sets `VECTOR_SEARCH=false` (keyword retrieval only); with that setting a 414-page annual report indexes without trouble. On a host with ≥1 GB RAM, remove it to get hybrid retrieval back.

**What was verified on Render (3 Nov 2026):** Yahoo prices refresh; BSE's API refuses the host (403) and the filing feed falls back to the screener.in index automatically; screener.in statements and BSE-hosted PDFs download; research indexing completes.

## 3. Web app on Vercel

1. Vercel → **Add New Project** → the repo → root directory `frontend`.
2. Environment variable `VITE_API_URL` = your Render URL (e.g. `https://finn-api-tz7o.onrender.com`), no trailing slash.
3. Deploy. `vercel.json` handles client-side routes.

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | API | Enables AI reading, ledger, bull/bear, document Q&A |
| `MODEL_CHEAP` / `MODEL_STRONG` | API | Model routing (defaults: `claude-haiku-5-5`, `claude-sonnet-5-5`) |
| `CORS_ORIGINS` | API | Comma-separated allowed web origins |
| `AUTO_REFRESH_MINUTES` | API | Periodic refresh on hosts that stay awake; `0` = on demand |
| `DATA_DIR` | API | SQLite, PDF cache and vector index location (`/data` in Docker) |
| `VECTOR_SEARCH` | API | `false` on hosts under ~1 GB RAM: keyword retrieval only |
| `NETWORK_DEMO_MODE` | API | `true` (default): requests without a token read the synthetic demo network |
| `NETWORK_RETENTION_DAYS` | API | Contact retention (default 730) |
| `VITE_API_URL` | Web | API base URL |

No new services or variables are required for the Network: `render.yaml`, the Dockerfile and `vercel.json` are unchanged.

## Rollback

Every change is additive. To roll back, revert the commit and push; Render rebuilds from the previous image and the
previous snapshot comes back with it. Locally, keep a copy of `backend/data/finn.sqlite3` with its `-wal`/`-shm` files.

## Smoke test after deploying

`GET /api/health` → `ok: true`, `network.public_profiles > 0` · `GET /api/network/summary` → contacts 59 · open the
web app on a phone: Today loads, Network tab answers "Who previously worked at Tata Motors?".
