// Source-File AI Declaration
// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../src/App'

const USER = {
  user_id: '00000000-0000-0000-0000-000000000001',
  restaurant_id: '00000000-0000-0000-0000-000000000002',
  restaurant_name: 'Test Bistro',
  email: 'chef@example.com',
  role: 'owner',
}

function mockMe(response: Response | Error) {
  const fetchMock = vi.fn(() =>
    response instanceof Error ? Promise.reject(response) : Promise.resolve(response),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('App session restore', () => {
  it('restores the user from the session cookie on a full page load', async () => {
    const fetchMock = mockMe(new Response(JSON.stringify(USER), { status: 200 }))

    renderAt('/login')

    // A restored user is sent away from /login instead of seeing the form.
    expect(await screen.findByRole('navigation')).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Log in' })).toBeNull()
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/me', { credentials: 'include' })
  })

  it('redirects to /login when there is no valid session', async () => {
    mockMe(new Response(null, { status: 401 }))

    renderAt('/')

    expect(await screen.findByRole('button', { name: 'Log in' })).toBeTruthy()
  })

  it('redirects to /login when the server cannot be reached', async () => {
    mockMe(new TypeError('Failed to fetch'))

    renderAt('/')

    expect(await screen.findByRole('button', { name: 'Log in' })).toBeTruthy()
  })
})
