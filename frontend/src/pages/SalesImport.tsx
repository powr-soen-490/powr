// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useEffect, useState } from 'react'
import { PageHeader } from '../layout/PageHeader'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { DateField } from '../components/fields'
import { SummaryCard } from '../components/SummaryCard'
import { SyncStatus } from '../components/SyncStatus'

// Fake data until the import status endpoint (#53) exists: the first run stops midway so the
// error and retry states can be seen, and the retry resumes from where it stopped.
const HISTORY_START = '2024-01-02'
const HISTORY_END = '2026-11-08'
const TOTAL_ORDERS = 48_210
const ITEMS_PER_ORDER = 2.6
const FAIL_AT = 45
const POLL_MS = 500

type Status = 'idle' | 'running' | 'failed' | 'done'

const number = new Intl.NumberFormat('en-US')

function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function daysBetween(start: string, end: string): number {
  return Math.round((Date.parse(end) - Date.parse(start)) / 86_400_000) + 1
}

export function SalesImport({ onBack }: { onBack: () => void }) {
  const [start, setStart] = useState(HISTORY_START)
  const [end, setEnd] = useState(HISTORY_END)
  const [status, setStatus] = useState<Status>('idle')
  const [percent, setPercent] = useState(0)
  const [failedOnce, setFailedOnce] = useState(false)

  const orders = Math.round(TOTAL_ORDERS * (percent / 100))
  const rangeError = start && end && start > end ? 'Start date must be before the end date.' : undefined

  useEffect(() => {
    if (status !== 'running') return
    const timer = setTimeout(() => {
      const next = Math.min(percent + 5, 100)
      if (!failedOnce && next >= FAIL_AT) {
        setFailedOnce(true)
        setStatus('failed')
      } else {
        setPercent(next)
        if (next === 100) setStatus('done')
      }
    }, POLL_MS)
    return () => clearTimeout(timer)
  }, [status, percent, failedOnce])

  function startImport() {
    setPercent(0)
    setFailedOnce(false)
    setStatus('running')
  }

  return (
    <>
      <PageHeader
        title="Import sales history"
        subtitle="Bring your Toast orders into POWR so the forecast learns from what you actually sold."
        actions={<Button variant="ghost" onClick={onBack}>‹ Back to Settings</Button>}
      />

      {status === 'failed' && (
        <Alert title="The import stopped." action={<Button size="sm" onClick={() => setStatus('running')}>Retry import</Button>}>
          Toast didn't respond. {number.format(orders)} orders are already saved; retrying continues from there.
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
          <DateField label="From" value={start} onChange={setStart} min={HISTORY_START} max={HISTORY_END}
            disabled={status === 'running'} error={rangeError} />
          <DateField label="To" value={end} onChange={setEnd} min={HISTORY_START} max={HISTORY_END}
            disabled={status === 'running'} />
          <Button variant="primary" onClick={startImport}
            disabled={status === 'running' || !start || !end || Boolean(rangeError)}>
            {status === 'done' ? 'Import again' : 'Start import'}
          </Button>
        </div>
      </section>

      {(status === 'running' || status === 'failed') && (
        <section className="card" aria-label="Import progress">
          <h2>Importing orders</h2>
          <SyncStatus
            text={`${number.format(orders)} of ${number.format(TOTAL_ORDERS)} orders imported · ${percent}% done`}
            progress={percent}
          />
        </section>
      )}

      {status === 'done' && (
        <section className="stack" aria-label="Import summary">
          <SyncStatus text={`Import complete · ${formatDate(start)} – ${formatDate(end)}`} />
          <div className="grid-3">
            <SummaryCard label="Orders imported" value={number.format(orders)} />
            <SummaryCard label="Items imported" value={number.format(Math.round(orders * ITEMS_PER_ORDER))} />
            <SummaryCard label="Date span" value={`${number.format(daysBetween(start, end))} days`}
              note={`${formatDate(start)} – ${formatDate(end)}`} />
          </div>
        </section>
      )}
    </>
  )
}
