// Source-File AI Declaration
// AI contribution: Below 50% AI-generated

/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  envDir: '..',
  envPrefix: ['VITE_', 'FLAGSMITH_ENVIRONMENT_KEY'],
  plugins: [react()],
  server: {
    // File-change events from a Windows/macOS host don't reach a Docker bind mount, so the
    // container polls instead (VITE_USE_POLLING is set in docker-compose.yml).
    watch: process.env.VITE_USE_POLLING === 'true' ? { usePolling: true, interval: 300 } : undefined,
    // Same-origin /api in dev so the session cookie works without cross-site settings.
    proxy: {
      '/api': process.env.API_PROXY_TARGET ?? 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    coverage: {
      provider: 'v8',
      // lcov is uploaded to Codecov in CI; text prints a summary in the job log
      reporter: ['text', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/main.tsx', 'src/**/*.d.ts'],
    },
  },
})
