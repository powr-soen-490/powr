// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router'
import App from './App'
import { PAGE_FLAG_NAMES, type PageFlag } from './layout/navigation'

const flagHooks = vi.hoisted(() => ({
  useFlags: vi.fn(),
  useFlagsmithLoading: vi.fn(),
}))

vi.mock('@flagsmith/flagsmith/react', () => flagHooks)

function makeFlags(enabled: PageFlag[] = []) {
  return Object.fromEntries(
    PAGE_FLAG_NAMES.map((name) => [name, { enabled: enabled.includes(name), value: null }]),
  )
}

function renderDashboard() {
  return render(
    <MemoryRouter initialEntries={['/mockup']}>
      <App />
    </MemoryRouter>,
  )
}

describe('feature-flagged dashboard', () => {
  beforeEach(() => {
    flagHooks.useFlags.mockReturnValue(makeFlags(PAGE_FLAG_NAMES))
    flagHooks.useFlagsmithLoading.mockReturnValue({ isLoading: false, error: null })
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('shows a loading state while Flagsmith loads', () => {
    flagHooks.useFlagsmithLoading.mockReturnValue({ isLoading: true, error: null })

    renderDashboard()

    expect(screen.getByRole('status').textContent).toContain('Loading feature flags…')
    expect(screen.queryByRole('navigation', { name: 'Main' })).toBeNull()
  })

  it('shows only enabled pages and selects an enabled page when Home is disabled', () => {
    flagHooks.useFlags.mockReturnValue(makeFlags(['page_forecast']))

    renderDashboard()

    expect(screen.queryByRole('button', { name: 'Home' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Forecast' }).getAttribute('aria-current')).toBe(
      'page',
    )
    expect(screen.getByRole('heading', { name: 'Forecast' })).not.toBeNull()
  })

  it('shows the empty state when all pages are disabled', () => {
    flagHooks.useFlags.mockReturnValue(makeFlags())

    renderDashboard()

    expect(screen.getByRole('status').textContent).toContain(
      'No pages are enabled for this environment.',
    )
    expect(screen.getByRole('navigation', { name: 'Main' })).not.toBeNull()
    expect(screen.queryByRole('button', { name: 'Home' })).toBeNull()
  })

  it('reports refresh errors while keeping disabled pages hidden', () => {
    flagHooks.useFlags.mockReturnValue(makeFlags(['page_home']))
    flagHooks.useFlagsmithLoading.mockReturnValue({
      isLoading: false,
      error: new Error('offline'),
    })

    renderDashboard()

    expect(screen.getByRole('alert').textContent).toContain(
      'Feature flags could not be refreshed. Disabled pages remain hidden.',
    )
    expect(screen.queryByRole('button', { name: 'Home' })).not.toBeNull()
    expect(screen.queryByRole('button', { name: 'Forecast' })).toBeNull()
  })

  it('navigates to another enabled page', () => {
    renderDashboard()

    fireEvent.click(screen.getByRole('button', { name: 'Forecast' }))

    expect(screen.getByRole('heading', { name: 'Forecast' })).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Forecast' }).getAttribute('aria-current')).toBe(
      'page',
    )
  })
})
