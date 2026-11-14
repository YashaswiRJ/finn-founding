# Network intelligence

The Network answers "who do I know who can help me understand this", inside Push and Pull and on its own. This page
describes the data, how a person in a filing is linked to the investor's network, and how people are ranked.

## Principles

1. **The database establishes a connection; nothing else does.** A *known* link is a row in `relationships` the investor
   recorded. An *inferred* link is a career overlap computed from employment/education rows, shown with its evidence and
   a confidence, and never stored as a relationship.
2. **No model writes, explains or chooses people.** Explanations are templates over evidence. Private network data is
   never sent to a model; at most the investor's *question text* is, to turn it into a filter.
3. **Every fact carries its source:** `synthetic` (demo), `user_entered`, `filing` (with the sentence it came from),
   `inferred`, `declared` / `derived` (expertise).
4. **Quiet by default.** The Network appears on a filing only when it has a strong enough link (thresholds below).

## Data

| Table | Holds | Owner |
|---|---|---|
| `organizations`, `org_aliases` | Every company, university, ministry; aliases like `tata motors`, `tml`, `tatamotors` → TMPV | public |
| `org_relations` | Competitor / supplier / customer links (demo: curated, labelled synthetic). Same-sector listed peers count as competitors automatically | public |
| `people` (owner NULL) | People disclosed in filings, with `source_url` (PDF) and `source_ref` (announcement) | public |
| `people` (owner set) | The investor (`kind='self'`) and their contacts | private |
| `employments`, `educations` | Careers; `start_year`, `end_year`, `is_current`, `evidence`, `confidence` | via person |
| `expertise` | Theme weights, `declared` by the investor or `derived` from careers | via person |
| `relationships` | Known links with kind, strength 1–5, context, last interaction | private |
| `person_matches` | "Is this filing person one of my contacts?" suggestions and decisions | private |
| `network_insights` | Stored network views of filings and reconnect triggers; dismissable | private |

### The demo network

`backend/scripts/generate_network.py` writes `backend/seed/network_demo.json` deterministically (seed 2027): 29
hand-written anchors and 30 generated background contacts (59 people, 61 relationships). Anchors are written against
the real story lines in the current filings:

| Real event (filing) | Anchors whose careers overlap |
|---|---|
| Cipla's new Global Chief Technical Operating Officer (ex-BCG MD, ex-Glenmark) | Aditya Rao (Partner, BCG, now), Neha Bansal (ex-BCG), Rahul Deshpande (ex-Glenmark) |
| Cipla's new independent director (ex-CFO Castrol India; Bharat Forge board) | Meera Krishnan (ex-Castrol finance), Arjun Bhatia (Bharat Forge, now) |
| Wipro's new Americas CEO (ex-Birlasoft CEO, 28 years at Wipro) | Sunita Iyer (ex-Birlasoft), Prakash Menon (ex-Wipro) |
| HDFC Bank's head of business banking retires | Farhan Qureshi (HDFC Bank business banking 2010–2020) |
| NTPC's new government nominee director (Ministry of Power) | Anil Mathur (ex-Joint Secretary, Ministry of Power) |
| Portfolio and research companies | At least one former employee of TMPV, MARUTI, SUNPHARMA, CIPLA, HDFCBANK, LT, MTARTECH, SUZLON, HAL, BEL, TCS, SBIN, ITC, HINDUNILVR, TITAN… |
| Expertise map | Semiconductors, specialty chemicals, rural lending, EVs, pharma, power… |

Synthetic people only know other synthetic people. The generator refuses names that collide with real people in the
filings.

## From filing to profile

1. **Classify** (`classify.py`): management-change subcategories, plus a rule over title + detail for appointments and
   exits announced as press releases or generic filings (auditors, scrutinisers excluded). Chairman / CEO / MD / CFO /
   chief-x-officer / president → HIGH; re-appointments stay MEDIUM.
2. **Read people** (`filing_people.py`, no model): honorific + name per line ("Ms Rashmi Joshi", "Shri Diwakar Nath
   Misra", "Dr. C Jayakumar"), and "X appoints Y as Z" for press releases. SEBI table headers ("Reason for change viz.
   appointment, re-appointment, resignation…") are stripped first so they can't be read as what happened. A name counts
   only if a change verb is near it (signatories and quoted executives drop out). Variants fold together ("T. Sriraman"
   = "Sriraman T"). Role, effective date and background come from the same text. With an API key, the cheap model's
   reading in `enrich.py` is used instead and fed into the same profile step.
3. **Profile** (`profiles.py`): one public person per name per company (deterministic id). The filing company employment
   comes from the filing itself. The background becomes rows by rules (organisations recognised by alias or by shape —
   "… Limited", "University of …", "Ministry of …"; titles from "as X of Y"; years from "(2021–2026)", "since 2010",
   "joined … 1991", "for nearly 27 years"; board seats; current vs previous) or by Haiku, where every row's `evidence`
   must be found verbatim in the background or it is dropped. **Outside hires** ("joins Cipla from BCG") start at the
   effective date, so they never falsely overlap the hiring company's alumni. Internal promotions keep an open start.

Verified on 10 real filings (`backend/tests/fixtures/filings/`) and, on the live data, 14 filings with 0 failures.

## Entity resolution

- **People** (`names.norm_person`): lower-case, strip accents, honorifics (`mr ms dr shri smt …`), DIN brackets and
  punctuation; plus an initials key (`krithivasan|k`) for "K. Krithivasan" vs "Krithivasan K".
- **Filing person ↔ contact** (`resolve.py`): exact normalised name 0.70, initials key 0.50; +0.25 if they share an
  employer, +0.05 if both sides have dates there. ≥0.9 "very likely the same person", ≥0.6 "possibly", below that
  nothing. **Never merged automatically**; the investor confirms or rejects, and rejections are remembered.
- **Organisations** (`orgs.py`): exact alias → normalised name → NSE symbol → fuzzy ratio ≥ 0.92. Unknown employers
  are created by name so overlaps still work.

## Paths and overlaps

- **Reach** (`graph.reach`): best path from the investor to every contact over known edges, at most two hops.
  Strength = edge strength / 5; two hops multiply and decay by 0.85. A contact with no recorded relationship gets 0.4
  and a "strength not recorded" flag.
- **Overlap** (`graph.overlaps`), strongest first:

| Overlap | Confidence |
|---|---|
| Same employer, intersecting years | (0.45 + 0.1 × min(years, 3)) × size + 0.1 if same function, max 0.85 |
| Both currently at the same organisation | 0.45 × size (+0.1 same function) |
| One on the board, the other works there now | 0.50 × size |
| Same employer, dates don't establish an overlap | 0.25 × size |
| Same employer, different times | 0.12 × size |
| Likely batchmates (graduation ±1 year) | 0.60 |
| Same institution, overlapping years (±3) | 0.40 |
| Same alma mater | 0.18 |

Size factor: small 1.0, mid 0.85, large 0.6, unknown 0.75 — two people at a 600,000-person company probably never met.

## Ranking

`score = relevance × path strength × warmth`. Warmth: last spoke < 180 days 1.0, < 2 years 0.9, older 0.8, unknown 0.85.

| Target | Relevance |
|---|---|
| Company (who to call) | Former employee: e^(−years since left / 8) × seniority; current employee 0.9 (flag: current insider — context, not unpublished numbers); competitor 0.6, supplier/customer 0.55, group 0.5 (× decay); sector-theme expertise 0.4 × weight; crossed paths with someone in the company's recent filings 0.5 × overlap confidence |
| Person (who can get me to) | The person in your network → their path; otherwise each contact's best overlap with them, on top of the path to that contact |
| Theme (go-to people) | Expertise weight (declared, or derived: years at organisations whose sector maps to the theme × seniority, /10, max 1) |
| Employer (who worked at) | Path strength × warmth × seniority |

When the Network speaks (`insights.py`):
- On a filing with people: links with score ≥ 0.07.
- "Best placed to explain this": only material events — M&A, capex, litigation (and fund-raise or pledging when HIGH)
  — and only for a score ≥ 0.15, i.e. someone who worked at the company, a competitor or a supplier.
- On real data this puts a network line on 16 of 82 important filings, rather than on most of them.

**Reconnect:** contacts you haven't spoken to in 120 days whose current or former listed employer filed something
HIGH/MEDIUM in the last 21 days.

**Suggested questions** (Who to call): built from FINN's own primary-source research for that company — guidance it
missed or couldn't verify, and the observations its statements produced — matched to the contact's function, each
question given to one person only.

## Invariants (tested)

- Every edge in every returned path is a recorded relationship of this investor, or an overlap with evidence and a
  confidence in (0, 0.85].
- An investor never sees another investor's contacts, relationships, matches or insights.
- The seed snapshot contains only public people.
- A model-read career row whose evidence isn't in the filing is dropped.
