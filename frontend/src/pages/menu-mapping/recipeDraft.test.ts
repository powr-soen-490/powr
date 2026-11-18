// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { describe, expect, it } from 'vitest'
import type { MenuItemSummary, MenuModifier, Recipe, UnitGroup } from '../../api/recipes'
import {
  countItems, draftCost, draftFromRecipe, draftProblem, effectiveFromDate, filterItems, sameDraft, toSave,
  visibleModifiers, type Draft, type IngredientRef,
} from './recipeDraft'

const GROUPS: UnitGroup[] = [
  { kind: 'mass', base_unit: 'g', units: ['g', 'kg'], factors: { g: '1', kg: '1000' } },
  { kind: 'count', base_unit: 'each', units: ['each', 'dozen'], factors: { each: '1', dozen: '12' } },
]

// $86.25 for 5 kg, and $10.32 for 24 pitas
const chicken: IngredientRef = { id: 'chicken', name: 'Chicken breast', baseUnit: 'g', unitCost: 0.01725, vendorName: 'Costco', active: true }
const pita: IngredientRef = { id: 'pita', name: 'Pita', baseUnit: 'each', unitCost: 0.43, vendorName: 'Sysco', active: true }
const feta: IngredientRef = { id: 'feta', name: 'Feta', baseUnit: 'g', unitCost: null, vendorName: null, active: true }

const souvlaki: Draft = {
  lines: [
    { ingredient: chicken, quantity: '0.2', unit: 'kg' },
    { ingredient: pita, quantity: '1', unit: 'each' },
  ],
  modifierLines: [{ ingredient: feta, quantity: '30', unit: 'g', modifierId: 'extra-feta', effect: 'add' }],
}
const names = new Map([['extra-feta', 'Extra feta']])

describe('the recipe draft', () => {
  it('costs each line in base units and flags unpriced ingredients', () => {
    const base = draftCost(GROUPS, souvlaki.lines)
    expect(base.total).toBeCloseTo(3.88)
    expect(base.missingPrice).toBe(false)
    expect(draftCost(GROUPS, [...souvlaki.lines, souvlaki.modifierLines[0]]).missingPrice).toBe(true)
  })

  it('names the first problem before saving', () => {
    expect(draftProblem(souvlaki, names)).toBeNull()
    expect(draftProblem({ lines: [], modifierLines: [] }, names)).toBe('Add at least one ingredient.')
    expect(draftProblem({ ...souvlaki, lines: [{ ...souvlaki.lines[0], quantity: '0' }] }, names))
      .toBe('Enter a quantity above zero for Chicken breast.')
    expect(draftProblem({ ...souvlaki, lines: [...souvlaki.lines, souvlaki.lines[1]] }, names))
      .toBe('Pita is listed twice; combine it into one line.')
    const extra = souvlaki.modifierLines[0]
    expect(draftProblem({ ...souvlaki, modifierLines: [{ ...extra, quantity: '' }] }, names))
      .toBe('Enter a quantity above zero for Feta in “Extra feta”.')
    expect(draftProblem({ ...souvlaki, modifierLines: [extra, extra] }, names))
      .toBe('Feta is listed twice for “Extra feta”.')
  })

  it('round-trips a saved recipe, showing quantities as they were typed', () => {
    const line = {
      ingredient_id: 'chicken', ingredient_name: 'Chicken breast', quantity: '200.0000', base_unit: 'g',
      entered_quantity: '0.2000', entered_unit: 'kg', cost: '3.45', unit_cost: '0.01725',
      vendor_name: 'Costco', ingredient_active: true,
    }
    const recipe = {
      lines: [line],
      modifier_lines: [{ ...line, menu_modifier_id: 'extra-feta', modifier_name: 'Extra feta', effect: 'add' }],
    } as Recipe
    const draft = draftFromRecipe(recipe)
    expect(draft.lines[0]).toEqual({ ingredient: chicken, quantity: '0.2', unit: 'kg' })
    expect(draft.modifierLines[0]).toMatchObject({ modifierId: 'extra-feta', effect: 'add', quantity: '0.2' })
    expect(draftFromRecipe(null)).toEqual({ lines: [], modifierLines: [] })
    expect(sameDraft(draft, draftFromRecipe(recipe))).toBe(true)
    expect(sameDraft(draft, { ...draft, lines: [{ ...draft.lines[0], quantity: '0.25' }] })).toBe(false)
  })

  it('sends quantities as typed, in the units chosen', () => {
    expect(toSave(souvlaki, null)).toEqual({
      effective_from: null,
      lines: [
        { ingredient_id: 'chicken', quantity: '0.2', unit: 'kg' },
        { ingredient_id: 'pita', quantity: '1', unit: 'each' },
      ],
      modifier_lines: [{ menu_modifier_id: 'extra-feta', ingredient_id: 'feta', effect: 'add', quantity: '30', unit: 'g' }],
    })
  })

  it('starts now unless a future date is picked', () => {
    const now = new Date(2026, 10, 17, 15, 0)
    expect(effectiveFromDate('', now)).toBeNull()
    expect(effectiveFromDate('2026-11-17', now)).toBeNull()
    expect(effectiveFromDate('2026-12-01', now)).toBe(new Date(2026, 11, 1).toISOString())
  })
})

describe('the menu list', () => {
  const item = (name: string, status: MenuItemSummary['status']) => ({ name, status }) as MenuItemSummary
  const items = [item('Dolmades', 'unmapped'), item('Gyro', 'needs_review'), item('Souvlaki plate', 'mapped')]

  it('filters by status and name, and counts each status', () => {
    expect(filterItems(items, 'gy', 'all').map((i) => i.name)).toEqual(['Gyro'])
    expect(filterItems(items, '', 'mapped').map((i) => i.name)).toEqual(['Souvlaki plate'])
    expect(countItems(items)).toEqual({ all: 3, unmapped: 1, needs_review: 1, mapped: 1 })
  })

  it('shows modifiers sold with the item or already mapped, unless all are asked for', () => {
    const modifier = (id: string, sold: number) => ({ id, sold_with_item: sold }) as MenuModifier
    const modifiers = [modifier('add-tzatziki', 4), modifier('extra-feta', 0), modifier('no-onion', 0)]
    expect(visibleModifiers(modifiers, souvlaki, false).map((m) => m.id)).toEqual(['add-tzatziki', 'extra-feta'])
    expect(visibleModifiers(modifiers, souvlaki, true)).toHaveLength(3)
  })
})
