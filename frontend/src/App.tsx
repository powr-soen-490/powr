// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useState, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import './styles/tokens.css'
import './styles/global.css'
import type { AuthUser } from './api/auth'
import { Sidebar } from './layout/Sidebar'
import type { PageId } from './layout/navigation'
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
import ToastSettingsPage from './pages/ToastSettingsPage'

function Dashboard({ user, onLoggedOut }: { user?: AuthUser; onLoggedOut?: () => void }) {
  const [page, setPage] = useState<PageId>('home')

  const pages: Record<PageId, ReactNode> = {
    home: <Home onNavigate={setPage} />,
    orders: <RecommendedOrders />,
    forecast: <Forecast />,
    menu: <MenuMapping />,
    inventory: <Inventory />,
    settings: <Settings />,
  }

  return (
    <MockDataProvider>
      <ToastProvider>
        <div className="app">
          <Sidebar page={page} onNavigate={setPage} user={user} onLoggedOut={onLoggedOut} />
          <main className="content">{pages[page]}</main>
        </div>
      </ToastProvider>
    </MockDataProvider>
  )
}

function App() {
  const [user, setUser] = useState<AuthUser | null>(null)

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
      <Route
        path="/settings/pos"
        element={
          user ? (
            <ToastSettingsPage key={user.restaurant_id} user={user} />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
