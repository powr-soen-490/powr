// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

export interface PosCredentials {
  id: string
  pos_name: string
  client_id: string
  // True when Toast rejected the saved client ID or secret; reconnecting clears it.
  needs_reconnect: boolean
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

// Why connecting failed, by status code. The server's own text is never shown. When adding or
// changing a status code here, update CONNECT_ERRORS in backend/app/api/toast_connection.py too.
const CONNECT_ERRORS: Record<number, string> = {
  400: "Toast didn't accept this client ID and secret. Check them and try again.",
  404: "These Toast credentials can't access any restaurant.",
  409: "These Toast credentials can access more than one restaurant, which POWR doesn't support yet.",
  429: 'Toast is limiting logins right now. Wait a few minutes and try again.',
  502: "Couldn't reach Toast. Try again later.",
}

// `errors` maps status codes to messages; key 0 replaces the message for any other failure.
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
    // A message in `errors` wins, so each caller can word its own failures.
    const message = errors[response.status] ?? (response.status === 401
      ? 'Your session has expired. Log in again.'
      : response.status === 403
        ? 'Only restaurant owners can manage POS credentials.'
        : errors[0] ?? 'Could not save or load Toast credentials. Try again.')
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
  return {
    id: body.id, pos_name: body.pos_name, client_id: body.client_id,
    needs_reconnect: body.needs_reconnect === true,
  }
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

export interface SalesImportJob {
  id: string
  status: 'running' | 'failed' | 'done'
  start_date: string
  end_date: string
  last_completed_date: string | null
  days_completed: number
  total_days: number
  percent: number
  orders_imported: number
  items_imported: number
  // Why the import stopped, written by the server for the owner; null unless it failed.
  error: string | null
  created_at: string
  finished_at: string | null
}

const IMPORTS_URL = '/api/pos/toast/imports'

// Why starting or retrying failed, by status code. When adding or changing a status code here,
// update IMPORT_ERRORS in backend/app/api/toast_import.py too.
const IMPORT_ERRORS: Record<number, string> = {
  0: 'Could not start or load the import. Try again.',
  403: 'Only restaurant owners can import sales.',
}
const START_IMPORT_ERRORS: Record<number, string> = {
  ...IMPORT_ERRORS,
  404: 'Connect Toast before importing sales.',
  409: 'An import is already running.',
  422: "Those dates can't be imported. Pick days that have already finished, with From before To.",
}
const RETRY_IMPORT_ERRORS: Record<number, string> = {
  ...IMPORT_ERRORS,
  404: 'Connect Toast again, then retry the import.',
  409: 'This import is not stopped anymore. Refresh the page.',
}

function salesImportJob(body: SalesImportJob): SalesImportJob {
  return {
    id: body.id,
    status: body.status,
    start_date: body.start_date,
    end_date: body.end_date,
    last_completed_date: body.last_completed_date,
    days_completed: body.days_completed,
    total_days: body.total_days,
    percent: body.percent,
    orders_imported: body.orders_imported,
    items_imported: body.items_imported,
    error: body.error,
    created_at: body.created_at,
    finished_at: body.finished_at,
  }
}

// The restaurant's latest sales import, or null when it has never imported.
export async function getLatestSalesImport(): Promise<SalesImportJob | null> {
  const response = await request('GET', `${IMPORTS_URL}/latest`, undefined, IMPORT_ERRORS)
  const body = await response.json() as SalesImportJob | null
  return body === null ? null : salesImportJob(body)
}

// Starts importing the business days from start to end in the background.
export async function startSalesImport(start: string, end: string): Promise<SalesImportJob> {
  const response = await request(
    'POST', IMPORTS_URL, { start_date: start, end_date: end }, START_IMPORT_ERRORS,
  )
  return salesImportJob(await response.json() as SalesImportJob)
}

// Continues a failed import from the day after the last one it saved.
export async function retrySalesImport(id: string): Promise<SalesImportJob> {
  const response = await request(
    'POST', `${IMPORTS_URL}/${encodeURIComponent(id)}/retry`, undefined, RETRY_IMPORT_ERRORS,
  )
  return salesImportJob(await response.json() as SalesImportJob)
}
