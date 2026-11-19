// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useState } from 'react'
import type { MenuModifier, UnitGroup } from '../../api/recipes'
import { Button, IconButton } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { NumberField, Select } from '../../components/fields'
import { AddIngredientBar, type CreateIngredient } from './AddIngredientBar'
import { parseQuantity, unitsFor, type DraftModifierLine } from './recipeDraft'

type Effect = DraftModifierLine['effect']

const EFFECTS: { value: Effect; label: string }[] = [
  { value: 'add', label: 'Adds' },
  { value: 'remove', label: 'Removes' },
]

// Edits what one modifier does to the dish. Apply changes the page's draft; "Save mapping"
// commits it. A substitution ("rice instead of pita") is one line that removes and one that adds.
// `hidden` keeps the dialog's state while the new-ingredient dialog is open over it.
export function ModifierDialog({ modifier, lines: initialLines, groups, hidden, onApply, onClose, onCreate }: {
  modifier: MenuModifier
  lines: DraftModifierLine[]
  groups: UnitGroup[]
  hidden: boolean
  onApply: (lines: DraftModifierLine[]) => void
  onClose: () => void
  onCreate: CreateIngredient
}) {
  const [lines, setLines] = useState(initialLines)
  const [effect, setEffect] = useState<Effect>('add')
  const invalid = lines.some((line) => parseQuantity(line.quantity) === null)

  function update(index: number, patch: Partial<DraftModifierLine>) {
    setLines(lines.map((line, i) => (i === index ? { ...line, ...patch } : line)))
  }

  return (
    <Dialog
      open={!hidden}
      width={640}
      title={`${initialLines.length === 0 ? 'Map' : 'Edit'} “${modifier.name}”`}
      onClose={onClose}
      actions={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={invalid} onClick={() => onApply(lines)}>Apply</Button>
      </>}
    >
      <p className="caption">When this modifier is ordered, these ingredients are added to or removed from one order.</p>
      {lines.length === 0 ? (
        <p className="list-empty">No ingredient changes yet.</p>
      ) : (
        <table>
          <tbody>
            {lines.map((line, index) => {
              const name = line.ingredient.name
              return (
                <tr key={`${line.effect}-${line.ingredient.id}`}>
                  <td className="w-120">
                    <Select label={`Effect on ${name}`} hideLabel compact value={line.effect} options={EFFECTS}
                      onChange={(value) => update(index, { effect: value as Effect })} />
                  </td>
                  <td className="strong">{name}</td>
                  <td className="w-100">
                    <NumberField label={`Quantity of ${name}`} hideLabel compact value={line.quantity}
                      error={parseQuantity(line.quantity) === null ? 'Above 0' : undefined}
                      onChange={(quantity) => update(index, { quantity })} />
                  </td>
                  <td className="w-100">
                    <Select label={`Unit for ${name}`} hideLabel compact value={line.unit}
                      options={unitsFor(groups, line.ingredient).map((u) => ({ value: u, label: u }))}
                      onChange={(unit) => update(index, { unit })} />
                  </td>
                  <td className="w-44">
                    <IconButton icon="bin" label={`Remove ${name}`} size="sm"
                      onClick={() => setLines(lines.filter((_, i) => i !== index))} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      <AddIngredientBar
        groups={groups}
        disabled={false}
        excludeIds={lines.map((line) => line.ingredient.id)}
        onCreate={onCreate}
        onAdd={(line) => setLines([...lines, { ...line, modifierId: modifier.id, effect }])}
      >
        <Select className="w-120" label="Change" value={effect} options={EFFECTS} onChange={(v) => setEffect(v as Effect)} />
      </AddIngredientBar>
    </Dialog>
  )
}
