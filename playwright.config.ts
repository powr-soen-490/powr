// Source-File AI Declaration
// AI contribution: Below 50% AI-generated

import { defineConfig, devices } from '@playwright/test';

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
// import dotenv from 'dotenv';
// import path from 'path';
// dotenv.config({ path: path.resolve(__dirname, '.env') });

const E2E_FRONTEND_PORT = 5174;
const E2E_FRONTEND_URL = `http://localhost:${E2E_FRONTEND_PORT}`;
// Must match E2E_PORT in backend/tests/e2e_server.py.
const E2E_API_URL = 'http://localhost:8001';

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
  testDir: './e2e',
  /* Run tests in files in parallel */
  fullyParallel: true,
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  /* Opt out of parallel tests on CI. */
  workers: process.env.CI ? 1 : undefined,
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: 'html',
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('')`. */
    baseURL: E2E_FRONTEND_URL,

    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: 'on-first-retry',
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },

    /* Test against mobile viewports. */
    // {
    //   name: 'Mobile Chrome',
    //   use: { ...devices['Pixel 5'] },
    // },
    // {
    //   name: 'Mobile Safari',
    //   use: { ...devices['iPhone 12'] },
    // },

    /* Test against branded browsers. */
    // {
    //   name: 'Microsoft Edge',
    //   use: { ...devices['Desktop Edge'], channel: 'msedge' },
    // },
    // {
    //   name: 'Google Chrome',
    //   use: { ...devices['Desktop Chrome'], channel: 'chrome' },
    // },
  ],

  /*
   * The tests get their own frontend (5174) and backend (8001), separate from the ones you run
   * by hand, and the backend uses a database that is reset at the start of every run (see
   * backend/tests/e2e_server.py). Servers are never reused, so tests never hit stale code.
   */
  webServer: [
    {
      command: `npm run dev -- --port ${E2E_FRONTEND_PORT} --strictPort`,
      cwd: './frontend',
      url: E2E_FRONTEND_URL,
      env: { API_PROXY_TARGET: E2E_API_URL },
      reuseExistingServer: false,
    },
    {
      // Needs Python with the backend dependencies (the activated backend/.venv locally) and
      // PostgreSQL at DATABASE_URL, whose user may create databases.
      command: 'python -m tests.e2e_server',
      cwd: './backend',
      url: `${E2E_API_URL}/health`,
      reuseExistingServer: false,
    },
  ],
});
