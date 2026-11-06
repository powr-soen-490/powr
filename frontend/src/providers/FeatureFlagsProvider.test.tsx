// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import type { ReactNode } from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const providerCapture = vi.hoisted(() => ({ options: [] as unknown[] }))

vi.mock('@flagsmith/flagsmith/react', async () => {
  const React = await import('react')

  return {
    FlagsmithProvider: ({
      children,
      options,
    }: {
      children: ReactNode
      options: unknown
    }) => {
      providerCapture.options.push(options)
      return React.createElement(React.Fragment, null, children)
    },
  }
})

type ProviderOptions = {
  environmentID: string
  api?: string
  preventFetch: boolean
  defaultFlags: Record<string, { enabled: boolean; value: null }>
  onError: (error: Error) => void
}

async function loadProvider() {
  vi.resetModules()
  const module = await import('./FeatureFlagsProvider')
  return module.FeatureFlagsProvider
}

describe('FeatureFlagsProvider', () => {
  beforeEach(() => {
    providerCapture.options.length = 0
    vi.stubEnv('FLAGSMITH_ENVIRONMENT_KEY', '')
    vi.stubEnv('VITE_FLAGSMITH_API_URL', '')
    vi.stubEnv('DEV', true)
    vi.stubEnv('PROD', false)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('renders children and enables local defaults when no key is configured in dev', async () => {
    const FeatureFlagsProvider = await loadProvider()

    render(
      <FeatureFlagsProvider>
        <p>Dashboard</p>
      </FeatureFlagsProvider>,
    )

    expect(screen.getByText('Dashboard').textContent).toBe('Dashboard')
    const options = providerCapture.options[0] as ProviderOptions
    expect(options).toMatchObject({
      environmentID: 'local-defaults',
      preventFetch: true,
    })
    expect(Object.values(options.defaultFlags).every((flag) => flag.enabled)).toBe(true)
  })

  it('keeps production defaults off when the key is missing', async () => {
    vi.stubEnv('DEV', false)
    vi.stubEnv('PROD', true)
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const FeatureFlagsProvider = await loadProvider()

    render(
      <FeatureFlagsProvider>
        <p>Dashboard</p>
      </FeatureFlagsProvider>,
    )

    expect(consoleError).toHaveBeenCalledWith(
      'FLAGSMITH_ENVIRONMENT_KEY is missing; all feature pages will remain hidden.',
    )
    const options = providerCapture.options[0] as ProviderOptions
    expect(Object.values(options.defaultFlags).every((flag) => !flag.enabled)).toBe(true)
    expect(options.preventFetch).toBe(true)
  })

  it('uses the configured environment key and reports SDK errors', async () => {
    vi.stubEnv('FLAGSMITH_ENVIRONMENT_KEY', 'staging-client-key')
    vi.stubEnv('VITE_FLAGSMITH_API_URL', 'https://flags.example/api/')
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const FeatureFlagsProvider = await loadProvider()

    render(
      <FeatureFlagsProvider>
        <p>Dashboard</p>
      </FeatureFlagsProvider>,
    )

    const options = providerCapture.options[0] as ProviderOptions
    expect(options).toMatchObject({
      environmentID: 'staging-client-key',
      api: 'https://flags.example/api/',
      preventFetch: false,
    })
    const error = new Error('offline')
    options.onError(error)
    expect(consoleError).toHaveBeenCalledWith(
      'Unable to load Flagsmith feature flags.',
      error,
    )
  })
})
