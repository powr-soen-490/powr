// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useEffect, useState } from 'react'
import { PageHeader } from '../layout/PageHeader'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { DateField } from '../components/fields'
import { SummaryCard } from '../components/SummaryCard'
import { SyncStatus } from '../components/SyncStatus'
import {
  PosError,
  getLatestSalesImport,
  retrySalesImport,
  startSalesImport,
  type SalesImportJob,
} from '../api/pos'

// Mykonos Grill's Toast history starts in 2024 (story #52); the server uses the same default.
const HISTORY_START = '2024-01-01'
// How often the page asks for progress while an import runs. Each poll also keeps the
// free-tier server awake, which is why the page asks the owner to keep it open.
const POLL_MS = 2000
// A business day ends after closing, often around 4am the next morning, so the newest day
// that can be imported is the one that ended 36 hours after midnight UTC (as on the server).
const BUSINESS_DAY_SETTLE_MS = 36 * 60 * 60 * 1000

const number = new Intl.NumberFormat('en-US')

function lastFinishedBusinessDay(now: number = Date.now()): string {
  return new Date(now - BUSINESS_DAY_SETTLE_MS).toISOString().slice(0, 10)
}

function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function errorMessage(error: unknown): string {
  return error instanceof PosError ? error.message : 'Something went wrong. Try again.'
}

export function SalesImport({ onBack }: { onBack: () => void }) {
  const latestDay = lastFinishedBusinessDay()
  const [start, setStart] = useState(HISTORY_START)
  const [end, setEnd] = useState(latestDay)
  const [job, setJob] = useState<SalesImportJob | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [requestError, setRequestError] = useState<string | null>(null)

  const running = job?.status === 'running'
  const rangeError = start && end && start > end ? 'Start date must be before the end date.' : undefined

  // Load the latest import when the page opens, and keep polling while it runs.
  useEffect(() => {
    if (!loading && !running) return
    let cancelled = false
    const timer = setTimeout(async () => {
      try {
        const latest = await getLatestSalesImport()
        if (!cancelled) {
          setJob(latest)
          setRequestError(null)
        }
      } catch (error) {
        if (!cancelled) setRequestError(errorMessage(error))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }, loading ? 0 : POLL_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [loading, running, job])

  async function send(action: () => Promise<SalesImportJob>) {
    setBusy(true)
    setRequestError(null)
    try {
      setJob(await action())
    } catch (error) {
      setRequestError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Import sales history"
        subtitle="Bring your Toast orders into POWR so the forecast learns from what you actually sold."
        actions={<>
          <Button variant="ghost" onClick={onBack}>‹ Back to Settings</Button>
          <a className="btn btn-secondary" href="/settings/pos">Manage Toast connection</a>
        </>}
      />

      {requestError && <Alert title="Something went wrong.">{requestError}</Alert>}

      {job?.status === 'failed' && (
        <Alert
          title="The import stopped."
          action={<Button size="sm" disabled={busy} onClick={() => send(() => retrySalesImport(job.id))}>Retry import</Button>}
        >
          {job.error} {number.format(job.orders_imported)} orders are already saved; retrying continues from there.
        </Alert>
      )}

      <section className="card import-card" aria-label="Import range">
        <div className="card-head">
          <div>
            <h2>Date range</h2>
            <div className="label">Defaults to all the history available in Toast.</div>
          </div>
        </div>
        <div className="field-row import-range">
          <DateField label="From" value={start} onChange={setStart} min={HISTORY_START} max={latestDay}
            disabled={running} error={rangeError} />
          <DateField label="To" value={end} onChange={setEnd} min={HISTORY_START} max={latestDay}
            disabled={running} />
          <Button variant="primary" onClick={() => send(() => startSalesImport(start, end))}
            disabled={loading || busy || running || !start || !end || Boolean(rangeError)}>
            {job?.status === 'done' ? 'Import again' : 'Start import'}
          </Button>
        </div>
      </section>

      {(job?.status === 'running' || job?.status === 'failed') && (
        <section className="card" aria-label="Import progress">
          <h2>Importing orders</h2>
          <SyncStatus
            text={`${number.format(job.orders_imported)} orders imported · ${job.percent}% done`}
            progress={job.percent}
          />
          {running && (
            <div className="label">
              Day {number.format(job.days_completed)} of {number.format(job.total_days)}.
              Keep this page open until the import finishes.
            </div>
          )}
        </section>
      )}

      {job?.status === 'done' && (
        <section className="stack" aria-label="Import summary">
          <SyncStatus text={`Import complete · ${formatDate(job.start_date)} – ${formatDate(job.end_date)}`} />
          <div className="grid-3">
            <SummaryCard label="Orders imported" value={number.format(job.orders_imported)} />
            <SummaryCard label="Items imported" value={number.format(job.items_imported)} />
            <SummaryCard label="Date span" value={`${number.format(job.total_days)} days`}
              note={`${formatDate(job.start_date)} – ${formatDate(job.end_date)}`} />
          </div>
        </section>
      )}
    </>
  )
}
