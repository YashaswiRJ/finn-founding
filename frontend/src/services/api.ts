const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

/** A signed-in investor's bearer token, if any. Without one the API serves the synthetic demo network. */
function authHeader(): Record<string, string> {
  try {
    const t = localStorage.getItem('finn-token')
    return t ? { Authorization: `Bearer ${t}` } : {}
  } catch {
    return {}
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...authHeader(), ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(0, 'FINN’s server is unreachable. It may be waking up — retry in a few seconds.')
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') msg = body.detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, msg)
  }
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: async <T>(path: string, form: FormData): Promise<T> => {
    const res = await fetch(`${BASE}${path}`, { method: 'POST', body: form })
    if (!res.ok) throw new ApiError(res.status, (await res.json().catch(() => ({}))).detail ?? 'Upload failed')
    return res.json()
  },
}

// ---- Types mirroring the backend payloads ----

export type Priority = 'HIGH' | 'MEDIUM' | 'LOW'

export interface MarketStats {
  date: string
  close: number
  prev_close: number | null
  return_pct: number | null
  volume: number | null
  avg_volume: number | null
  volume_multiple: number | null
  lookback_sessions: number
  spark: number[]
  fetched_at: string | null
  fetch_ok: boolean | null
  fetch_error: string | null
  source_url: string
}

export interface Company {
  symbol: string
  name: string
  sector: string | null
  size_bucket: string | null
  bse_code: string | null
  in_portfolio: number
  is_research_pick: number
  market: MarketStats | null
  high_priority_7d: number
}

export interface RefreshStatus {
  state: 'never' | 'running' | 'done' | 'failed' | 'started' | 'already_running'
  started_at: string | null
  finished_at: string | null
  step?: string | null
  errors?: string[]
}

export interface Citation {
  doc_title: string
  doc_type?: string
  period?: string | null
  page: number | null
  quote?: string | null
  url: string | null
}

export interface ResultsCard {
  basis: string | null
  unit: string | null
  period_label: string | null
  metrics: Record<string, { current: number | null; prev_q: number | null; year_ago: number | null;
    qoq: number | null; yoy: number | null; derived?: string | null; verified?: boolean }>
  page: number | null
  checks: string[]
  promise_checks?: { quote: string; metric: string; target_text: string; outcome: string; explanation: string }[]
}

export interface PersonCard {
  name: string
  role: string
  change: 'appointed' | 'resigned' | 'retired' | 'ceased' | 'other'
  effective: string | null
  background: string | null
  background_source: 'filing' | 'not_disclosed'
  linkedin_search_url: string
  person_id?: string
  method?: 'rules' | string
}

export interface Summary {
  what_happened: string
  why_it_matters: string
  implication: string
  unknowns: string
  model: string
  is_interpretation: boolean
}

export interface Announcement {
  id: string
  symbol: string
  company_name: string
  title: string
  detail: string | null
  bse_category: string | null
  bse_subcategory: string | null
  published_at: string
  source: string
  filing_page_url: string | null
  pdf_url: string | null
  category: string
  category_confidence: number
  category_method: string
  priority: Priority
  priority_score: number
  priority_reason: string
  summary: Summary | null
  card: { needs_reading?: boolean; tags?: string[]; critical?: boolean; results?: ResultsCard;
    people?: PersonCard[]; read_error?: string }
  enriched_at: string | null
  low_confidence: boolean
  related?: { id: string; title: string; published_at: string; pdf_url: string | null; priority: Priority }[]
  network?: AnnouncementNetwork | null
}

export interface Digest {
  window_hours: number
  generated_at: string
  counts: { filings: number; events: number; high: number; medium: number; low: number }
  must_read: Announcement[]
  worth_a_look: Announcement[]
  buried: Announcement[]
  freshness: { last_success: string | null; via: string | null; failures: { key: string; detail: string }[] }
  network_summary?: { reconnect: PersonHit[] } | null
}

export interface Alert {
  id: number
  symbol: string
  name: string | null
  trade_date: string
  rule: string
  kind: 'price_up' | 'price_down' | 'volume' | 'announcement'
  value: number | null
  threshold: number | null
  created_at: string
  acknowledged: number
  details: {
    reason: string
    close?: number
    prev_close?: number
    return_pct?: number
    volume?: number
    avg_volume?: number
    volume_multiple?: number
    lookback_sessions?: number
    source_url?: string
    basis?: string
    announcement_id?: string
  }
}

export interface AlertSettings {
  price_up_pct: number
  price_down_pct: number
  volume_multiple: number
  enabled: { price_up: boolean; price_down: boolean; volume: boolean; announcement: boolean }
  symbols: string[] | null
  announcement_categories: string[]
  announcement_min_priority: Priority
  scan_sessions: number
}

export interface CitedSegment {
  text: string
  citations: { doc_id: string; doc_title: string; doc_type: string; period: string | null; page: number | null; url: string | null; quote: string }[]
}

export interface SnapRow { metric: string; current: number | null; prev_q: number | null; year_ago: number | null; qoq: number | null; yoy: number | null; note: string | null }

export interface Financials {
  symbol: string
  name: string
  basis: string
  is_bank: boolean
  source: { name: string; url: string; fetched_at: string; unit: string }
  key_ratios: Record<string, string | undefined>
  snapshot: {
    period: string | null; period_label: string | null; prev_label: string | null; year_ago_label: string | null
    rows: SnapRow[]
    margin: { label: string; current: number | null; prev_q: number | null; year_ago: number | null } | null
  }
  quarterly: { period: string; label: string; revenue: number | null; ebitda: number | null; pat: number | null; margin: number | null }[]
  annual: { year: string; label: string; revenue: number | null; ebitda: number | null; pat: number | null; margin: number | null;
    cfo: number | null; fcf: number | null; borrowings: number | null; equity: number | null; de: number | null; roce: number | null;
    wc_days: number | null; ccc: number | null; cfo_to_pat: number | null }[]
  observations: { trajectory: string[]; balance_sheet: string[]; cash_quality: string[] }
}

export interface Promise_ {
  id: string; doc_id: string; page: number; said_in: string; quote: string; speaker: string; metric: string; metric_detail: string
  target_text: string; unit: string; due_period: string; outcome: 'Met' | 'Exceeded' | 'Missed' | 'Not yet due' | "Can't verify"
  actual_value: number | null; actual_text: string; doc_title: string; doc_url: string; explanation: string
}

export interface LabelledPoint { label: string; text: string; citations: CitedSegment['citations'] }

export interface ResearchJob {
  id: string; symbol: string; status: 'running' | 'done' | 'failed'; error: string | null
  steps: { name: string; state: 'pending' | 'running' | 'done' | 'failed' | 'skipped'; detail: string | null }[]
  updated_at: string
}

export interface DocumentRow {
  id: string; doc_type: string; period: string | null; title: string; source_url: string; pages: number | null
  text_quality: string | null; status: string; error: string | null
}

export interface CompanyResearch {
  company: { symbol: string; name: string; sector: string | null; in_portfolio: number } | null
  sections: {
    financials?: { data: Financials; updated_at: string }
    ledger?: { data: { rows: Promise_[]; counts: Record<string, number>; transcripts_read: { title: string; url: string; call: string | null }[] }; updated_at: string }
    business?: { data: { segments: CitedSegment[]; model: string }; updated_at: string }
    bull_bear?: { data: { bull: LabelledPoint[]; bear: LabelledPoint[]; ledger_conclusion: LabelledPoint | null; watch: LabelledPoint | null; dropped_uncited: number; model: string }; updated_at: string }
  }
  job: ResearchJob | null
  documents: DocumentRow[]
  llm_configured: boolean
}

export interface ChatReply {
  intent: 'portfolio' | 'move' | 'numbers' | 'documents' | 'network'
  people?: PersonHit[]
  target?: { id: string; full_name: string; headline: string | null } | null
  symbol: string | null
  segments: CitedSegment[]
  cards: Announcement[]
  moves?: Alert[]
  table?: { columns: string[]; rows: (string | number | null)[][] }
  basis?: string
  model?: string
  job_id?: string
  grounded?: boolean
}

export interface Health {
  ok: boolean
  llm_configured: boolean
  companies: number
  network?: { demo_mode: boolean; public_profiles: number }
}

// ---- Network ----

/** Where a fact came from. 'synthetic' = demo data; 'filing' = an exchange disclosure; 'inferred' = computed by FINN. */
export type Provenance = 'synthetic' | 'user_entered' | 'filing' | 'public_dataset' | 'inferred' | 'declared' | 'derived'

export interface PathEdge {
  kind: string
  label: string
  known: boolean
  strength?: number
  provenance: Provenance | string
  context?: string | null
  confidence?: number
  evidence?: string
}

export interface PathNode { id: string; name: string; edge?: PathEdge }

export interface PersonBrief {
  id: string
  full_name: string
  headline: string | null
  kind: 'self' | 'contact' | 'public_figure'
  provenance: Provenance
  location?: string | null
  last_interaction_at?: string | null
  source_url?: string | null
  source_ref?: string | null
}

export interface PersonHit {
  person: PersonBrief
  score: number
  path: PathNode[]
  why: { text: string; provenance: Provenance | string; confidence?: number }[]
  explanation: string
  flags: string[]
  degree: number
  suggested_questions?: string[]
  announcement_id?: string
  insight_id?: number
  match?: { confidence: number; method: string; status: string }
}

export interface AnnouncementNetwork {
  people: { filing_person: { name: string; role: string; change: string; background_source: string }; person_id: string; hits: PersonHit[] }[]
  best_placed: PersonHit | null
}

export interface Employment {
  id: number; org_id: string; org_name: string; symbol: string | null; sector: string | null; title: string | null
  function: string | null; seniority: string | null; start_year: number | null; end_year: number | null
  is_current: number | null; provenance: string; evidence: string | null; confidence: number
}

export interface Education { id: number; org_name: string; degree: string | null; end_year: number | null; provenance: string; evidence: string | null }

export interface PersonDetail extends PersonBrief {
  notes: string | null
  employments: Employment[]
  educations: Education[]
  expertise: { theme: string; label?: string; weight: number; method: 'declared' | 'derived'; evidence: string }[]
  relationships: { id: number; person: PersonBrief & { name: string }; kind: string; label: string; strength: number; context: string | null; provenance: string }[]
  paths: PersonHit[]
  diligence: string[]
  matches: { contact_id: string; contact_name: string; confidence: number; method: string; label: string }[]
  filing?: { id: string; title: string; published_at: string; pdf_url: string | null; symbol: string; company_name: string | null; person: PersonCard | null }
}

export interface NetworkSummary {
  investor: { id: string; display_name: string | null; demo: boolean }
  contacts: number
  relationships: number
  organizations: number
  themes: { theme: string; label: string; count: number; top: PersonHit[] }[]
  reconnect: PersonHit[]
  in_the_news: (PersonBrief & { symbol?: string; published_at?: string })[]
}

export interface NetworkQueryReply {
  filter: { kind: string; organization: string | null; themes: string[]; role: string | null; employment: string; via: string }
  target: { id: string; full_name: string; headline: string | null } | null
  people: PersonHit[]
  summary: string
  basis: string
}

export interface CompanyContacts {
  symbol: string
  organization: string
  people: PersonHit[]
  theme_fallback: PersonHit[]
  in_the_news: (PersonBrief & { title: string | null })[]
  basis: string
}
