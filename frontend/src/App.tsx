import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { SkeletonRows } from './components/ui'
import { AppProvider } from './context/AppContext'
import { AppShell } from './layouts/AppShell'
import { AlertsPage } from './pages/Alerts'
import { AskPage } from './pages/Ask'
import { FeedPage } from './pages/Feed'
import { TodayPage } from './pages/Today'

// Charts live only on Research; loading them lazily keeps the daily brief fast on a phone.
const ResearchPage = lazy(() => import('./pages/Research').then((m) => ({ default: m.ResearchPage })))
const NetworkPage = lazy(() => import('./pages/Network').then((m) => ({ default: m.NetworkPage })))
const PersonPage = lazy(() => import('./pages/Person').then((m) => ({ default: m.PersonPage })))
const PrivacyPage = lazy(() => import('./pages/Person').then((m) => ({ default: m.PrivacyPage })))

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<TodayPage />} />
            <Route path="feed" element={<FeedPage />} />
            <Route path="alerts" element={<AlertsPage />} />
            <Route path="research" element={<Suspense fallback={<SkeletonRows n={4} />}><ResearchPage /></Suspense>} />
            <Route path="research/:symbol" element={<Suspense fallback={<SkeletonRows n={4} h={120} />}><ResearchPage /></Suspense>} />
            <Route path="network" element={<Suspense fallback={<SkeletonRows n={4} h={80} />}><NetworkPage /></Suspense>} />
            <Route path="network/privacy" element={<Suspense fallback={<SkeletonRows n={3} />}><PrivacyPage /></Suspense>} />
            <Route path="network/person/:id" element={<Suspense fallback={<SkeletonRows n={4} h={90} />}><PersonPage /></Suspense>} />
            <Route path="ask" element={<AskPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  )
}
