// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { SalesImport } from './SalesImport'
import { Settings } from './Settings'

// Advances the simulated import one poll at a time so each render can schedule the next timer.
function advancePolls(count: number) {
  for (let i = 0; i < count; i++) {
    act(() => {
      vi.advanceTimersByTime(500)
    })
  }
}

describe('SalesImport', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  it('fails midway, resumes on retry and shows the summary', () => {
    render(<SalesImport onBack={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: 'Start import' }))
    expect(screen.getByRole('progressbar')).not.toBeNull()

    advancePolls(9)
    expect(screen.getByText('The import stopped.')).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Retry import' }))
    expect(screen.queryByText('The import stopped.')).toBeNull()

    advancePolls(20)
    expect(screen.getByText('48,210')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Import again' })).not.toBeNull()
  })

  it('blocks the import when From is after To', () => {
    render(<SalesImport onBack={vi.fn()} />)

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-11-01' } })
    fireEvent.change(screen.getByLabelText('To'), { target: { value: '2026-10-01' } })

    expect(screen.getByText('Start date must be before the end date.')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Start import' }).hasAttribute('disabled')).toBe(true)
  })

  it('opens from POS Settings and goes back', () => {
    render(<Settings />)

    fireEvent.click(screen.getAllByRole('button', { name: 'Open' })[1])
    expect(screen.getByRole('heading', { name: 'Import sales history' })).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '‹ Back to Settings' }))
    expect(screen.getByRole('heading', { name: 'Settings' })).not.toBeNull()
  })
})
