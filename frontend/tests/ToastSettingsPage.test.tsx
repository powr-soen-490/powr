// Source-File AI Declaration
// AI contribution: 50% or more AI-generated
// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router'
import ToastSettingsPage from '../src/pages/ToastSettingsPage'

const owner = { user_id: 'user', restaurant_id: 'restaurant', email: 'owner@example.com', role: 'owner' }
const metadata = { id: 'connection', pos_name: 'TOAST', client_id: 'saved-client', expires_at: null }
const fetchMock = vi.fn<typeof fetch>()

function json(body: unknown, status = 200, requestId?: string) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...(requestId ? { 'X-Request-ID': requestId } : {}) },
  })
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

describe('Toast credential form', () => {
  it('connects through the API and clears the secret after submitting', async () => {
    fetchMock.mockResolvedValueOnce(json({}, 404))
      .mockResolvedValueOnce(json({ message: 'Saved' }))
      .mockResolvedValueOnce(json({ ...metadata, client_id: 'my-client' }))
    const view = show()
    await screen.findByText('Not connected')
    fill()
    expect((screen.getByLabelText('Client secret') as HTMLInputElement).type).toBe('password')
    fireEvent.click(screen.getByRole('button', { name: 'Connect Toast' }))
    await screen.findByText('Connected')

    expect(fetchMock.mock.calls[1]).toEqual(['/api/pos/credentials', {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pos_name: 'TOAST', client_id: 'my-client', client_secret: 'private-secret' }),
    }])
    expect((screen.getByLabelText('Client secret') as HTMLInputElement).value).toBe('')
    expect(view.container.innerHTML).not.toContain('private-secret')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('updates saved credentials and disconnects only after confirmation', async () => {
    fetchMock.mockResolvedValueOnce(json({ ...metadata, expires_at: '2020-01-01T00:00:00Z' }))
      .mockResolvedValueOnce(json({ message: 'Updated' }))
      .mockResolvedValueOnce(json({ ...metadata, client_id: 'updated-client' }))
      .mockResolvedValueOnce(json({ message: 'Deleted' }))
    show()
    await screen.findByText('Needs reconnect')
    expect((screen.getByLabelText('Client secret') as HTMLInputElement).value).toBe('')
    fill('updated-client', 'new-secret')
    fireEvent.click(screen.getByRole('button', { name: 'Update credentials' }))
    await screen.findByText('Connected')
    expect(fetchMock.mock.calls[1][1]?.method).toBe('PATCH')

    fireEvent.click(screen.getByRole('button', { name: 'Disconnect Toast' }))
    expect(fetchMock).toHaveBeenCalledTimes(3)
    fireEvent.click(screen.getByRole('button', { name: 'Confirm disconnect' }))
    await screen.findByText('Not connected')
    expect(fetchMock.mock.calls[3]).toEqual([
      '/api/pos/credentials?pos_name=TOAST', { method: 'DELETE', credentials: 'include' },
    ])
    expect((screen.getByLabelText('Client ID') as HTMLInputElement).value).toBe('')
  })

  it('does not expose the form or call owner APIs for a kitchen manager', () => {
    show('kitchen_manager')
    expect(screen.getByText(/Only restaurant owners/)).toBeTruthy()
    expect(screen.queryByLabelText('Client secret')).toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows the server request ID without echoing a failed request secret', async () => {
    fetchMock.mockResolvedValueOnce(json({}, 404))
      .mockResolvedValueOnce(json({ detail: 'private-secret' }, 500, 'request-123'))
    const view = show()
    await screen.findByText('Not connected')
    fill()
    fireEvent.click(screen.getByRole('button', { name: 'Connect Toast' }))
    await screen.findByText('request-123')
    expect(screen.getByRole('alert').textContent).not.toContain('private-secret')
    expect(view.container.innerHTML).not.toContain('private-secret')
    expect((screen.getByLabelText('Client secret') as HTMLInputElement).value).toBe('')
  })

  it('keeps saving disabled until the initial status request can be retried', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Network failure'))
      .mockResolvedValueOnce(json(metadata))
    show()
    await screen.findByRole('alert')
    expect((screen.getByLabelText('Client ID') as HTMLInputElement).closest('fieldset')?.disabled).toBe(true)
    expect(screen.queryByText('Not connected')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    await screen.findByText('Connected')
    await waitFor(() => expect((screen.getByLabelText('Client ID') as HTMLInputElement).value).toBe('saved-client'))
  })
})
