// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

// The signed-in user, as returned by login and sign-up.
export interface AuthUser {
  user_id: string
  restaurant_id: string
  email: string
  role: string
}

export interface SignupRequest {
  restaurantName: string
  email: string
  password: string
  eulaAccepted: boolean
  eulaVersion: string
}

export class AuthError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'AuthError'
  }
}

const API_BASE_URL: string = import.meta.env.VITE_API_URL ?? ''

const NETWORK_ERROR = 'Could not reach the server. Check your connection and try again.'
const SERVER_ERROR = 'Something went wrong on our side. Try again in a moment.'

async function postJson(path: string, body: unknown): Promise<Response> {
  try {
    return await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new AuthError(NETWORK_ERROR)
  }
}

async function readDetail(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
      return body.detail
    }
  } catch {
    // Not JSON; fall through.
  }
  return null
}

// Log in with email and password, then the backend sets the session cookie after successful authentication.
export async function login(email: string, password: string): Promise<AuthUser> {
  const response = await postJson('/api/auth/login', { email, password })
  if (response.ok) {
    return (await response.json()) as AuthUser
  }
  if (response.status === 401 || response.status === 422) {
    throw new AuthError('Email or password is incorrect. Try again.')
  }
  if (response.status === 429) {
    throw new AuthError('Too many failed attempts. Wait a few minutes and try again.')
  }
  throw new AuthError(SERVER_ERROR)
}

// Create a restaurant and its owner account, then the backend signs the new user in.
export async function signup(request: SignupRequest): Promise<AuthUser> {
  const response = await postJson('/api/auth/signup', {
    restaurant_name: request.restaurantName,
    email: request.email,
    password: request.password,
    eula_accepted: request.eulaAccepted,
    eula_version: request.eulaVersion,
  })
  if (response.ok) {
    return (await response.json()) as AuthUser
  }
  if (response.status === 400) {
    // Password-policy and EULA messages are written for the user.
    throw new AuthError((await readDetail(response)) ?? 'Check the form and try again.')
  }
  if (response.status === 409) {
    // The backend deliberately doesn't say whether the email is taken.
    throw new AuthError(
      "We couldn't create an account with these details. If you already have one, log in instead.",
    )
  }
  if (response.status === 422) {
    throw new AuthError('Check the form and try again.')
  }
  throw new AuthError(SERVER_ERROR)
}

// Ends the session on the server and clears the cookie.
export async function logout(): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    })
  } catch {
    throw new AuthError(NETWORK_ERROR)
  }
  if (!response.ok) {
    throw new AuthError(SERVER_ERROR)
  }
}
