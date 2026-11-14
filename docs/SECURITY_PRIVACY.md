# Security and privacy

The Network holds personal information about real relationships, so it is designed private-first. This page separates
what the prototype implements from what a real deployment would add.

## What is stored, and for how long

| Data | Whose | Stored | Retention |
|---|---|---|---|
| Market data, filings, research | Public | SQLite; seed snapshot | Indefinite |
| People named in filings (name, role, the filing's own profile text, career rows citing it) | Public disclosure | SQLite; seed snapshot | Indefinite (refreshed when re-filed) |
| The investor's contacts, careers, notes, last-spoke dates | The investor | SQLite, owner-scoped | `expires_at` = added + 730 days (`NETWORK_RETENTION_DAYS`); purged at boot and on every refresh |
| Relationships, same-person decisions, network insights | The investor | SQLite, owner-scoped | Deleted with the contact or the account |
| Bearer tokens | The investor | SHA-256 hash only | Until reissued |

## Implemented in the prototype

- **Isolation:** every private row has `owner_id`; `network/repo.py` is the only code that reads them and always
  filters by owner. Tests call every repo function as a second investor and assert nothing leaks. Relationships can
  only join the investor's own contacts.
- **Authentication:** `Authorization: Bearer <token>` → investor (hash lookup). `NETWORK_DEMO_MODE=true` lets the public
  demo serve one fictional investor without sign-in; set it `false` and network endpoints return 401 without a token,
  while Push/Pull keep working without the network field.
- **Never to a model:** contacts, relationships and notes are never sent to an LLM. Explanations are templates. A network
  question may go to the cheap model only as text, only when rules can't parse it, to get a filter back.
- **Never in the snapshot:** the committed snapshot contains public rows only (tested).
- **Consent:** adding a contact requires confirming a professional relationship (`consent_basis='investor_attested'`);
  demo rows are `synthetic`.
- **Erasure:** delete a contact (cascades), or `DELETE /api/network/me/data` for everything.
- **Provenance and unsupported claims:** every fact says where it came from; inferred links carry a confidence and
  "verify before relying on it"; current insiders are flagged ("talk context and industry, not unpublished numbers").
- **No scraping:** no LinkedIn or platform scraping; the LinkedIn link is a search URL the investor opens themselves.
- **Input validation:** Pydantic lengths, enums and ranges on every body; https-only document import; PDF magic and
  size checks.
- **Rate limiting:** 30 per minute per IP on Ask and network questions.
- **Prompt injection:** filing and document text is marked untrusted, outputs are schema-constrained, and anything
  factual is verified against the source text.
- **Secrets:** only in `.env` (git-ignored) or the host's dashboard; never logged or committed.

## A real deployment would add

- SSO/OIDC with the firm's identity provider, short-lived tokens, device binding; CORS pinned to the firm's origin.
- Postgres with row-level security on every network table, encryption at rest with per-tenant keys, and an audit log
  of reads and exports.
- A consent record per contact under India's DPDP Act 2023: purpose limitation (investment research), a notice, and
  honouring a contact's own deletion request.
- Network import only from sources the investor may use: their own LinkedIn data export, CRM and calendar via OAuth,
  or a licensed people-data provider under contract.
- Compliance workflow for conversations with current insiders (MNPI), with logs.
- Secrets in a secret manager; dependency and container scanning.
