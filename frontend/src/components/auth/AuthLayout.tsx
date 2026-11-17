// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useState, type ReactNode, type Ref } from 'react'
import './AuthLayout.css'

export function AlertIcon() {
  return (
    <svg className="alert-icon" viewBox="0 0 16 16" aria-hidden="true">
      <circle cx="8" cy="8" r="6.75" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 4.5v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="8" cy="11.25" r="0.9" fill="currentColor" />
    </svg>
  )
}

export function FieldError({ id, message }: { id: string; message: string | null }) {
  if (!message) return null
  return (
    <p id={id} className="field-error">
      <AlertIcon />
      {message}
    </p>
  )
}

function EyeIcon({ crossed }: { crossed: boolean }) {
  return (
    <svg className="eye-icon" viewBox="0 0 20 20" aria-hidden="true">
      <path
        d="M1.75 10S4.75 4.25 10 4.25 18.25 10 18.25 10 15.25 15.75 10 15.75 1.75 10 1.75 10Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="10" cy="10" r="2.75" fill="none" stroke="currentColor" strokeWidth="1.5" />
      {crossed && (
        <path d="M3.5 3.5l13 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      )}
    </svg>
  )
}

interface TextFieldProps {
  id: string
  label: string
  type: 'text' | 'email' | 'password'
  autoComplete: string
  placeholder: string
  value: string
  error: string | null
  // Help text shown under the input while there is no error.
  hint?: string
  inputRef?: Ref<HTMLInputElement>
  onChange: (value: string) => void
  onBlur?: () => void
}

export function TextField({
  id,
  label,
  type,
  autoComplete,
  placeholder,
  value,
  error,
  hint,
  inputRef,
  onChange,
  onBlur,
}: TextFieldProps) {
  const [passwordVisible, setPasswordVisible] = useState(false)
  const isPassword = type === 'password'
  const errorId = `${id}-error`
  const hintId = `${id}-hint`
  return (
    <div className="field">
      <label htmlFor={id} className="field-label">{label}</label>
      <div className="field-control">
        <input
          ref={inputRef}
          id={id}
          type={isPassword && passwordVisible ? 'text' : type}
          autoComplete={autoComplete}
          // A revealed password is plain text so we don't want the browser to spell-check it or try to auto-correct it.
          spellCheck={isPassword ? false : undefined}
          autoCapitalize={isPassword ? 'off' : undefined}
          autoCorrect={isPassword ? 'off' : undefined}
          placeholder={placeholder}
          className="field-input"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onBlur={onBlur}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? errorId : hint ? hintId : undefined}
        />
        {isPassword && (
          <button
            type="button"
            className="password-toggle"
            aria-label={passwordVisible ? 'Hide password' : 'Show password'}
            aria-controls={id}
            onClick={() => setPasswordVisible((visible) => !visible)}
          >
            <EyeIcon crossed={passwordVisible} />
          </button>
        )}
      </div>
      {error ? (
        <FieldError id={errorId} message={error} />
      ) : (
        hint && <p id={hintId} className="field-hint">{hint}</p>
      )}
    </div>
  )
}

export function SubmitButton({
  pending,
  label,
  pendingLabel,
}: {
  pending: boolean
  label: string
  pendingLabel: string
}) {
  return (
    <button type="submit" className="auth-button" disabled={pending}>
      {pending && <span className="spinner" aria-hidden="true" />}
      {pending ? pendingLabel : label}
    </button>
  )
}

interface AuthLayoutProps {
  title: string
  subtitle: string
  // Shown in the corner alert when set
  error: { title: string; message: string } | null
  footer: ReactNode
  // Optional link shown above the title, e.g. back to the page the user came from
  backLink?: ReactNode
  children: ReactNode
}

// Shared frame for the login, sign-up and Toast connection pages: brand, card, footer and
// error alert.
function AuthLayout({ title, subtitle, error, footer, backLink, children }: AuthLayoutProps) {
  return (
    <div className="auth-page">
      {error && (
        <div className="auth-alert" role="alert">
          <AlertIcon />
          <div>
            <p className="auth-alert-title">{error.title}</p>
            <p className="auth-alert-body">{error.message}</p>
          </div>
        </div>
      )}

      <main className="auth-main">
        <p className="auth-brand">POWR</p>

        <section className="auth-card" aria-labelledby="auth-heading">
          {backLink && <div className="auth-back">{backLink}</div>}
          <h1 id="auth-heading" className="auth-heading">{title}</h1>
          <p className="auth-subheading">{subtitle}</p>
          {children}
        </section>

        <p className="auth-footer">{footer}</p>
      </main>
    </div>
  )
}

export default AuthLayout
