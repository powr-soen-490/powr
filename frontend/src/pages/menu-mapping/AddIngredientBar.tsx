// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useEffect, useState, type ReactNode } from 'react'
import { searchIngredients, type Ingredient, type UnitGroup } from '../../api/recipes'
import { Button } from '../../components/Button'
import { NumberField, Select, TextField } from '../../components/fields'
import { parseQuantity, refFromIngredient, unitsFor, type DraftLine, type IngredientRef } from './recipeDraft'

// Asks the page to create a missing ingredient named `name`, then calls `pick` with it.
export type CreateIngredient = (name: string, pick: (ingredient: IngredientRef) => void) => void

// Active ingredients matching `text`, searched on the server as Marco types; `query` is the
// text the results are for, so a stale answer is never read as "no such ingredient".
function useIngredientSearch(text: string): { query: string | null; results: Ingredient[] } {
  const [search, setSearch] = useState<{ query: string | null; results: Ingredient[] }>({ query: null, results: [] })
  useEffect(() => {
    let cancelled = false
    const query = text.trim()
    const timer = setTimeout(() => {
      searchIngredients(query)
        .then((results) => { if (!cancelled) setSearch({ query, results }) })
        .catch(() => { if (!cancelled) setSearch({ query: null, results: [] }) })
    }, 200)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [text])
  return search
}

export function AddIngredientBar({ groups, disabled, excludeIds, onAdd, onCreate, children }: {
  groups: UnitGroup[]
  disabled: boolean
  excludeIds: string[]
  onAdd: (line: DraftLine) => void
  onCreate: CreateIngredient
  children?: ReactNode // extra controls shown first, e.g. "adds / removes"
}) {
  const [text, setText] = useState('')
  const [chosen, setChosen] = useState<IngredientRef | null>(null)
  const [qty, setQty] = useState('')
  const [unit, setUnit] = useState('')
  const { query, results } = useIngredientSearch(text)

  const typed = text.trim().toLowerCase()
  const exact = results.find((i) => i.name.toLowerCase() === typed)
  const picked = chosen && chosen.name.toLowerCase() === typed ? chosen : exact ? refFromIngredient(exact) : null
  const units = picked ? unitsFor(groups, picked) : []
  const chosenUnit = units.includes(unit) ? unit : (picked?.baseUnit ?? '')
  const already = picked !== null && excludeIds.includes(picked.id)
  // Shown as buttons rather than a <datalist>: browsers don't reopen a datalist when its
  // options arrive after the keystroke, so server results would stay hidden.
  const searched = typed !== '' && query === text.trim()
  const matches = results.filter((i) => !excludeIds.includes(i.id)).slice(0, 8)

  function pick(ingredient: IngredientRef) {
    setChosen(ingredient)
    setText(ingredient.name)
  }

  function add() {
    if (!picked) return
    onAdd({ ingredient: picked, quantity: qty.trim(), unit: chosenUnit })
    setText('')
    setChosen(null)
    setQty('')
    setUnit('')
  }

  return (
    <div className="add-bar-wrap">
      <div className="add-bar">
        {children}
        <TextField
          className="grow"
          label="Ingredient"
          placeholder="Search ingredients, e.g. pita"
          value={text}
          disabled={disabled}
          onChange={setText}
        />
        <NumberField className="w-120" label="Quantity" placeholder="0" value={qty} disabled={disabled} onChange={setQty} />
        <Select
          className="w-100"
          label="Unit"
          value={chosenUnit}
          disabled={disabled || !picked}
          options={picked ? units.map((u) => ({ value: u, label: u })) : [{ value: '', label: '—' }]}
          onChange={setUnit}
        />
        <Button icon="plus" disabled={disabled || !picked || already || parseQuantity(qty) === null} onClick={add}>
          Add
        </Button>
      </div>
      {already && <p className="caption add-bar-hint">{picked.name} is already listed. Change its quantity instead.</p>}
      {searched && !picked && !disabled && (
        <div className="caption add-bar-hint" role="group" aria-label="Matching ingredients">
          {matches.length > 0 ? 'Pick an ingredient:' : `No ingredient called “${text.trim()}”.`}
          {matches.map((i) => (
            <Button key={i.id} size="sm" onClick={() => pick(refFromIngredient(i))}>{i.name}</Button>
          ))}
          {matches.length > 0 && ' or'}
          <Button size="sm" icon="plus" onClick={() => onCreate(text.trim(), pick)}>
            Create “{text.trim()}”
          </Button>
        </div>
      )}
    </div>
  )
}
