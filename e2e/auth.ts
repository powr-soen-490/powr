// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { expect, type Page } from '@playwright/test'

// Meets the server password policy. Shared by every owner this file creates.
export const PASSWORD = 'Str0ng!Password'

export interface Owner {
  restaurantName: string
  email: string
  password: string
}

// A new owner each call, so parallel tests never sign up the same email.
export function newOwner(): Owner {
  return {
    restaurantName: 'Mykonos Grill',
    email: `owner-${crypto.randomUUID()}@example.com`,
    password: PASSWORD,
  }
}

export async function signUp(page: Page, owner: Owner): Promise<void> {
  await page.goto('/signup')
  await page.getByLabel('Restaurant name').fill(owner.restaurantName)
  await page.getByLabel('Work email').fill(owner.email)
  await page.getByRole('textbox', { name: 'Password' }).fill(owner.password)
  await page.getByRole('checkbox', { name: /End User License Agreement/ }).check()
  await page.getByRole('button', { name: 'Create account' }).click()
}

export async function logIn(page: Page, owner: Owner): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Email').fill(owner.email)
  await page.getByRole('textbox', { name: 'Password' }).fill(owner.password)
  await page.getByRole('button', { name: 'Log in', exact: true }).click()
}

export async function logOut(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Log out', exact: true }).click()
}

export function signedInAs(page: Page, email: string) {
  return page.getByText(`Logged in as ${email}`)
}

export async function expectLoginScreen(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('heading', { name: 'Welcome' })).toBeVisible()
}
