// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import type { ReactNode } from 'react'
import flagsmith, { type IFlags } from '@flagsmith/flagsmith'
import { FlagsmithProvider as FlagsmithReactProvider } from '@flagsmith/flagsmith/react'
import { PAGE_FLAGS, type PageFlag } from '../layout/navigation'

const environmentKey = import.meta.env.FLAGSMITH_ENVIRONMENT_KEY
const hasEnvironmentKey = Boolean(environmentKey)
const defaultFlags: IFlags<PageFlag> = {
  [PAGE_FLAGS.home]: { enabled: import.meta.env.DEV, value: null },
  [PAGE_FLAGS.orders]: { enabled: import.meta.env.DEV, value: null },
  [PAGE_FLAGS.forecast]: { enabled: import.meta.env.DEV, value: null },
  [PAGE_FLAGS.menu]: { enabled: import.meta.env.DEV, value: null },
  [PAGE_FLAGS.inventory]: { enabled: import.meta.env.DEV, value: null },
  [PAGE_FLAGS.settings]: { enabled: import.meta.env.DEV, value: null },
}

if (!hasEnvironmentKey && import.meta.env.PROD) {
  console.error('FLAGSMITH_ENVIRONMENT_KEY is missing; all feature pages will remain hidden.')
}

export function FeatureFlagsProvider({ children }: { children: ReactNode }) {
  return (
    <FlagsmithReactProvider
      flagsmith={flagsmith}
      options={{
        environmentID: environmentKey || 'local-defaults',
        api: import.meta.env.VITE_FLAGSMITH_API_URL || undefined,
        defaultFlags,
        preventFetch: !hasEnvironmentKey,
        onError: (error) => console.error('Unable to load Flagsmith feature flags.', error),
      }}
    >
      {children}
    </FlagsmithReactProvider>
  )
}
