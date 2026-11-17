// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { SalesImportJob } from '../api/pos'
import { SalesImport } from './SalesImport'
import { Settings } from './Settings'

const LATEST = 'GET /api/pos/toast/imports/latest'
const START = 'POST /api/pos/toast/imports'
const fetchMock = vi.fn<typeof fetch>()

const running: SalesImportJob = {
  id: 'job-1',
  status: 'running',
  start_date: '2026-11-09',
  end_date: '2026-11-10',
  last_completed_date: null,
  days_completed: 0,
  total_days: 2,
  percent: 0,
  orders_imported: 0,
  items_imported: 0,
  error: null,
  created_at: '2026-11-17T15:00:00Z',
  finished_at: null,
}
const failed: SalesImportJob = {
  ...running,
  status: 'failed',
  last_completed_date: '2026-11-09',
  days_completed: 1,
  percent: 50,
  orders_imported: 56,
  items_imported: 110,
  error: 'Toast could not be reached. Retry later: the days already imported are kept.',
}
const done: SalesImportJob = {
  ...running,
  status: 'done',
  last_completed_date: '2026-11-10',
  days_completed: 2,
  percent: 100,
  orders_imported: 1_160,
  items_imported: 2_350,
  finished_at: '2026-11-17T15:01:00Z',
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

// Answers each "METHOD url" with its queued replies; the last reply repeats.
function serve(routes: Record<string, Response[]>) {
  fetchMock.mockImplementation(async (input, init) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    const queue = routes[key]
    if (!queue?.length) throw new Error(`Unexpected request: ${key}`)
    return (queue.length > 1 ? queue.shift()! : queue[0]).clone()
  })
}

function calls(key: string) {
  return fetchMock.mock.calls.filter(([input, init]) => `${init?.method ?? 'GET'} ${String(input)}` === key)
}

// Lets timers fire and fetch replies arrive, then re-renders.
async function wait(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

async function show() {
  render(<SalesImport onBack={vi.fn()} />)
  await wait()
}

describe('SalesImport', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-17T15:00:00Z'))
    fetchMock.mockReset()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('starts an import, shows its progress and the summary when it is done', async () => {
    serve({ [LATEST]: [json(null), json({ ...running, days_completed: 1, percent: 50, orders_imported: 56 }), json(done)], [START]: [json(running, 202)] })
    await show()
    expect((screen.getByLabelText('From') as HTMLInputElement).value).toBe('2024-01-01')
    expect((screen.getByLabelText('To') as HTMLInputElement).value).toBe('2026-11-16')

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-11-09' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-11-10' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start import' }))
    await wait()

    expect(JSON.parse(String(calls(START)[0][1]?.body))).toEqual({ start_date: '2026-11-09', end_date: '2026-11-10' })
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('0')
    expect(screen.getByText(/Keep this page open/)).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Start import' }).hasAttribute('disabled')).toBe(true)

    await wait(2000)
    expect(screen.getByText('56 orders imported · 50% done')).not.toBeNull()

    await wait(2000)
    expect(screen.queryByRole('progressbar')).toBeNull()
    expect(screen.getByText('1,160')).not.toBeNull()
    expect(screen.getByText('2,350')).not.toBeNull()
    expect(screen.getByText('2 days')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Import again' })).not.toBeNull()

    await wait(10_000)
    expect(calls(LATEST)).toHaveLength(3)  // no more polling once it is done
  })

  it('shows why a stopped import failed and retries it from where it stopped', async () => {
    serve({ [LATEST]: [json(failed), json(done)], 'POST /api/pos/toast/imports/job-1/retry': [json({ ...failed, status: 'running', error: null }, 202)] })
    await show()
    expect(screen.getByText('The import stopped.')).not.toBeNull()
    expect(screen.getByText(/Toast could not be reached\. .*56 orders are already saved/)).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Retry import' }))
    await wait()
    expect(screen.queryByText('The import stopped.')).toBeNull()
    expect(screen.getByText('56 orders imported · 50% done')).not.toBeNull()

    await wait(2000)
    expect(screen.getByRole('button', { name: 'Import again' })).not.toBeNull()
  })

  it('picks up an import that is already running when the page opens', async () => {
    serve({ [LATEST]: [json(running), json(done)] })
    await show()
    expect(screen.getByRole('progressbar')).not.toBeNull()

    await wait(2000)
    expect(screen.getByText('1,160')).not.toBeNull()
  })

  it('explains why an import could not start', async () => {
    serve({ [LATEST]: [json(null)], [START]: [json({ detail: 'An import is already running.' }, 409)] })
    await show()

    fireEvent.click(screen.getByRole('button', { name: 'Start import' }))
    await wait()

    expect(screen.getByText('An import is already running.')).not.toBeNull()
  })

  it('blocks the import when From is after To', async () => {
    serve({ [LATEST]: [json(null)] })
    await show()

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-11-01' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-10-01' } })

    expect(screen.getByText('Start date must be before the end date.')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Start import' }).hasAttribute('disabled')).toBe(true)
  })

  it('opens from POS Settings and goes back', async () => {
    serve({ [LATEST]: [json(null)] })
    render(<Settings />)

    fireEvent.click(screen.getAllByRole('button', { name: 'Open' })[1])
    await wait()
    expect(screen.getByRole('heading', { name: 'Import sales history' })).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '‹ Back to Settings' }))
    expect(screen.getByRole('heading', { name: 'Settings' })).not.toBeNull()
  })

  it('links to the Toast connection page', async () => {
    serve({ [LATEST]: [json(null)] })
    await show()

    expect(screen.getByRole('link', { name: 'Manage Toast connection' }).getAttribute('href')).toBe('/settings/pos')
  })
})
