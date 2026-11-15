import { Bell, BookOpenText, Layers, MessageCircle, Moon, RotateCw, Search, Sun, Users } from 'lucide-react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { useApp } from '../context/AppContext'
import { useApi } from '../hooks/useApi'
import type { Company } from '../services/api'
import { relTime } from '../utils/format'

const TABS = [
  { to: '/', label: 'Today', icon: BookOpenText, end: true },
  { to: '/feed', label: 'Feed', icon: Layers },
  { to: '/research', label: 'Research', icon: Search },
  { to: '/network', label: 'Network', icon: Users },
  { to: '/ask', label: 'Ask', icon: MessageCircle },
]

function section(path: string) {
  if (path === '/') return 'TODAY'
  const first = path.split('/')[1] ?? ''
  if (first === 'network' && path.includes('/person/')) return 'PERSON'
  return first.toUpperCase() || 'TODAY'
}

/** A scrolling strip of the portfolio's last close: the terminal's heartbeat. */
function Ticker() {
  const { refreshTick } = useApp()
  const p = useApi<{ companies: Company[] }>(`/api/portfolio?t=${refreshTick}`)
  const items = (p.data?.companies ?? []).filter((c) => c.market?.return_pct != null)
  if (!items.length) return <div className="h-7 border-b border-line bg-surface" aria-hidden />
  const row = items.map((c) => {
    const r = c.market!.return_pct!
    return (
      <Link key={c.symbol} to={`/research/${c.symbol}`} className="flex items-center gap-1.5 px-3">
        <span className="text-ink-2">{c.symbol}</span>
        <span className={r > 0 ? 'text-up' : r < 0 ? 'text-down' : 'text-ink-3'}>
          {r > 0 ? '▲' : r < 0 ? '▼' : '■'}{Math.abs(r).toFixed(2)}
        </span>
      </Link>
    )
  })
  return (
    <div className="ticker h-7 overflow-hidden border-b border-line bg-surface" aria-label="Portfolio, last close">
      <div className="ticker-track num flex h-7 items-center text-[11px]">
        {row}
        <span aria-hidden className="flex">{row}</span>
      </div>
    </div>
  )
}

export function AppShell() {
  const { refresh, startRefresh, theme, setTheme } = useApp()
  const { pathname } = useLocation()
  const running = refresh?.state === 'running' || refresh?.state === 'started'
  const dark = theme !== 'light'

  return (
    <div className="term-bg min-h-dvh">
      <div className="mx-auto flex min-h-dvh max-w-xl flex-col">
        <header className="sticky top-0 z-20 bg-page/95 backdrop-blur">
          <div className="flex h-11 items-center gap-2 border-b border-line px-4">
            <span className="mono text-[13px] font-bold tracking-tight text-accent">FINN</span>
            <span className="mono text-[13px] font-semibold text-ink">▸ {section(pathname)}<span className="cursor-blink text-accent">_</span></span>
            <span className="mono ml-1 min-w-0 truncate text-[10.5px] uppercase tracking-wide text-ink-3" aria-live="polite">
              {running ? `● updating · ${refresh?.step ?? 'starting'}` : refresh?.finished_at ? `synced ${relTime(refresh.finished_at)}` : 'eod data'}
            </span>
            <div className="ml-auto flex items-center">
              <Link to="/alerts" aria-label="Alerts and alert rules" className="grid size-8 place-items-center rounded text-ink-2 hover:bg-surface-2 hover:text-ink">
                <Bell size={15} aria-hidden />
              </Link>
              <button onClick={() => void startRefresh()} disabled={running} aria-label="Refresh data"
                className="grid size-8 place-items-center rounded text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-60">
                <RotateCw size={15} className={running ? 'animate-spin' : ''} aria-hidden />
              </button>
              <button onClick={() => setTheme(dark ? 'light' : 'dark')} aria-label={`Switch to ${dark ? 'light' : 'dark'} theme`}
                className="grid size-8 place-items-center rounded text-ink-2 hover:bg-surface-2 hover:text-ink">
                {dark ? <Sun size={15} aria-hidden /> : <Moon size={15} aria-hidden />}
              </button>
            </div>
          </div>
          <Ticker />
        </header>

        <main className="flex-1 px-4 pb-24 pt-3">
          <Outlet />
        </main>

        <nav className="pb-safe fixed inset-x-0 bottom-0 z-20 border-t border-line bg-page/95 backdrop-blur" aria-label="Main">
          <ul className="mx-auto grid max-w-xl grid-cols-5">
            {TABS.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink to={to} end={end}
                  className={({ isActive }) => `relative flex h-14 flex-col items-center justify-center gap-1 ${isActive ? 'text-ink' : 'text-ink-3'}`}>
                  {({ isActive }) => (
                    <>
                      {isActive && <span className="absolute inset-x-5 top-0 h-[2px] bg-accent-fill" aria-hidden />}
                      <Icon size={18} strokeWidth={isActive ? 2.25 : 1.75} className={isActive && to === '/network' ? 'text-net' : ''} aria-hidden />
                      <span className="mono text-[9.5px] font-semibold uppercase tracking-[0.08em]">{label}</span>
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </div>
  )
}
