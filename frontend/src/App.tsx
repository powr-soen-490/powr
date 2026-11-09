// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useEffect, useState, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { useFlags, useFlagsmithLoading } from '@flagsmith/flagsmith/react'
import './styles/tokens.css'
import './styles/global.css'
import { fetchCurrentUser, type AuthUser } from './api/auth'
import { Sidebar } from './layout/Sidebar'
import { getVisibleNavigation, PAGE_FLAG_NAMES, PAGE_FLAGS, type PageId } from './layout/navigation'
import { ToastProvider } from './components/Toast'
import { MockDataProvider } from './mocks/MockDataProvider'
import { Home } from './pages/Home'
import { RecommendedOrders } from './pages/RecommendedOrders'
import { Forecast } from './pages/Forecast'
import { MenuMapping } from './pages/MenuMapping'
import { Inventory } from './pages/Inventory'
import { Settings } from './pages/Settings'
import LoginPage from './pages/LoginPage'
import SignupPage from './pages/SignupPage'

function Dashboard({ user, onLoggedOut }: { user?: AuthUser; onLoggedOut?: () => void }) {
  const [page, setPage] = useState<PageId>('home')
  const flags = useFlags(PAGE_FLAG_NAMES)
  const loading = useFlagsmithLoading()
  const isPageEnabled = (pageId: PageId) => flags[PAGE_FLAGS[pageId]]?.enabled ?? false
  const navigation = getVisibleNavigation((flag) => flags[flag]?.enabled ?? false)
  const enabledPages = new Set(navigation.map(({ id }) => id))
  const selectedPage = navigation.some((item) => item.id === page)
    ? page
    : navigation[0]?.id ?? null

  const pages: Record<PageId, ReactNode> = {
    home: <Home onNavigate={setPage} enabledPages={enabledPages} />,
    orders: <RecommendedOrders />,
    forecast: <Forecast />,
    menu: <MenuMapping />,
    inventory: <Inventory />,
    settings: <Settings />,
  }

  if (loading?.isLoading) {
    return <main className="content"><p role="status">Loading feature flags…</p></main>
  }

  return (
    <MockDataProvider>
      <ToastProvider>
        <div className="app">
          <Sidebar
            page={selectedPage}
            items={navigation}
            onNavigate={(nextPage) => {
              if (isPageEnabled(nextPage)) setPage(nextPage)
            }}
            user={user}
            onLoggedOut={onLoggedOut}
          />
          <main className="content">
            {loading?.error && (
              <p role="alert">Feature flags could not be refreshed. Disabled pages remain hidden.</p>
            )}
            {selectedPage ? pages[selectedPage] : (
              <section className="card" role="status">
                No pages are enabled for this environment.
              </section>
            )}
          </main>
        </div>
      </ToastProvider>
    </MockDataProvider>
  )
}

function App() {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [checkingSession, setCheckingSession] = useState(true)

  // On a full page load, restore the user from the session cookie before routing,
  // so protected routes don't redirect to /login while the check is in flight.
  useEffect(() => {
    let cancelled = false
    void fetchCurrentUser().then((currentUser) => {
      if (cancelled) return
      // Keep a user who logged in while the check was in flight.
      setUser((existing) => existing ?? currentUser)
      setCheckingSession(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  if (checkingSession) {
    return null
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={user ? <Navigate to="/" replace /> : <LoginPage onLoggedIn={setUser} />}
      />
      <Route
        path="/signup"
        element={user ? <Navigate to="/" replace /> : <SignupPage onSignedUp={setUser} />}
      />
      <Route
        path="/"
        element={
          user ? (
            <Dashboard user={user} onLoggedOut={() => setUser(null)} />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />
      <Route path="/mockup" element={<Dashboard />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
