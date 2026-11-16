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

export interface ToastConnection {
  location_id: string
  location_name: string | null
}

const API_BASE_URL: string = import.meta.env.VITE_API_URL ?? ''
const CREDENTIALS_URL = '/api/pos/credentials'
const CONNECTION_URL = '/api/pos/toast/connection'

// Why connecting failed, by status code. The server's own text is never shown.
const CONNECT_ERRORS: Record<number, string> = {
  400: "Toast didn't accept this client ID and secret. Check them and try again.",
  404: "These Toast credentials can't access any restaurant.",
  409: "These Toast credentials can access more than one restaurant, which POWR doesn't support yet.",
  429: 'Toast is limiting logins right now. Wait a few minutes and try again.',
  502: "Couldn't reach Toast. Try again later.",
}

async function request(
  method: string, path: string, body?: unknown, errors: Record<number, string> = {},
): Promise<Response> {
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
        : errors[response.status] ?? 'Could not save or load Toast credentials. Try again.'
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

export async function getToastConnection(): Promise<ToastConnection | null> {
  const response = await request('GET', CONNECTION_URL)
  if (response.status === 404) return null
  const body = await response.json() as ToastConnection
  return { location_id: body.location_id, location_name: body.location_name }
}

// Toast checks the credentials and the restaurant GUID is found from them; nothing is saved
// unless that works.
export async function connectToast(clientId: string, clientSecret: string): Promise<ToastConnection> {
  const response = await request(
    'PUT', CONNECTION_URL, { client_id: clientId, client_secret: clientSecret }, CONNECT_ERRORS,
  )
  const body = await response.json() as ToastConnection
  return { location_id: body.location_id, location_name: body.location_name }
}

export async function disconnectToast(): Promise<void> {
  await request('DELETE', CONNECTION_URL)
}
