// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

export interface PosCredentials {
  id: string
  pos_name: string
  client_id: string
  expires_at: string | null
}

export class PosError extends Error {
  requestId: string | null

  constructor(message: string, requestId: string | null = null) {
    super(message)
    this.name = 'PosError'
    this.requestId = requestId
  }
}

const API_BASE_URL: string = import.meta.env.VITE_API_URL ?? ''
const CREDENTIALS_URL = '/api/pos/credentials'

async function request(method: string, path: string, body?: unknown): Promise<Response> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      credentials: 'include',
      ...(body === undefined ? {} : {
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    })
  } catch {
    throw new PosError('Could not reach the server. Check your connection and try again.')
  }
  if (!response.ok && !(method === 'GET' && response.status === 404)) {
    const message = response.status === 401
      ? 'Your session has expired. Log in again.'
      : response.status === 403
        ? 'Only restaurant owners can manage POS credentials.'
        : 'Could not save or load Toast credentials. Try again.'
    // Do not display arbitrary response text that could contain a submitted secret.
    throw new PosError(message, response.headers.get('X-Request-ID'))
  }
  return response
}

export async function getToastCredentials(): Promise<PosCredentials | null> {
  const response = await request('GET', `${CREDENTIALS_URL}?pos_name=TOAST`)
  if (response.status === 404) return null
  const body = await response.json() as PosCredentials
  // Only keep the public metadata, even if the server adds other fields later.
  return { id: body.id, pos_name: body.pos_name, client_id: body.client_id, expires_at: body.expires_at }
}

export async function saveToastCredentials(
  clientId: string, clientSecret: string, updating: boolean,
): Promise<void> {
  await request(updating ? 'PATCH' : 'POST', CREDENTIALS_URL, {
    pos_name: 'TOAST', client_id: clientId, client_secret: clientSecret,
  })
}

export async function disconnectToast(): Promise<void> {
  await request('DELETE', `${CREDENTIALS_URL}?pos_name=TOAST`)
}
