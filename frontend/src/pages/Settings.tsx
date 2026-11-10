// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useState, type ReactNode } from 'react'
import { PageHeader } from '../layout/PageHeader'
import { SalesImport } from './SalesImport'

function SettingsRow({ title, description, children, onClick }: {
  title: string
  description?: string
  children?: ReactNode
  onClick?: () => void
}) {
  return (
    <div className="settings-row">
      <div className="settings-row-copy">
        <strong>{title}</strong>
        {description && <span className="label">{description}</span>}
      </div>
      <div className="settings-row-control">
        {children ?? (
          <button type="button" className="settings-link" onClick={onClick}>
            Open <span aria-hidden="true">›</span>
          </button>
        )}
      </div>
    </div>
  )
}

export function Settings() {
  const [theme, setTheme] = useState('light')
  const [unit, setUnit] = useState('metric')
  const [view, setView] = useState<'main' | 'pos'>('main')

  if (view === 'pos') return <SalesImport onBack={() => setView('main')} />

  return (
    <>
      <PageHeader title="Settings" subtitle="Your account, POS connection and preferences" />

      <section className="card settings-panel" aria-label="Settings">
        <SettingsRow
          title="Account Settings"
          description="Manage your profile and restaurant details."
        />
        <SettingsRow
          title="POS Settings"
          description="Manage your Toast connection and import your sales history."
          onClick={() => setView('pos')}
        />
        <SettingsRow title="Theme" description="Choose the appearance of POWR.">
          <div className="pill-options" role="group" aria-label="Theme">
            {['light', 'dark'].map((option) => (
              <button
                key={option}
                type="button"
                className={`pill-toggle${theme === option ? ' on' : ''}`}
                aria-pressed={theme === option}
                onClick={() => setTheme(option)}
              >
                {option[0].toUpperCase() + option.slice(1)}
              </button>
            ))}
          </div>
        </SettingsRow>
        <SettingsRow title="Unit" description="Choose how quantities are displayed.">
          <label className="select-wrap settings-select">
            <span className="visually-hidden">Unit system</span>
            <select className="select" value={unit} onChange={(event) => setUnit(event.target.value)}>
              <option value="metric">Metric</option>
              <option value="imperial">Imperial</option>
            </select>
          </label>
        </SettingsRow>
        <SettingsRow
          title="Other"
          description="Notifications, appearance and other preferences."
        />
      </section>
    </>
  )
}
