// Source-File AI Declaration
// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { SALES_IMPORT_LINK } from '../src/layout/navigation'
import ToastSettingsPage from '../src/pages/ToastSettingsPage'

const owner = { user_id: 'user', restaurant_id: 'restaurant', email: 'owner@example.com', role: 'owner' }
const metadata = { id: 'credential', pos_name: 'TOAST', client_id: 'saved-client', needs_reconnect: false }
const mykonos = { location_id: 'guid-1', location_name: 'Mykonos Grill - Boca NEW' }
const CREDENTIALS = 'GET /api/pos/credentials?pos_name=TOAST'
const CONNECTION = 'GET /api/pos/toast/connection'
const CONNECT = 'PUT /api/pos/toast/connection'
const DISCONNECT = 'DELETE /api/pos/toast/connection'
const fetchMock = vi.fn<typeof fetch>()

function json(body: unknown, status = 200, requestId?: string) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...(requestId ? { 'X-Request-ID': requestId } : {}) },
  })
}

// Answers each "METHOD url" with its queued replies; the last reply repeats.
function serve(routes: Record<string, (Response | Error)[]>) {
  fetchMock.mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    const queue = routes[key]
    if (!queue?.length) throw new Error(`Unexpected request: ${key}`)
    const reply = queue.length > 1 ? queue.shift()! : queue[0]
    if (reply instanceof Error) throw reply
    return reply.clone()
  })
}

function calls(key: string) {
  return fetchMock.mock.calls.filter(([input, init]) => `${init?.method ?? 'GET'} ${String(input)}` === key)
}

function show(role = 'owner') {
  return render(<MemoryRouter><ToastSettingsPage user={{ ...owner, role }} /></MemoryRouter>)
}

function fill(clientId = 'my-client', secret = 'private-secret') {
  fireEvent.change(screen.getByLabelText('Client ID'), { target: { value: clientId } })
  fireEvent.change(screen.getByLabelText('Client secret'), { target: { value: secret } })
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('Toast connection form', () => {
  it('connects without asking for a restaurant GUID and shows the restaurant Toast found', async () => {
    serve({
      [CREDENTIALS]: [json({}, 404), json({ ...metadata, client_id: 'my-client' })],
      [CONNECTION]: [json({}, 404), json(mykonos)],
      [CONNECT]: [json(mykonos)],
    })
    const view = show()
    await screen.findByText('Not connected')
    expect(screen.queryByLabelText(/GUID/i)).toBeNull()
    fill()
    expect((screen.getByLabelText('Client secret') as HTMLInputElement).type).toBe('password')
    fireEvent.click(screen.getByRole('button', { name: 'Connect Toast' }))
    await screen.findByText('Connected')

    expect(calls(CONNECT)).toEqual([['/api/pos/toast/connection', {
      method: 'PUT', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_id: 'my-client', client_secret: 'private-secret' }),
    }]])
    expect(screen.getByText('Mykonos Grill - Boca NEW')).toBeTruthy()
    expect(screen.getByText(/Connected to Mykonos Grill - Boca NEW\./)).toBeTruthy()
    expect((screen.getByLabelText('Client secret') as HTMLInputElement).value).toBe('')
    expect(view.container.innerHTML).not.toContain('private-secret')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('updates the connection and disconnects only after confirmation', async () => {
    serve({
      [CREDENTIALS]: [json({ ...metadata, needs_reconnect: true }), json(metadata)],
      [CONNECTION]: [json(mykonos)],
      [CONNECT]: [json(mykonos)],
      [DISCONNECT]: [json({ message: 'Toast disconnected.' })],
    })
    show()
    await screen.findByText('Needs reconnect')
    expect(screen.getByText(/Toast rejected the saved client ID or secret/)).toBeTruthy()
    expect(screen.getByText('Mykonos Grill - Boca NEW')).toBeTruthy()
    expect((screen.getByLabelText('Client secret') as HTMLInputElement).value).toBe('')
    fill('updated-client', 'new-secret')
    fireEvent.click(screen.getByRole('button', { name: 'Update connection' }))
    await screen.findByText('Connected')
    expect(screen.queryByText(/Toast rejected the saved client ID or secret/)).toBeNull()
    expect(calls(CONNECT)).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: 'Disconnect Toast' }))
    expect(calls(DISCONNECT)).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Confirm disconnect' }))
    await screen.findByText('Not connected')
    expect(calls(DISCONNECT)).toEqual([['/api/pos/toast/connection', { method: 'DELETE', credentials: 'include' }]])
    expect(screen.queryByText('Mykonos Grill - Boca NEW')).toBeNull()
    expect((screen.getByLabelText('Client ID') as HTMLInputElement).value).toBe('')
  })

  it('stays connected when the server reports an old token expiry', async () => {
    // A token expiring on its own is renewed by the server; only needs_reconnect matters.
    serve({
      [CREDENTIALS]: [json({ ...metadata, expires_at: '2020-01-01T00:00:00Z' })],
      [CONNECTION]: [json(mykonos)],
    })
    show()
    await screen.findByText('Connected')
    expect(screen.queryByText('Needs reconnect')).toBeNull()
  })

  it('asks to reconnect when the restaurant is linked but the saved login is gone', async () => {
    serve({ [CREDENTIALS]: [json({}, 404)], [CONNECTION]: [json(mykonos)] })
    show()
    await screen.findByText('Not connected')
    expect((screen.getByLabelText('Client ID') as HTMLInputElement).value).toBe('')
    expect(screen.getByRole('button', { name: 'Connect Toast' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Disconnect Toast' })).toBeTruthy()
  })

  it('does not treat a login shared by another restaurant as its own connection', async () => {
    serve({ [CREDENTIALS]: [json(metadata)], [CONNECTION]: [json({}, 404)] })
    show()
    await screen.findByText('Not connected')
    expect(screen.getByRole('button', { name: 'Connect Toast' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Disconnect Toast' })).toBeNull()
    expect((screen.getByLabelText('Client ID') as HTMLInputElement).value).toBe('')
  })

  it('falls back to a generic name when the connected restaurant has no saved name', async () => {
    const unnamed = { location_id: 'guid-1', location_name: null }
    serve({
      [CREDENTIALS]: [json({}, 404), json(metadata)],
      [CONNECTION]: [json({}, 404), json(unnamed)],
      [CONNECT]: [json(unnamed)],
    })
    show()
    await screen.findByText('Not connected')
    fill()
    fireEvent.click(screen.getByRole('button', { name: 'Connect Toast' }))
    await screen.findByText('Connected')

    expect(screen.getByText(/Connected to your Toast restaurant\./)).toBeTruthy()
    expect(screen.getByText('your Toast restaurant')).toBeTruthy()
  })

  it('does not expose the form or call owner APIs for a kitchen manager', () => {
    show('kitchen_manager')
    expect(screen.getByText(/Only restaurant owners/)).toBeTruthy()
    expect(screen.queryByLabelText('Client secret')).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it.each([
    [400, "Toast didn't accept this client ID and secret"],
    [404, "can't access any restaurant"],
    [409, 'more than one restaurant'],
    [429, 'Toast is limiting logins'],
    [502, "Couldn't reach Toast"],
    [500, 'Could not save or load Toast credentials'],
  ])('explains a %i from connecting without echoing the server or the secret', async (status, message) => {
    serve({
      [CREDENTIALS]: [json({}, 404)],
      [CONNECTION]: [json({}, 404)],
      [CONNECT]: [json({ detail: 'private-secret' }, status, 'request-123')],
    })
    const view = show()
    await screen.findByText('Not connected')
    fill()
    fireEvent.click(screen.getByRole('button', { name: 'Connect Toast' }))
    await screen.findByText('request-123')
    expect(screen.getByRole('alert').textContent).toContain(message)
    expect(view.container.innerHTML).not.toContain('private-secret')
    expect(screen.getByText('Not connected')).toBeTruthy()
    expect((screen.getByLabelText('Client secret') as HTMLInputElement).value).toBe('')
  })

  it('keeps saving disabled until the initial status request can be retried', async () => {
    serve({
      [CREDENTIALS]: [new TypeError('Network failure'), json(metadata)],
      [CONNECTION]: [json(mykonos)],
    })
    show()
    await screen.findByRole('alert')
    expect((screen.getByLabelText('Client ID') as HTMLInputElement).closest('fieldset')?.disabled).toBe(true)
    expect(screen.queryByText('Not connected')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await screen.findByText('Connected')
    await waitFor(() => expect((screen.getByLabelText('Client ID') as HTMLInputElement).value).toBe('saved-client'))
  })
})

// Stands in for the dashboard: shows the state the back link sent along.
function DashboardStandIn() {
  return <p>Dashboard opened with {JSON.stringify(useLocation().state)}</p>
}

describe('Back link to Import sales history', () => {
  it.each([
    { status: 'Not connected', credentials: json({}, 404), connection: json({}, 404) },
    { status: 'Connected', credentials: json(metadata), connection: json(mykonos) },
  ])('shows when the page says $status', async ({ status, credentials, connection }) => {
    serve({ [CREDENTIALS]: [credentials], [CONNECTION]: [connection] })
    show()
    await screen.findByText(status)
    expect(screen.getByRole('link', { name: '‹ Back to Import sales history' })).toBeTruthy()
  })

  it('opens the dashboard asking for Import sales history', async () => {
    serve({ [CREDENTIALS]: [json({}, 404)], [CONNECTION]: [json({}, 404)] })
    render(
      <MemoryRouter initialEntries={['/settings/pos']}>
        <Routes>
          <Route path="/settings/pos" element={<ToastSettingsPage user={owner} />} />
          <Route path="/" element={<DashboardStandIn />} />
        </Routes>
      </MemoryRouter>,
    )
    await screen.findByText('Not connected')
    fireEvent.click(screen.getByRole('link', { name: '‹ Back to Import sales history' }))
    expect(screen.getByText(`Dashboard opened with ${JSON.stringify(SALES_IMPORT_LINK)}`)).toBeTruthy()
  })
})
