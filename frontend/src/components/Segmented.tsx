// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

export function Segmented({ options, value, onChange, label }: {
  options: string[]
  value: string
  onChange?: (option: string) => void
  label?: string
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          type="button"
          key={option}
          className={option === value ? 'on' : ''}
          aria-pressed={option === value}
          onClick={() => onChange?.(option)}
        >
          {option}
        </button>
      ))}
    </div>
  )
}
