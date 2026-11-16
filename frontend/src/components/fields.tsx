// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useId, type ReactNode } from 'react'
import { Icon } from './Icon'
import { IconButton } from './Button'

type FieldShellProps = {
  id: string
  label: string
  hideLabel?: boolean
  help?: string
  error?: string
  className?: string
  children: ReactNode
}

// Label above, control, then help or error text below (Figma B2).
function FieldShell({ id, label, hideLabel, help, error, className, children }: FieldShellProps) {
  return (
    <div className={['field', className].filter(Boolean).join(' ')}>
      <label htmlFor={id} className={hideLabel ? 'visually-hidden' : 'field-label'}>{label}</label>
      {children}
      {error ? (
        <div id={`${id}-msg`} className="field-error"><Icon name="alert-circle" size={14} />{error}</div>
      ) : help ? (
        <div id={`${id}-msg`} className="field-help">{help}</div>
      ) : null}
    </div>
  )
}

type BaseProps = {
  label: string
  value: string
  onChange: (value: string) => void
  hideLabel?: boolean
  help?: string
  error?: string
  disabled?: boolean
  compact?: boolean
  className?: string
}

function controlProps(id: string, { help, error, disabled }: BaseProps) {
  return {
    id,
    disabled,
    'aria-invalid': error ? true : undefined,
    'aria-describedby': help || error ? `${id}-msg` : undefined,
  }
}

export function TextField(props: BaseProps & { placeholder?: string; type?: 'text' | 'email' | 'tel' }) {
  const id = useId()
  const { value, onChange, placeholder, type = 'text', compact } = props
  return (
    <FieldShell id={id} {...props}>
      <input
        {...controlProps(id, props)}
        type={type}
        className={`input${compact ? ' input-compact' : ''}`}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
      />
    </FieldShell>
  )
}

export function DateField(props: BaseProps & { min?: string; max?: string }) {
  const id = useId()
  const { value, onChange, min, max, compact } = props
  return (
    <FieldShell id={id} {...props}>
      <input
        {...controlProps(id, props)}
        type="date"
        className={`input${compact ? ' input-compact' : ''}`}
        value={value}
        min={min}
        max={max}
        onChange={(e) => onChange(e.target.value)}
      />
    </FieldShell>
  )
}

// Right-aligned number with an optional unit suffix inside the box.
export function NumberField(props: BaseProps & { unit?: string; placeholder?: string }) {
  const id = useId()
  const { value, onChange, unit, placeholder, compact, error } = props
  return (
    <FieldShell id={id} {...props}>
      <div className={`input input-affix${compact ? ' input-compact' : ''}${error ? ' invalid' : ''}`}>
        <input
          {...controlProps(id, props)}
          inputMode="decimal"
          className="num"
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
        />
        {unit && <span className="unit">{unit}</span>}
      </div>
    </FieldShell>
  )
}

export type SelectOption = { value: string; label: string }

export function Select(props: BaseProps & { options: SelectOption[] }) {
  const id = useId()
  const { value, onChange, options, compact } = props
  return (
    <FieldShell id={id} {...props}>
      <div className="select-wrap">
        <select
          {...controlProps(id, props)}
          className={`input select${compact ? ' input-compact' : ''}`}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        >
          {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <Icon name="chevron-down" />
      </div>
    </FieldShell>
  )
}

export function SearchField({ label, value, onChange, placeholder, hideLabel, className }: Omit<BaseProps, 'help' | 'error' | 'compact'> & { placeholder?: string }) {
  const id = useId()
  return (
    <FieldShell id={id} label={label} hideLabel={hideLabel} className={className}>
      <div className="input input-affix search">
        <Icon name="search" size={20} />
        <input id={id} type="search" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
        {value && <IconButton icon="x" label="Clear search" size="sm" onClick={() => onChange('')} />}
      </div>
    </FieldShell>
  )
}
