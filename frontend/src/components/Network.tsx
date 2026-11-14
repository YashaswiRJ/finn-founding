import { AlertTriangle, ChevronRight, Network as NetworkIcon, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import type { AnnouncementNetwork, CompanyContacts, PathNode, PersonHit, Provenance } from '../services/api'
import { EmptyState, ErrorState, SectionTitle, SkeletonRows } from './ui'

/**
 * The Network's UI vocabulary. Every person-fact carries where it came from, because the investor has to know
 * the difference between "you know her", "FINN inferred they overlapped" and "the filing says so".
 */

const PROV: Record<string, { label: string; title: string }> = {
  synthetic: { label: 'Demo data', title: 'A fictional person from FINN’s demo network' },
  user_entered: { label: 'You added', title: 'You recorded this' },
  filing: { label: 'From filing', title: 'Disclosed in an exchange filing' },
  inferred: { label: 'Inferred', title: 'Computed by FINN from careers, not a known relationship' },
  declared: { label: 'You said', title: 'Expertise you recorded' },
  derived: { label: 'From career', title: 'Derived from their employment history' },
  public_dataset: { label: 'Public data', title: 'From a public dataset' },
}

export function ProvenanceChip({ p }: { p: Provenance | string }) {
  const v = PROV[p] ?? { label: p, title: p }
  const inferred = p === 'inferred'
  return (
    <span title={v.title}
      className={`inline-flex h-[18px] shrink-0 items-center rounded px-1.5 text-[10px] font-medium ${inferred ? 'border border-dashed border-line-strong text-ink-2' : 'bg-surface-2 text-ink-3'}`}>
      {v.label}
    </span>
  )
}

const FLAG: Record<string, { label: string; warn?: boolean; title: string }> = {
  mnpi: { label: 'Current insider', warn: true, title: 'Works there now: talk context and industry, not unpublished numbers' },
  inferred: { label: 'Inferred link', title: 'The last step is a career overlap FINN computed, not a known relationship' },
  possibly_same_person: { label: 'Same person?', title: 'One of your contacts may be this person' },
  unrecorded_strength: { label: 'Strength not recorded', title: 'You added them without saying how well you know them' },
}

export function FlagChips({ flags }: { flags: string[] }) {
  return (
    <>
      {flags.filter((f) => FLAG[f]).map((f) => (
        <span key={f} title={FLAG[f].title}
          className={`inline-flex h-[18px] items-center gap-1 rounded px-1.5 text-[10px] font-medium ${FLAG[f].warn ? 'bg-accent-wash text-accent' : 'border border-line text-ink-3'}`}>
          {FLAG[f].warn && <AlertTriangle size={10} aria-hidden />}{FLAG[f].label}
        </span>
      ))}
    </>
  )
}

/** You — Former colleague — Neha ┄ Inferred ┄ Vikram. Solid = known relationship; dashed = computed overlap. */
export function PathLine({ path }: { path: PathNode[] }) {
  const sentence = path.map((n, i) => (i === 0 ? n.name : `${n.edge?.label ?? 'knows'} ${n.name}`)).join(', ')
  return (
    <ol className="flex flex-wrap items-center gap-x-1 gap-y-0.5 text-xs" aria-label={`Path: ${sentence}`}>
      {path.map((n, i) => (
        <li key={n.id + i} className="flex items-center gap-1">
          {n.edge && (
            <span className="flex items-center gap-1 text-[10px] text-ink-3" aria-hidden>
              <span className={`w-3 border-t ${n.edge.known ? 'border-ink-3' : 'border-dashed border-ink-3'}`} />
              <span className={n.edge.known ? '' : 'italic'}>{n.edge.known ? n.edge.label : `inferred ${Math.round((n.edge.confidence ?? 0) * 100)}%`}</span>
              <span className={`w-3 border-t ${n.edge.known ? 'border-ink-3' : 'border-dashed border-ink-3'}`} />
            </span>
          )}
          <span className={`${i === 0 ? 'text-ink-3' : 'font-medium'} ${i === path.length - 1 && i > 0 ? 'text-ink' : ''}`}>{n.name}</span>
        </li>
      ))}
    </ol>
  )
}

export function PersonHitRow({ h, showQuestions = false, compact = false }: { h: PersonHit; showQuestions?: boolean; compact?: boolean }) {
  return (
    <li className="rounded-xl border border-line bg-surface">
      <Link to={`/network/person/${encodeURIComponent(h.person.id)}`} className="block px-3.5 py-3">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-sm font-semibold">{h.person.full_name}</span>
          <span className="shrink-0 text-[11px] text-ink-3">{h.degree <= 1 ? 'Direct' : '2nd degree'}</span>
          <span className="ml-auto flex shrink-0 items-center gap-1">
            <ProvenanceChip p={h.person.provenance} />
            <ChevronRight size={15} className="text-ink-3" aria-hidden />
          </span>
        </div>
        <p className={`mt-1 text-[13px] leading-snug text-ink-2 ${compact ? 'line-clamp-2' : 'line-clamp-4'}`}>{h.explanation}</p>
        <div className="mt-2"><PathLine path={h.path} /></div>
        {h.flags.length > 0 && <div className="mt-2 flex flex-wrap gap-1"><FlagChips flags={h.flags} /></div>}
      </Link>
      {showQuestions && h.suggested_questions && h.suggested_questions.length > 0 && (
        <div className="border-t border-line px-3.5 py-2.5">
          <p className="eyebrow">Worth asking them</p>
          <ul className="mt-1 space-y-1 text-xs text-ink-2">
            {h.suggested_questions.map((q) => <li key={q}>· {q}</li>)}
          </ul>
        </div>
      )}
    </li>
  )
}

/** One line on a filing card. Says nothing when the network has nothing to add. */
export function NetworkStrip({ net }: { net: AnnouncementNetwork | null | undefined }) {
  if (!net) return null
  const withHits = net.people.find((p) => p.hits.length > 0)
  let text: string | null = null
  if (withHits) {
    const top = withHits.hits[0]
    const via = top.degree > 1 ? ` via ${top.path[1].name}` : ''
    const more = withHits.hits.length > 1 ? ` +${withHits.hits.length - 1}` : ''
    text = `${top.person.full_name}${via} can get you to ${withHits.filing_person.name}${more}`
  } else if (net.best_placed) {
    const b = net.best_placed
    const reason = b.why[0]?.text ? ` — ${b.why[0].text}` : ''
    text = `Best placed to explain this: ${b.person.full_name}${b.degree > 1 ? ` (via ${b.path[1].name})` : ''}${reason}`
  }
  if (!text) return null
  return (
    <p className="mt-2.5 flex items-start gap-1.5 rounded-lg border border-dashed border-line-strong px-2.5 py-1.5 text-xs text-ink-2">
      <Users size={13} className="mt-px shrink-0 text-ink-3" aria-hidden />
      <span><span className="font-semibold text-ink">Your network · </span>{text}</span>
    </p>
  )
}

/** The full network view of a filing, inside the filing sheet. */
export function NetworkBlock({ net }: { net: AnnouncementNetwork | null | undefined }) {
  if (!net) return null
  const people = net.people
  if (!people.length && !net.best_placed) return null
  return (
    <div>
      <p className="eyebrow flex items-center gap-1.5"><NetworkIcon size={12} aria-hidden /> Your network</p>
      <div className="mt-2 space-y-4">
        {people.map((p) => (
          <div key={p.person_id}>
            <p className="text-xs text-ink-2">
              Who can get you to <Link to={`/network/person/${encodeURIComponent(p.person_id)}`} className="font-semibold text-ink underline underline-offset-2">{p.filing_person.name}</Link>
            </p>
            {p.hits.length ? (
              <ul className="mt-1.5 space-y-2">{p.hits.map((h) => <PersonHitRow key={h.person.id} h={h} compact />)}</ul>
            ) : (
              <p className="mt-1 text-xs text-ink-3">No one in your network has crossed paths with {p.filing_person.name} on the record.</p>
            )}
          </div>
        ))}
        {net.best_placed && (
          <div>
            <p className="text-xs text-ink-2">Best placed to give you context on this event</p>
            <ul className="mt-1.5 space-y-2"><PersonHitRow h={net.best_placed} compact /></ul>
          </div>
        )}
      </div>
      <p className="mt-2 text-[11px] text-ink-3">Known links are relationships you recorded. Inferred links are career overlaps FINN computed from filings and profiles — verify before relying on them.</p>
    </div>
  )
}

/** Pull: who in the network can help understand this company. */
export function WhoToCall({ symbol }: { symbol: string }) {
  const r = useApi<CompanyContacts>(`/api/network/company/${symbol}/contacts`)
  return (
    <section id="who" className="scroll-mt-24">
      <SectionTitle aside={<Link to="/network" className="text-xs text-ink-3 underline underline-offset-2">Your network</Link>}>Who to call</SectionTitle>
      {r.error && !r.data ? (
        r.error.includes('Sign-in') ? <p className="text-sm text-ink-3">Sign in to see who in your network can help.</p>
          : <ErrorState message={r.error} onRetry={r.reload} />
      ) : !r.data ? (
        <SkeletonRows n={2} h={96} />
      ) : r.data.people.length ? (
        <>
          <ul className="space-y-2">{r.data.people.map((h) => <PersonHitRow key={h.person.id} h={h} showQuestions />)}</ul>
          <p className="mt-2 text-[11px] text-ink-3">{r.data.basis}</p>
        </>
      ) : r.data.theme_fallback.length ? (
        <>
          <p className="mb-2 text-sm text-ink-2">No one in your network has worked at {r.data.organization}, its competitors or suppliers. Closest sector experts:</p>
          <ul className="space-y-2">{r.data.theme_fallback.map((h) => <PersonHitRow key={h.person.id} h={h} compact />)}</ul>
        </>
      ) : (
        <EmptyState title={`No one in your network connects to ${r.data.organization}`}>
          <Link to="/network" className="underline underline-offset-2">Add someone you know</Link>
        </EmptyState>
      )}
      {r.data && r.data.in_the_news.length > 0 && (
        <div className="mt-3 rounded-lg bg-surface-2 px-3 py-2.5 text-xs">
          <p className="eyebrow">People in {r.data.organization}’s recent filings</p>
          <ul className="mt-1 space-y-1">
            {r.data.in_the_news.map((p) => (
              <li key={p.id}>
                <Link to={`/network/person/${encodeURIComponent(p.id)}`} className="flex items-center gap-1">
                  <span className="font-medium">{p.full_name}</span><span className="truncate text-ink-3">· {p.headline}</span>
                  <ChevronRight size={13} className="ml-auto shrink-0 text-ink-3" aria-hidden />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
