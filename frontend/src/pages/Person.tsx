import { ExternalLink, FileText, HelpCircle, Quote } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { PersonHitRow, ProvenanceChip } from '../components/Network'
import { EmptyState, ErrorState, SectionTitle, SkeletonRows } from '../components/ui'
import { useApi } from '../hooks/useApi'
import { api, type Employment, type PersonDetail } from '../services/api'
import { timeLabel } from '../utils/format'

function span(e: Employment) {
  if (e.start_year && e.end_year) return `${e.start_year}–${e.end_year}`
  if (e.start_year) return e.is_current === 0 ? `from ${e.start_year}` : `${e.start_year}–now`
  if (e.is_current === 1) return 'Current'
  if (e.is_current === 0) return 'Earlier'
  return 'Dates not stated'
}

export function PersonPage() {
  const { id = '' } = useParams()
  const nav = useNavigate()
  const r = useApi<PersonDetail>(`/api/network/people/${encodeURIComponent(id)}`)
  const [busy, setBusy] = useState(false)

  if (r.error && !r.data) return <><Back /><ErrorState message={r.error} onRetry={r.reload} /></>
  if (!r.data) return <><Back /><SkeletonRows n={4} h={90} /></>
  const p = r.data
  const isPublic = p.kind === 'public_figure'
  const current = p.employments.filter((e) => e.is_current === 1 || (e.end_year == null && e.start_year != null))
  const boards = p.employments.filter((e) => e.seniority === 'board')
  const career = p.employments.filter((e) => e.seniority !== 'board' || e.title !== 'Board member')

  async function decide(contactId: string, status: 'confirmed' | 'rejected') {
    setBusy(true)
    await api.post(`/api/network/matches/${encodeURIComponent(p.id)}/${encodeURIComponent(contactId)}`, { status }).catch(() => null)
    setBusy(false)
    void r.reload()
  }

  async function remove() {
    if (!window.confirm(`Remove ${p.full_name} from your network? This deletes everything FINN holds about them.`)) return
    await api.del(`/api/network/people/${encodeURIComponent(p.id)}`)
    nav('/network')
  }

  return (
    <div>
      <Back />
      <header className="mt-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <h1 className="text-xl font-bold tracking-tight">{p.full_name}</h1>
          <ProvenanceChip p={p.provenance} />
        </div>
        {p.headline && <p className="mt-0.5 text-sm text-ink-2">{p.headline}</p>}
        <p className="mt-1 text-xs text-ink-3">
          {isPublic ? 'Named in an exchange filing. You don’t know them directly.' : p.kind === 'contact' ? 'In your network' : ''}
          {p.location ? ` · ${p.location}` : ''}{p.last_interaction_at ? ` · last spoke ${p.last_interaction_at}` : ''}
        </p>
      </header>

      {p.filing && (
        <section className="mt-4 rounded-xl border border-line bg-surface p-3.5 text-sm">
          <p className="eyebrow">Why they’re here</p>
          <p className="mt-1">
            <Link to={`/research/${p.filing.symbol}`} className="font-semibold underline underline-offset-2">{p.filing.company_name ?? p.filing.symbol}</Link>
            {' '}filed {timeLabel(p.filing.published_at)}: {p.filing.person ? `${p.filing.person.change} as ${p.filing.person.role}` : p.filing.title}
            {p.filing.person?.effective ? `, effective ${p.filing.person.effective}` : ''}.
          </p>
          {p.filing.person?.background && <Bio text={p.filing.person.background} />}
          {p.filing.pdf_url && (
            <a href={p.filing.pdf_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-ink-2 underline underline-offset-2">
              <FileText size={12} aria-hidden /> Open the filing <ExternalLink size={11} aria-hidden />
            </a>
          )}
        </section>
      )}

      {p.matches.length > 0 && (
        <section className="mt-4 rounded-xl bg-accent-wash p-3.5 text-sm">
          <p className="font-semibold">Is this someone you already know?</p>
          {p.matches.map((m) => (
            <div key={m.contact_id} className="mt-2">
              <p className="text-ink-2">Your contact <Link to={`/network/person/${encodeURIComponent(m.contact_id)}`} className="font-semibold underline">{m.contact_name}</Link> is {m.label} ({Math.round(m.confidence * 100)}%, matched on {m.method.replace('+', ' + ').replace('_', ' ')}).</p>
              <div className="mt-1.5 flex gap-2">
                <button disabled={busy} onClick={() => void decide(m.contact_id, 'confirmed')} className="rounded-lg bg-ink px-3 py-1 text-xs font-semibold text-page">Same person</button>
                <button disabled={busy} onClick={() => void decide(m.contact_id, 'rejected')} className="rounded-lg border border-line-strong px-3 py-1 text-xs">Different person</button>
              </div>
            </div>
          ))}
        </section>
      )}

      <SectionTitle>{isPublic ? 'How you could reach them' : 'How you’re connected'}</SectionTitle>
      {p.paths.length ? (
        <ul className="space-y-2">{p.paths.map((h) => <PersonHitRow key={h.person.id + h.score} h={h} compact />)}</ul>
      ) : (
        <p className="text-sm text-ink-3">{isPublic ? `No one in your network has crossed paths with ${p.full_name} on the record.` : 'No path recorded.'}</p>
      )}

      {p.diligence.length > 0 && (
        <>
          <SectionTitle>Worth asking about</SectionTitle>
          <ul className="space-y-1.5">
            {p.diligence.map((d) => (
              <li key={d} className="flex items-start gap-2 text-sm text-ink-2"><HelpCircle size={14} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />{d}</li>
            ))}
          </ul>
        </>
      )}

      <SectionTitle aside={current.length ? <span className="text-xs text-ink-3">{current.length} current</span> : undefined}>Career</SectionTitle>
      {career.length ? <Timeline rows={career} /> : <EmptyState title="No career history recorded" />}

      {boards.filter((b) => b.title === 'Board member').length > 0 && (
        <>
          <SectionTitle>Board seats</SectionTitle>
          <ul className="flex flex-wrap gap-1.5">
            {boards.filter((b) => b.title === 'Board member').map((b) => (
              <li key={b.id} className={`rounded-full px-2.5 py-1 text-xs ${b.is_current === 1 ? 'bg-surface-2 text-ink' : 'border border-line text-ink-3'}`}
                title={b.evidence ?? undefined}>
                {b.org_name}{b.is_current === 0 ? ' (past)' : ''}
              </li>
            ))}
          </ul>
        </>
      )}

      {p.educations.length > 0 && (
        <>
          <SectionTitle>Education</SectionTitle>
          <ul className="space-y-1 text-sm">
            {p.educations.map((e) => (
              <li key={e.id} className="flex items-center gap-2"><span className="font-medium">{e.org_name}</span>
                <span className="text-ink-3">{[e.degree, e.end_year].filter(Boolean).join(' · ')}</span>
                <span className="ml-auto"><ProvenanceChip p={e.provenance} /></span></li>
            ))}
          </ul>
        </>
      )}

      {p.expertise.length > 0 && (
        <>
          <SectionTitle>Expertise</SectionTitle>
          <ul className="space-y-2">
            {p.expertise.slice(0, 6).map((x) => (
              <li key={x.theme} className="text-xs">
                <div className="flex items-center gap-2">
                  <span className="w-40 shrink-0 truncate font-medium">{x.label ?? x.theme.replace(/_/g, ' ')}</span>
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2" aria-hidden>
                    <span className="block h-full rounded-full bg-ink-3" style={{ width: `${Math.round(x.weight * 100)}%` }} />
                  </span>
                  <ProvenanceChip p={x.method} />
                </div>
                <p className="mt-0.5 text-ink-3">{x.evidence}</p>
              </li>
            ))}
          </ul>
        </>
      )}

      {p.relationships.length > 0 && (
        <>
          <SectionTitle>Knows</SectionTitle>
          <ul className="space-y-1 text-sm">
            {p.relationships.map((rel) => (
              <li key={rel.id} className="flex items-center gap-2">
                {rel.person.kind === 'self' ? <span className="font-medium">You</span>
                  : <Link to={`/network/person/${encodeURIComponent(rel.person.id)}`} className="font-medium underline underline-offset-2">{rel.person.full_name}</Link>}
                <span className="text-ink-3">{rel.label}{rel.context ? ` · ${rel.context}` : ''}</span>
                <span className="ml-auto text-xs text-ink-3" aria-label={`strength ${rel.strength} of 5`}>{'●'.repeat(rel.strength)}<span className="opacity-30">{'●'.repeat(5 - rel.strength)}</span></span>
              </li>
            ))}
          </ul>
        </>
      )}

      {p.notes && (
        <>
          <SectionTitle>Your notes</SectionTitle>
          <p className="text-sm text-ink-2">{p.notes}</p>
        </>
      )}

      {p.kind === 'contact' && (
        <button onClick={() => void remove()} className="mt-8 text-xs text-ink-3 underline underline-offset-2">Remove from my network</button>
      )}
    </div>
  )
}

function Timeline({ rows }: { rows: Employment[] }) {
  return (
    <ol className="relative space-y-3 border-l border-line pl-4">
      {rows.map((e) => (
        <li key={e.id} className="relative">
          <span className={`absolute -left-[21px] top-1.5 size-2.5 rounded-full border-2 border-page ${e.is_current === 1 ? 'bg-ink' : 'bg-line-strong'}`} aria-hidden />
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-medium">{e.symbol ? <Link to={`/research/${e.symbol}`} className="underline underline-offset-2">{e.org_name}</Link> : e.org_name}</span>
            <span className="ml-auto shrink-0 text-xs text-ink-3">{span(e)}</span>
          </div>
          <p className="text-xs text-ink-2">{e.title ?? 'Role not stated'}</p>
          {e.provenance === 'filing' && e.evidence && (
            <p className="mt-1 flex items-start gap-1 text-[11px] leading-snug text-ink-3"><Quote size={10} className="mt-0.5 shrink-0" aria-hidden />{e.evidence}</p>
          )}
        </li>
      ))}
    </ol>
  )
}

function Bio({ text }: { text: string }) {
  const [more, setMore] = useState(false)
  const long = text.length > 320
  return (
    <div className="mt-2">
      <blockquote className={`border-l-2 border-line-strong pl-3 text-[13px] leading-relaxed text-ink-2 ${long && !more ? 'line-clamp-5' : ''}`}>{text}</blockquote>
      <p className="mt-1 text-[11px] text-ink-3">As disclosed in the filing.{long && (
        <button onClick={() => setMore((m) => !m)} className="ml-1 underline underline-offset-2">{more ? 'Show less' : 'Show the full profile'}</button>)}</p>
    </div>
  )
}

const Back = () => <Link to="/network" className="mb-2 inline-block text-xs text-ink-3">← Network</Link>

/** Plain-language data handling for the network. */
export function PrivacyPage() {
  return (
    <div className="space-y-4 text-sm leading-relaxed">
      <Back />
      <h1 className="text-xl font-bold tracking-tight">How FINN handles your network</h1>
      {[
        ['Private to you', 'Every contact, relationship and note carries your account as its owner, and every query is filtered by it. Another investor using FINN can never see them.'],
        ['Never sent to an AI model', 'Links between people are computed from relationships you recorded and from career histories. Explanations are written from that evidence by templates. When you ask a question in words, only your question text may go to a model to be turned into a filter.'],
        ['Labelled by source', '“Known” links are relationships you recorded. “Inferred” links are career overlaps FINN computed — they show their confidence and say “verify before relying on it”. “From filing” facts come from exchange disclosures, with the sentence they came from.'],
        ['Kept for two years', 'Contacts expire two years after you add them unless you renew them, and you can delete any person — or your entire network — at any time.'],
        ['Consent', 'You confirm a professional relationship before adding anyone. FINN does not scrape LinkedIn or any platform.'],
        ['This demo', 'The network you see is fictional: invented people whose careers deliberately overlap real companies and the real executives named in this month’s filings.'],
      ].map(([h, b]) => (
        <div key={h}><p className="font-semibold">{h}</p><p className="text-ink-2">{b}</p></div>
      ))}
    </div>
  )
}
