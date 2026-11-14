# LLMs and agents

One rule shapes everything: **a model reads and writes prose; code does arithmetic, decides relationships and checks
the model's work.** Every model call goes through `backend/app/llm/client.py`.

## Which step uses a model

| Step | Handled by | Why |
|---|---|---|
| Prices, returns, volume multiples, alert firing | Python | Arithmetic should never be probabilistic |
| Classifying filings | Rules first (most filings settle without a model) | BSE metadata already says what most filings are |
| Reading ambiguous filings: 4-part summary, priority, people | Haiku 5.5, JSON schema, effort `low` | Bulk, cheap, schema-guaranteed |
| **People in management-change filings** | **Rules** (`network/filing_people.py`); Haiku's reading when keyed | SEBI disclosures have a fixed shape; works with no key |
| **Career history from a filing's background** | Rules; Haiku `bio_to_history` when keyed, every row's evidence verified against the text | Cheap extraction, nothing unverifiable kept |
| Results numbers | Haiku transcribes; Python computes QoQ/YoY/EBITDA; figures must appear on the page | The model copies; it doesn't do maths |
| Scanned filings | Haiku reads the single page as a PDF image | Avoids trusting garbled OCR |
| Guidance extraction (Promise Ledger) | Haiku over keyword-filtered transcript pages; quotes verified | ~12 of 20+ pages per transcript |
| Ledger scoring | Python | A promise is met or missed by arithmetic |
| Business snapshot | Haiku + Citations API | Short, grounded |
| Bull/bear, ledger conclusion, document Q&A | Sonnet 5.5 + Citations API | Multi-document reasoning; citations are machine-checkable; uncited points deleted |
| **Entity resolution, paths, overlaps, ranking** | **Python** | Must be auditable; a model would guess |
| **Network explanations** | **Templates over evidence** | Zero cost, nothing invented, no personal data to a model |
| **Network question → filter** | Rules; Haiku `network_query_parse` only when rules find nothing, **question text only** | Most questions parse by rules |
| Embeddings | Chroma's local ONNX model | No API cost |

## Controls

- **Routing:** `MODEL_CHEAP` (Haiku) for bulk extraction; `MODEL_STRONG` (Sonnet) only for bull/bear, the ledger
  conclusion and document Q&A. The strong tier sends the server-side refusal fallback.
- **Caching:** every call is cached by a SHA-256 of its full input (`llm_cache`); system prompts carry a prompt-cache
  breakpoint; network prompts carry `PROMPT v1` so a prompt change invalidates the cache.
- **Cost log:** real token usage and cost per call (`llm_calls`), visible at `GET /api/costs`.
- **Structured output:** JSON schema (`output_config.format`) for every extraction.
- **Chunking:** page-bounded chunks, hybrid FTS5 + vector retrieval, only the relevant pages sent.
- **Retries / rate limits:** SDK retries (3); `LLMUnavailable` surfaces failures honestly; Ask and network questions
  are rate-limited per IP.
- **Untrusted input:** every prompt marks documents as data and ignores instructions inside them.

## Hallucination guards (in code, not prompts)

- Pages and citations come from FINN's own stored passages (custom-content documents), never from the model.
- Results figures and ledger quotes must appear verbatim on the source page.
- Bull/bear points without a citation are deleted and counted.
- Career rows from a model must have evidence found in the filing text, or they are dropped.
- The network engine never accepts a relationship from a model; links are rows or computed overlaps.

## Agents

FINN uses **tool routing, not autonomous agents.** `research/chat.py` picks one tool per question (portfolio
database, prices + filings, statements table, cited document retrieval, or the network engine); the research job is a
fixed pipeline. There is no multi-agent loop: for this workload a deterministic router is cheaper, faster, and easier to
trust and test. Where an agent would earn its place next: a research planner that decides which extra documents to read
when the ledger can't verify a promise.

## Cost

The rebuilt demo snapshot is designed to cost about a dollar once (Haiku for ~100 filing reads and a few bios; Sonnet
for bull/bear on a handful of companies), then nothing per visitor: the deployed demo serves stored results. The
Network costs nothing per question unless the rules can't parse it.
