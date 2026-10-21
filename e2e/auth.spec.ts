// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { expect, test } from '@playwright/test'
import { expectLoginScreen, logIn, logOut, newOwner, signUp, signedInAs } from './auth'

// The database starts empty (see backend/tests/e2e_server.py). This test creates the only
// account it needs, so there is no seed data.
test('an owner signs up, logs out, and logs back in', async ({ page }) => {
  const owner = newOwner()

  await signUp(page, owner)
  await expect(signedInAs(page, owner.email)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Log out', exact: true })).toBeEnabled()

  await logOut(page)
  await expectLoginScreen(page)
  // The cookie was revoked, not only hidden: the session no longer exists.
  expect((await page.request.get('/api/auth/me')).status()).toBe(401)

  await logIn(page, owner)
  await expect(signedInAs(page, owner.email)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Log out', exact: true })).toBeEnabled()
})
