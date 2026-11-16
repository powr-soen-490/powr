// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useEffect, useRef, useState, type SubmitEvent } from 'react'
import { Link } from 'react-router'
import type { AuthUser } from '../api/auth'
import {
  connectToast, disconnectToast, getToastConnection, getToastCredentials, PosError,
  type PosCredentials, type ToastConnection,
} from '../api/pos'
import AuthLayout from '../components/auth/AuthLayout'
import './ToastSettingsPage.css'

function ToastSettingsPage({ user }: { user: AuthUser }) {
  const owner = user.role === 'owner'
  const [saved, setSaved] = useState<PosCredentials | null>(null)
  const [connection, setConnection] = useState<ToastConnection | null>(null)
  const [clientId, setClientId] = useState('')
  const [clientSecret, setClientSecret] = useState('')
  const [loading, setLoading] = useState(owner)
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<PosError | null>(null)
  const [notice, setNotice] = useState('')
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)
  const [checkedAt, setCheckedAt] = useState(0)
  const working = useRef(false)

  useEffect(() => {
    if (!owner) return
    let active = true
    Promise.all([getToastCredentials(), getToastConnection()]).then(([credentials, restaurant]) => {
      if (!active) return
      setSaved(credentials)
      setConnection(restaurant)
      setCheckedAt(Date.now())
      setClientId(credentials?.client_id ?? '')
      setLoaded(true)
    }).catch((failure: unknown) => {
      if (active) setError(asPosError(failure))
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [owner])

  async function reload() {
    setLoading(true)
    setError(null)
    try {
      const [credentials, restaurant] = await Promise.all([getToastCredentials(), getToastConnection()])
      setSaved(credentials)
      setConnection(restaurant)
      setCheckedAt(Date.now())
      setClientId(credentials?.client_id ?? '')
      setLoaded(true)
    } catch (failure) {
      setError(asPosError(failure))
    } finally {
      setLoading(false)
    }
  }

  async function save(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!owner || !loaded || working.current) return
    working.current = true
    setBusy(true)
    setError(null)
    setNotice('')
    const secret = clientSecret
    setClientSecret('')
    try {
      // Toast checks the credentials and POWR finds the restaurant GUID from them.
      const restaurant = await connectToast(clientId.trim(), secret)
      setNotice(`Connected to ${restaurant.location_name ?? 'your Toast restaurant'}. `
        + 'The saved secret cannot be viewed again.')
      // The connect API does not return the credential metadata, so read it separately.
      setLoaded(false)
      await reload()
    } catch (failure) {
      setError(asPosError(failure))
    } finally {
      working.current = false
      setBusy(false)
    }
  }

  async function disconnect() {
    if (!owner || working.current) return
    working.current = true
    setBusy(true)
    setError(null)
    setNotice('')
    setClientSecret('')
    try {
      await disconnectToast()
      setSaved(null)
      setConnection(null)
      setClientId('')
      setConfirmDisconnect(false)
      setNotice('Toast disconnected. Saved credentials and the connected restaurant have been removed.')
    } catch (failure) {
      setError(asPosError(failure))
    } finally {
      working.current = false
      setBusy(false)
    }
  }

  const connected = saved !== null && connection !== null
  const expired = saved?.expires_at ? new Date(saved.expires_at).getTime() <= checkedAt : false
  const status = connected ? (expired ? 'Needs reconnect' : 'Connected') : 'Not connected'

  return (
    <AuthLayout title="Toast connection"
      subtitle="Enter your Toast API credentials. POWR finds your restaurant automatically."
      error={null} footer={<Link className="auth-link" to="/">Back to home</Link>}>
      {!owner ? <p>Only restaurant owners can view or change POS credentials.</p> : <>
        <p className="toast-status" role="status">
          Status: <strong>{loading ? 'Loading…' : loaded ? status : 'Unavailable'}</strong>
        </p>
        {loaded && connected && <p className="toast-status">
          Connected to: <strong>{connection.location_name ?? 'your Toast restaurant'}</strong>
        </p>}
        {error && <div className="toast-error" role="alert">
          <p>{error.message}</p>
          {error.requestId && <p>Request ID: <code>{error.requestId}</code></p>}
          {!loaded && <button type="button" onClick={reload} disabled={loading}>Retry</button>}
        </div>}
        {notice && <p className="toast-notice" role="status">{notice}</p>}
        <form className="auth-form" onSubmit={save}>
          <fieldset className="toast-fields" disabled={loading || busy || !loaded}>
            <label className="field" htmlFor="toast-client-id">
              <span className="field-label">Client ID</span>
              <input id="toast-client-id" className="field-input" autoComplete="off"
                value={clientId} onChange={(event) => setClientId(event.target.value)}
                required pattern=".*\S.*" />
            </label>
            <div className="field">
              <label className="field-label" htmlFor="toast-client-secret">Client secret</label>
              <input id="toast-client-secret" className="field-input" type="password"
                autoComplete="new-password" value={clientSecret} required
                aria-describedby="toast-secret-help"
                onChange={(event) => setClientSecret(event.target.value)} />
              <span className="field-hint" id="toast-secret-help">
                {connected ? 'Enter a new secret to update your connection. ' : ''}
                Your saved secret is never shown again.
              </span>
            </div>
            <button className="auth-button toast-save" type="submit">
              {busy ? 'Checking with Toast…' : connected ? 'Update connection' : 'Connect Toast'}
            </button>
          </fieldset>
        </form>
        {(saved || connection) && <div className="toast-disconnect">
          {confirmDisconnect ? <div role="group" aria-label="Confirm disconnect">
            <p>Disconnect Toast and remove the saved credentials and connected restaurant?</p>
            <div className="toast-actions">
              <button type="button" disabled={busy} onClick={() => setConfirmDisconnect(false)}>Cancel</button>
              <button type="button" className="toast-danger" disabled={busy} onClick={disconnect}>
                {busy ? 'Disconnecting…' : 'Confirm disconnect'}
              </button>
            </div>
          </div> : <button type="button" className="toast-danger" disabled={busy || loading || !loaded}
            onClick={() => setConfirmDisconnect(true)}>Disconnect Toast</button>}
        </div>}
      </>}
    </AuthLayout>
  )
}

function asPosError(error: unknown): PosError {
  return error instanceof PosError ? error : new PosError('Something went wrong. Try again.')
}

export default ToastSettingsPage
