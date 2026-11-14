# Data sources

Checked from a residential connection in India on 3 November 2026; re-verified 15 November 2026 (394 filings to 14 Nov).

| Need | Source | Status | Notes |
|---|---|---|---|
| EOD price & volume | Yahoo Finance chart endpoint (`query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}.NS`) | Works | Same data `yfinance` wraps, called directly to avoid a dependency. `close` is split-adjusted, not dividend-adjusted, so bonus/split dates don't fire false alerts. Today's bar is ignored until 16:00 IST. |
| Corporate announcements | BSE `AnnSubCategoryGetData` API | Works per company | Rejects requests without an `Accept-Language` header. The all-company query returns nothing, so FINN queries each company. |
| Corporate announcements, from cloud hosts | screener.in company page (latest BSE filings: title, exact time, BSE PDF link) | Works | **BSE's API returns 403 to Render's servers** (tested 3 Nov 2026), while BSE's PDF host and screener.in answer. FINN falls back automatically and says so in the Feed ("via screener.in index"). Screener's own one-line summaries are not used. Only the 5 latest filings per company are listed, so the seed snapshot carries the 30-day history. |
| Corporate announcements | NSE `corporate-announcements` API | **403** | Refuses non-browser clients even with a cookie session. Not used; BSE carries the same filings. |
| Filing PDFs | `bseindia.com/stockinfo/AnnPdfOpen.aspx` | Works | Some results filings are scans with an OCR text layer (e.g. ICICI Bank). FINN detects this and reads the page visually. |
| BSE code for any NSE ticker | screener.in company page | Works | Lets research generalise to tickers FINN has never seen. |
| Reported financials | screener.in (quarterly, annual P&L, balance sheet, cash flow, ratios) | Works | Standardised from company filings. Consolidated preferred, standalone fallback, always labelled. Banks have no EBITDA; NPA ratios are published standalone only. |
| Annual reports, concall transcripts | Links on screener.in (hosted on BSE or the company's site) | Works | Primary documents. |
| Manual fallback | PDF upload or https link | Works | For companies or documents the automatic path misses. |
| People in filings | The filing PDF (BSE) — SEBI Schedule III requires name, reason, date and a brief profile for appointed directors and KMP | Works | Read by rules (`network/filing_people.py`); by the cheap model when keyed. Background text is the filing's own words. |
| The investor's network | What the investor records; the demo uses `backend/seed/network_demo.json` (synthetic) | Works | Never scraped. See [NETWORK_INTELLIGENCE.md](NETWORK_INTELLIGENCE.md). |

## Pipelines: fetch → store → link

| Pipeline | Trigger | Steps | Stored in |
|---|---|---|---|
| Prices | Refresh (header button, `AUTO_REFRESH_MINUTES`, or snapshot build) | Yahoo chart API per symbol → bars → alert scan | `prices`, `alerts` |
| Filings | Same refresh | BSE per company (screener index if refused) → de-duplicate by PDF → rules triage → announcement alerts → model reading of filings that need it (if keyed) | `announcements` |
| People | Same refresh, after reading | Management-change filings without people → PDF → rules (or the model's reading) → public person + career rows citing the filing → network views recomputed lazily | `people` (owner NULL), `employments`, `educations` |
| Research | On demand (`/api/research/{symbol}/generate`) | screener statements → AR + transcripts → page chunks → ledger → synthesis | `research`, `documents`, `chunks`, `promises` |
| Network | Investor input (demo: seed file at boot) | Contacts, careers, relationships → derived expertise | owner-scoped network tables |

**Linking a name in a filing to a person in the network:** names are normalised (honorifics, initials, punctuation) and
compared within the investor's contacts; a shared employer raises confidence; the investor confirms or rejects. Separately,
careers are compared organisation by organisation to find overlaps. Organisations are linked by aliases, normalised names
and NSE symbols, so "Tata Motors Ltd", "TML" and "TATAMOTORS" are one organisation. Details in
[NETWORK_INTELLIGENCE.md](NETWORK_INTELLIGENCE.md).

## Primary-source discipline (Pull side)

Used: the company's filings, annual reports, earnings-call transcripts, and reported statements.

Deliberately not used, although available on the same pages: screener.in's AI summaries of concalls and annual reports, its company "about" text, credit-agency pages, and any news. `robots.txt` disallows `/company/source/quarter/*`, so FINN never fetches it; results PDFs come from BSE instead.

## Demo universe

Portfolio (20): TCS, INFY, WIPRO, HDFCBANK, ICICIBANK, SBIN, RELIANCE, ONGC, NTPC, TMPV, MARUTI, ITC, HINDUNILVR, SUNPHARMA, CIPLA, LT, BHARTIARTL, TITAN, plus SUZLON (mid cap) and MTARTECH (small cap) for size diversity.

`TATAMOTORS.NS` no longer resolves after the Tata Motors demerger; TMPV (Tata Motors Passenger Vehicles) kept BSE code 500570 and stands in.

Research picks: HAL, BEL, ASIANPAINT, COALINDIA, POWERGRID. Nothing in the code depends on either list; any NSE ticker with a screener.in page works.

## Freshness labels

Prices show "close of <date> (end of day, not live)". Filings show when the exchange feed was last checked. Research shows when statements were fetched. A server booted from the seed snapshot keeps every original timestamp, so old data never looks new.

The Network is outside this discipline by design (the brief allows people-enrichment and network insights): it never
enters a research prompt, and research never reads it.
