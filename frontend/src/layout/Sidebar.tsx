// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useState } from 'react'
import { logout, type AuthUser } from '../api/auth'
import { NAV, type PageId } from './navigation'

export function Sidebar({
  page,
  onNavigate,
  user,
  onLoggedOut,
}: {
  page: PageId
  onNavigate: (page: PageId) => void
  user?: AuthUser
  onLoggedOut?: () => void
}) {
  const [loggingOut, setLoggingOut] = useState(false)

  async function handleLogout() {
    setLoggingOut(true)
    try {
      await logout()
      onLoggedOut?.()
    } catch {
      // Stay signed in when the server cannot be reached. The session is still valid.
    } finally {
      setLoggingOut(false)
    }
  }

  return (
    <nav className="sidebar" aria-label="Main">
      <div className="wordmark">POWR</div>
      {NAV.map((item) => (
        <button
          key={item.id}
          className={`nav-item ${item.id === page ? 'active' : ''}`}
          aria-current={item.id === page ? 'page' : undefined}
          onClick={() => onNavigate(item.id)}
        >
          {item.label}
        </button>
      ))}
      {user && onLoggedOut && (
        <div className="sidebar-session">
          <p>Logged in as {user.email}</p>
          <button type="button" className="nav-item" onClick={() => void handleLogout()} disabled={loggingOut}>
            {loggingOut ? 'Logging out…' : 'Log out'}
          </button>
        </div>
      )}
    </nav>
  )
}
