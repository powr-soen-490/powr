// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Home } from './Home'

describe('Home page feature flags', () => {
  afterEach(cleanup)

  it('hides tasks and the next-orders card when their pages are disabled', () => {
    const onNavigate = vi.fn()

    render(<Home onNavigate={onNavigate} enabledPages={new Set(['home'])} />)

    expect(screen.queryByText('Needs attention')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Next orders' })).toBeNull()
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('shows and routes only tasks whose target pages are enabled', () => {
    const onNavigate = vi.fn()

    render(<Home onNavigate={onNavigate} enabledPages={new Set(['orders'])} />)

    expect(screen.getByText('2 orders to review')).not.toBeNull()
    expect(screen.queryByText('Eggs will run out Saturday')).toBeNull()
    expect(screen.queryByText('3 menu items not mapped')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Next orders' })).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Review orders' }))

    expect(onNavigate).toHaveBeenCalledWith('orders')

    fireEvent.click(screen.getByRole('button', { name: 'Go to recommended orders →' }))

    expect(onNavigate).toHaveBeenLastCalledWith('orders')
  })

  it('hides all task and order shortcuts when no target page is enabled', () => {
    const onNavigate = vi.fn()

    render(<Home onNavigate={onNavigate} enabledPages={new Set()} />)

    expect(screen.queryByText('Needs attention')).toBeNull()
    expect(screen.queryByRole('heading', { name: 'Next orders' })).toBeNull()
    expect(screen.queryByRole('heading', { name: 'How POWR is doing' })).not.toBeNull()
  })
})
