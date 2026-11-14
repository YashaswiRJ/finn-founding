import { ArrowUp, ChevronDown, Info, Mic, Newspaper, Plus, Square, UserPlus } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { PersonHitRow, ProvenanceChip } from '../components/Network'
import { EmptyState, ErrorState, SectionTitle, Sheet, SkeletonRows } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { api, type NetworkQueryReply, type NetworkSummary, type PersonBrief, type PersonHit } from '../services/api'

const EXAMPLES = [
  'Who can connect me to Cipla’s new chief technical operating officer?',
  'Who previously worked at Tata Motors?',
  'Who in my network understands semiconductor manufacturing?',
  'Which contacts have automobile industry experience?',
  'Who haven’t I spoken to in a while?',
]

type Recognition = { lang: string; interimResults: boolean; onresult: (e: { results: { 0: { transcript: string } }[] }) => void; onend: () => void; onerror: () => void; start: () => void; stop: () => void }
const SpeechRec: (new () => Recognition) | undefined =
  (window as unknown as { SpeechRecognition?: new () => Recognition }).SpeechRecognition
  ?? (window as unknown as { webkitSpeechRecognition?: new () => Recognition }).webkitSpeechRecognition

export function NetworkPage() {
  const summary = useApi<NetworkSummary>('/api/network/summary')
  const [q, setQ] = useState('')
  const [asked, setAsked] = useState<string | null>(null)
  const [reply, setReply] = useState<NetworkQueryReply | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [theme, setTheme] = useState<{ label: string; people: PersonHit[] } | null>(null)
  const [adding, setAdding] = useState(false)
  const [listening, setListening] = useState(false)
  const rec = useRef<Recognition | null>(null)

  async function ask(text: string) {
    const msg = text.trim()
    if (msg.length < 2) return
    setAsked(msg)
    setQ('')
    setTheme(null)
    setBusy(true)
    setErr(null)
    try {
      setReply(await api.post<NetworkQueryReply>('/api/network/query', { q: msg }))
    } catch (e) {
      setErr((e as Error).message)
      setReply(null)
    } finally {
      setBusy(false)
    }
  }

  function toggleMic() {
    if (!SpeechRec) return
    if (listening) return rec.current?.stop()
    const r = new SpeechRec()
    r.lang = 'en-IN'
    r.interimResults = false
    r.onresult = (e) => void ask(e.results[0][0].transcript)
    r.onend = () => setListening(false)
    r.onerror = () => setListening(false)
    rec.current = r
    setListening(true)
    r.start()
  }

  const s = summary.data
  return (
    <div>
      <div className="mb-3 mt-1">
        <h1 className="text-xl font-bold tracking-tight">Who can help</h1>
        <p className="mt-0.5 text-sm text-ink-2">Your network, read against the filings and companies you follow.</p>
        {s && (
          <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-ink-3">
            {s.contacts} people · {s.relationships} relationships
            {s.investor.demo && <><span aria-hidden>·</span><ProvenanceChip p="synthetic" /> <span>fictional demo network</span></>}
          </p>
        )}
      </div>

      <form onSubmit={(e) => { e.preventDefault(); void ask(q) }}
        className="flex items-center gap-1.5 rounded-2xl border border-line-strong bg-surface p-1.5">
        {SpeechRec && (
          <button type="button" onClick={toggleMic} aria-label={listening ? 'Stop listening' : 'Ask by voice'} aria-pressed={listening}
            className={`grid size-9 shrink-0 place-items-center rounded-xl ${listening ? 'bg-accent-fill text-[#0b0b0b]' : 'text-ink-2 hover:bg-surface-2'}`}>
            {listening ? <Square size={14} aria-hidden /> : <Mic size={17} aria-hidden />}
          </button>
        )}
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={listening ? 'Listening…' : 'Who do I know at… / who knows…'}
          aria-label="Ask your network" maxLength={300} className="h-9 min-w-0 flex-1 bg-transparent px-1 text-[15px] outline-none" />
        <button disabled={q.trim().length < 2 || busy} aria-label="Ask" className="grid size-9 shrink-0 place-items-center rounded-xl bg-ink text-page disabled:opacity-30">
          <ArrowUp size={17} aria-hidden />
        </button>
      </form>

      {!asked && (
        <div className="mt-2 flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none]">
          {EXAMPLES.map((e) => (
            <button key={e} onClick={() => void ask(e)} className="h-8 shrink-0 rounded-full border border-line bg-surface px-3 text-xs text-ink-2">{e}</button>
          ))}
        </div>
      )}

      {asked && (
        <section className="mt-4" aria-live="polite">
          <p className="text-xs text-ink-3">“{asked}”</p>
          {busy ? <SkeletonRows n={2} h={96} /> : err ? <ErrorState message={err} onRetry={() => void ask(asked)} /> : reply && (
            <>
              <p className="mt-1 text-[15px] font-medium leading-snug">{reply.summary}</p>
              {reply.target && (
                <Link to={`/network/person/${encodeURIComponent(reply.target.id)}`} className="mt-1 inline-block text-xs text-ink-2 underline underline-offset-2">
                  {reply.target.full_name}’s career, from the filing
                </Link>
              )}
              {reply.people.length > 0 && <ul className="mt-3 space-y-2">{reply.people.map((h) => <PersonHitRow key={h.person.id} h={h} />)}</ul>}
              <p className="mt-2 flex items-start gap-1.5 text-[11px] text-ink-3"><Info size={12} className="mt-px shrink-0" aria-hidden />{reply.basis}</p>
              <button onClick={() => { setAsked(null); setReply(null) }} className="mt-2 text-xs text-ink-3 underline underline-offset-2">Clear</button>
            </>
          )}
        </section>
      )}

      {summary.error && !s ? (
        <div className="mt-6"><ErrorState message={summary.error} onRetry={summary.reload} /></div>
      ) : !s ? (
        <div className="mt-6"><SkeletonRows n={3} h={80} /></div>
      ) : s.contacts === 0 ? (
        <div className="mt-6">
          <EmptyState title="FINN works from who you know">
            Add the people you’ve met, former colleagues and classmates. FINN then watches filings and research for moments they can help.
            <button onClick={() => setAdding(true)} className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-ink px-3 py-1.5 text-sm font-semibold text-page"><UserPlus size={14} aria-hidden /> Add someone</button>
          </EmptyState>
        </div>
      ) : (
        <>
          {s.in_the_news.length > 0 && <InTheNews people={s.in_the_news} />}

          {s.reconnect.length > 0 && (
            <>
              <SectionTitle aside={<span className="text-xs text-ink-3">a reason to call</span>}>Reconnect</SectionTitle>
              <ul className="space-y-2">{s.reconnect.map((h) => <PersonHitRow key={h.person.id} h={h} compact />)}</ul>
            </>
          )}

          <SectionTitle aside={<span className="text-xs text-ink-3">tap a theme</span>}>Go-to people by theme</SectionTitle>
          <div className="flex flex-wrap gap-1.5">
            {s.themes.map((t) => (
              <button key={t.theme} onClick={() => { setTheme(theme?.label === t.label ? null : { label: t.label, people: t.top }); setAsked(null) }}
                aria-pressed={theme?.label === t.label}
                className={`h-8 rounded-full px-3 text-xs font-medium ${theme?.label === t.label ? 'bg-ink text-page' : 'border border-line bg-surface text-ink-2'}`}>
                {t.label} <span className={theme?.label === t.label ? 'opacity-70' : 'text-ink-3'}>{t.count}</span>
              </button>
            ))}
          </div>
          {theme && <ul className="mt-3 space-y-2">{theme.people.map((h) => <PersonHitRow key={h.person.id} h={h} compact />)}</ul>}

          <Contacts total={s.contacts} onAdd={() => setAdding(true)} />
        </>
      )}

      <p className="mt-6 text-[11px] leading-relaxed text-ink-3">
        Your network is private to you. FINN never sends your contacts to an AI model: links are computed from recorded relationships and career histories,
        and every inferred link says so. <Link to="/network/privacy" className="underline underline-offset-2">How FINN handles this data</Link>
      </p>

      <AddContact open={adding} onClose={() => setAdding(false)} onAdded={() => { setAdding(false); void summary.reload() }} />
    </div>
  )
}

function InTheNews({ people }: { people: (PersonBrief & { symbol?: string; published_at?: string })[] }) {
  return (
    <>
      <SectionTitle aside={<span className="text-xs text-ink-3">from this month’s filings</span>}>People in the news</SectionTitle>
      <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
        {people.map((p) => (
          <li key={p.id}>
            <Link to={`/network/person/${encodeURIComponent(p.id)}`} className="flex items-center gap-2.5 px-3.5 py-2.5">
              <Newspaper size={15} className="shrink-0 text-ink-3" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{p.full_name}</span>
                <span className="block truncate text-xs text-ink-3">{p.symbol ? <span className="font-semibold text-ink-2">{p.symbol} · </span> : null}{p.headline}</span>
              </span>
              <span className="shrink-0 text-xs text-ink-2">How to reach</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  )
}

function Contacts({ total, onAdd }: { total: number; onAdd: () => void }) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const list = useApi<{ people: PersonBrief[] }>(open ? `/api/network/people?limit=500${filter ? `&q=${encodeURIComponent(filter)}` : ''}` : null)
  return (
    <div className="mt-6">
      <div className="flex items-center gap-2">
        <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex flex-1 items-center gap-1.5 text-left">
          <span className="eyebrow">All contacts</span><span className="text-xs text-ink-3">{total}</span>
          <ChevronDown size={14} className={`text-ink-3 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
        </button>
        <button onClick={onAdd} className="inline-flex items-center gap-1 rounded-lg border border-line px-2.5 py-1 text-xs font-medium"><Plus size={13} aria-hidden /> Add</button>
      </div>
      {open && (
        <div className="mt-2">
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by name or role" aria-label="Filter contacts"
            className="mb-2 h-9 w-full rounded-lg border border-line bg-surface px-3 text-sm outline-none" />
          {list.error ? <ErrorState message={list.error} onRetry={list.reload} /> : !list.data ? <SkeletonRows n={4} h={44} /> : (
            <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface">
              {list.data.people.map((p) => (
                <li key={p.id}>
                  <Link to={`/network/person/${encodeURIComponent(p.id)}`} className="flex items-center gap-2 px-3.5 py-2">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{p.full_name}</span>
                      <span className="block truncate text-xs text-ink-3">{p.headline}</span>
                    </span>
                    <ProvenanceChip p={p.provenance} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

function AddContact({ open, onClose, onAdded }: { open: boolean; onClose: () => void; onAdded: () => void }) {
  const [err, setErr] = useState<string | null>(null)
  const [dupes, setDupes] = useState<PersonBrief[] | null>(null)
  const [saving, setSaving] = useState(false)

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const num = (k: string) => (f.get(k) ? Number(f.get(k)) : null)
    setSaving(true)
    setErr(null)
    try {
      const r = await api.post<{ created: boolean; duplicates_warning?: PersonBrief[] }>('/api/network/people', {
        full_name: f.get('full_name'), employer: f.get('employer') || null, title: f.get('title') || null,
        start_year: num('start_year'), end_year: num('end_year'), relationship: f.get('relationship'),
        strength: Number(f.get('strength')), last_interaction_at: f.get('last') || null, attest: f.get('attest') === 'on',
        allow_duplicate: !!dupes,
      })
      if (!r.created) setDupes(r.duplicates_warning ?? [])
      else {
        setDupes(null)
        onAdded()
      }
    } catch (e2) {
      setErr((e2 as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const field = 'h-9 w-full rounded-lg border border-line bg-page px-3 text-sm outline-none'
  return (
    <Sheet open={open} onClose={onClose} title="Add someone you know">
      <form onSubmit={submit} className="space-y-3 text-sm">
        <label className="block"><span className="eyebrow">Name</span><input name="full_name" required minLength={2} maxLength={120} className={`mt-1 ${field}`} /></label>
        <label className="block"><span className="eyebrow">Company (current or past)</span><input name="employer" maxLength={120} placeholder="e.g. Tata Motors" className={`mt-1 ${field}`} /></label>
        <label className="block"><span className="eyebrow">Role there</span><input name="title" maxLength={120} className={`mt-1 ${field}`} /></label>
        <div className="grid grid-cols-2 gap-2">
          <label><span className="eyebrow">From (year)</span><input name="start_year" type="number" min={1950} max={2100} className={`mt-1 ${field}`} /></label>
          <label><span className="eyebrow">To (blank = now)</span><input name="end_year" type="number" min={1950} max={2100} className={`mt-1 ${field}`} /></label>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label><span className="eyebrow">How you know them</span>
            <select name="relationship" className={`mt-1 ${field}`} defaultValue="knows">
              <option value="knows">Know them</option><option value="former_colleague">Former colleague</option><option value="classmate">Classmate</option>
              <option value="friend">Friend</option><option value="met_at_event">Met at an event</option>
            </select>
          </label>
          <label><span className="eyebrow">How well (1–5)</span><input name="strength" type="number" min={1} max={5} defaultValue={3} className={`mt-1 ${field}`} /></label>
        </div>
        <label className="block"><span className="eyebrow">Last spoke</span><input name="last" type="date" className={`mt-1 ${field}`} /></label>
        <label className="flex items-start gap-2 text-xs text-ink-2">
          <input name="attest" type="checkbox" required className="mt-0.5" />
          I have a professional relationship with this person. FINN keeps this private to me, never sends it to an AI model, and deletes it after two years unless I renew it.
        </label>
        {dupes && dupes.length > 0 && (
          <p className="rounded-lg bg-accent-wash px-3 py-2 text-xs text-accent">
            You already have {dupes.map((d) => d.full_name).join(', ')} in your network. Save again to add a different person with the same name.
          </p>
        )}
        {err && <p className="text-xs text-down">{err}</p>}
        <button disabled={saving} className="w-full rounded-lg bg-ink py-2.5 text-sm font-semibold text-page disabled:opacity-50">{saving ? 'Saving…' : dupes ? 'Add anyway' : 'Add to my network'}</button>
      </form>
    </Sheet>
  )
}
