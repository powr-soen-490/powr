// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

/** @vitest-environment jsdom */

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router'
import { AuthError, logout } from '../src/api/auth'
import App from '../src/App'
import { NAV } from '../src/layout/navigation'
import { Sidebar } from '../src/layout/Sidebar'
import { FeatureFlagsProvider } from '../src/providers/FeatureFlagsProvider'

const OWNER = {
  user_id: '11111111-1111-1111-1111-111111111111',
  restaurant_id: '22222222-2222-2222-2222-222222222222',
  email: 'john@example.com',
  role: 'owner',
}

function okLogout(): Response {
  return new Response(null, { status: 200 })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('logout', () => {
  it('posts to the logout endpoint', async () => {
    vi.mocked(fetch).mockResolvedValue(okLogout())

    await logout()

    expect(fetch).toHaveBeenCalledWith('/api/auth/logout', {
      method: 'POST',
      credentials: 'include',
    })
  })

  it('throws when the server cannot be reached', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))

    await expect(logout()).rejects.toBeInstanceOf(AuthError)
  })

  it('throws when the server returns an error', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 500 }))

    await expect(logout()).rejects.toBeInstanceOf(AuthError)
  })
})

describe('Sidebar', () => {
  it('hides the session when nobody is signed in', () => {
    render(<Sidebar page="home" items={NAV} onNavigate={() => undefined} />)

    expect(screen.queryByRole('button', { name: 'Log out' })).toBeNull()
  })

  it('shows who is signed in and logs them out', async () => {
    const onLoggedOut = vi.fn()
    vi.mocked(fetch).mockResolvedValue(okLogout())
    render(
      <Sidebar
        page="home"
        items={NAV}
        onNavigate={() => undefined}
        user={OWNER}
        onLoggedOut={onLoggedOut}
      />,
    )

    expect(screen.getByText('Logged in as john@example.com')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Log out', exact: true }))

    await waitFor(() => expect(onLoggedOut).toHaveBeenCalledTimes(1))
  })

  it('stays signed in when logout fails', async () => {
    const onLoggedOut = vi.fn()
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'))
    render(
      <Sidebar
        page="home"
        items={NAV}
        onNavigate={() => undefined}
        user={OWNER}
        onLoggedOut={onLoggedOut}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Log out', exact: true }))

    await waitFor(() => expect(fetch).toHaveBeenCalled())
    expect(onLoggedOut).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Log out', exact: true })).toBeTruthy()
  })
})

describe('App', () => {
  it('sends signed-out visitors from home to login', async () => {
    // The session check finds no cookie, so the visitor is signed out.
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 401 }))
    render(
      <MemoryRouter initialEntries={['/']}>
        <FeatureFlagsProvider>
          <App />
        </FeatureFlagsProvider>
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Welcome' })).toBeTruthy()
  })

  it('shows the dashboard log out button after a successful login', async () => {
    // First call is the session check on load (no session yet), then the login itself.
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 401 }))
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify(OWNER), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    render(
      <MemoryRouter initialEntries={['/login']}>
        <FeatureFlagsProvider>
          <App />
        </FeatureFlagsProvider>
      </MemoryRouter>,
    )

    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: OWNER.email } })
    fireEvent.change(screen.getByPlaceholderText('Your password'), {
      target: { value: 'Str0ng!Password' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Log in', exact: true }))

    expect(await screen.findByText(`Logged in as ${OWNER.email}`)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Log out', exact: true })).toBeTruthy()
  })
})
