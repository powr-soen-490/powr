// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useEffect, useRef, useState, type SubmitEvent } from 'react'
import { Link } from 'react-router'
import type { AuthUser } from '../api/auth'
import {
  disconnectToast, getToastCredentials, PosError, saveToastCredentials, type PosCredentials,
} from '../api/pos'
import AuthLayout from '../components/auth/AuthLayout'
import './ToastSettingsPage.css'

function ToastSettingsPage({ user }: { user: AuthUser }) {
  const owner = user.role === 'owner'
  const [saved, setSaved] = useState<PosCredentials | null>(null)
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
    getToastCredentials().then((credentials) => {
      if (!active) return
      setSaved(credentials)
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
      const credentials = await getToastCredentials()
      setSaved(credentials)
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
      await saveToastCredentials(clientId.trim(), secret, saved !== null)
      setNotice('Toast credentials saved. The saved secret cannot be viewed again.')
      // The write API returns a message, so read the saved public metadata separately.
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
      setClientId('')
      setConfirmDisconnect(false)
      setNotice('Toast disconnected. Saved credentials have been deleted.')
    } catch (failure) {
      setError(asPosError(failure))
    } finally {
      working.current = false
      setBusy(false)
    }
  }

  const expired = saved?.expires_at ? new Date(saved.expires_at).getTime() <= checkedAt : false
  const status = saved ? (expired ? 'Needs reconnect' : 'Connected') : 'Not connected'

  return (
    <AuthLayout title="Toast connection" subtitle="Manage your Toast API credentials."
      error={null} footer={<Link className="auth-link" to="/">Back to home</Link>}>
      {!owner ? <p>Only restaurant owners can view or change POS credentials.</p> : <>
        <p className="toast-status" role="status">
          Status: <strong>{loading ? 'Loading…' : loaded ? status : 'Unavailable'}</strong>
        </p>
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
                {saved ? 'Enter a new secret to update your credentials. ' : ''}
                Your saved secret is never shown again.
              </span>
            </div>
            <button className="auth-button toast-save" type="submit">
              {busy ? 'Saving…' : saved ? 'Update credentials' : 'Connect Toast'}
            </button>
          </fieldset>
        </form>
        {saved && <div className="toast-disconnect">
          {confirmDisconnect ? <div role="group" aria-label="Confirm disconnect">
            <p>Disconnect Toast and delete the saved credentials?</p>
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
