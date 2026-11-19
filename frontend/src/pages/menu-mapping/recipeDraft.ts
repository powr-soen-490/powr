// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

// The recipe being edited on the Menu Mapping page, and the rules the page applies before the
// backend checks it again on save (units of the right kind, quantities above zero, no
// duplicate lines).

import type {
  Ingredient, MenuItemStatus, MenuItemSummary, MenuModifier, Recipe, RecipeLine, RecipeSave, ReviewReason, UnitGroup,
} from '../../api/recipes'

export interface IngredientRef {
  id: string
  name: string
  baseUnit: string // g, ml or each
  unitCost: number | null // price of one base unit
  vendorName: string | null
  active: boolean
}

export interface DraftLine {
  ingredient: IngredientRef
  quantity: string // as typed
  unit: string
}

export interface DraftModifierLine extends DraftLine {
  modifierId: string
  effect: 'add' | 'remove'
}

export interface Draft {
  lines: DraftLine[]
  modifierLines: DraftModifierLine[]
}

export const EMPTY_DRAFT: Draft = { lines: [], modifierLines: [] }

const toNumber = (value: string | null): number | null => (value === null ? null : Number(value))

export function refFromIngredient(ingredient: Ingredient): IngredientRef {
  return {
    id: ingredient.id,
    name: ingredient.name,
    baseUnit: ingredient.base_unit,
    unitCost: toNumber(ingredient.unit_cost),
    vendorName: ingredient.vendor_name,
    active: ingredient.is_active,
  }
}

function refFromLine(line: RecipeLine): IngredientRef {
  return {
    id: line.ingredient_id,
    name: line.ingredient_name,
    baseUnit: line.base_unit,
    unitCost: toNumber(line.unit_cost),
    vendorName: line.vendor_name,
    active: line.ingredient_active,
  }
}

// Shows each line as Marco typed it ("1 kg"), not in base units ("1000 g").
function quantityText(value: string): string {
  return String(Number(value))
}

export function draftFromRecipe(recipe: Recipe | null): Draft {
  if (recipe === null) return EMPTY_DRAFT
  return {
    lines: recipe.lines.map((line) => ({
      ingredient: refFromLine(line),
      quantity: quantityText(line.entered_quantity),
      unit: line.entered_unit,
    })),
    modifierLines: recipe.modifier_lines.map((line) => ({
      ingredient: refFromLine(line),
      quantity: quantityText(line.entered_quantity),
      unit: line.entered_unit,
      modifierId: line.menu_modifier_id,
      effect: line.effect,
    })),
  }
}

function groupFor(groups: UnitGroup[], baseUnit: string): UnitGroup | undefined {
  return groups.find((group) => group.base_unit === baseUnit)
}

// The units an ingredient can be measured in: any unit of its kind.
export function unitsFor(groups: UnitGroup[], ingredient: IngredientRef): string[] {
  return groupFor(groups, ingredient.baseUnit)?.units ?? [ingredient.baseUnit]
}

export function parseQuantity(text: string): number | null {
  const trimmed = text.trim()
  if (trimmed === '') return null
  const value = Number(trimmed)
  return Number.isFinite(value) && value > 0 ? value : null
}

// At today's prices; null when the ingredient has no price or the quantity is not valid yet.
export function lineCost(groups: UnitGroup[], line: DraftLine): number | null {
  const quantity = parseQuantity(line.quantity)
  const factor = groupFor(groups, line.ingredient.baseUnit)?.factors[line.unit]
  if (quantity === null || factor === undefined || line.ingredient.unitCost === null) return null
  return quantity * Number(factor) * line.ingredient.unitCost
}

export function draftCost(groups: UnitGroup[], lines: DraftLine[]): { total: number; missingPrice: boolean } {
  let total = 0
  let missingPrice = false
  for (const line of lines) {
    const cost = lineCost(groups, line)
    if (cost === null) missingPrice = true
    else total += cost
  }
  return { total, missingPrice }
}

// The first thing that stops the draft from being saved, in the kitchen manager's words.
export function draftProblem(draft: Draft, modifierNames: Map<string, string>): string | null {
  if (draft.lines.length === 0) return 'Add at least one ingredient.'
  const seen = new Set<string>()
  for (const line of draft.lines) {
    if (parseQuantity(line.quantity) === null) return `Enter a quantity above zero for ${line.ingredient.name}.`
    if (seen.has(line.ingredient.id)) return `${line.ingredient.name} is listed twice; combine it into one line.`
    seen.add(line.ingredient.id)
  }
  const seenModifier = new Set<string>()
  for (const line of draft.modifierLines) {
    const modifier = modifierNames.get(line.modifierId) ?? 'a modifier'
    if (parseQuantity(line.quantity) === null) {
      return `Enter a quantity above zero for ${line.ingredient.name} in “${modifier}”.`
    }
    const key = `${line.modifierId}/${line.ingredient.id}`
    if (seenModifier.has(key)) return `${line.ingredient.name} is listed twice for “${modifier}”.`
    seenModifier.add(key)
  }
  return null
}

// `effectiveFrom` is null for "now", or an ISO timestamp in the future.
export function toSave(draft: Draft, effectiveFrom: string | null): RecipeSave {
  return {
    effective_from: effectiveFrom,
    lines: draft.lines.map((line) => ({
      ingredient_id: line.ingredient.id, quantity: line.quantity.trim(), unit: line.unit,
    })),
    modifier_lines: draft.modifierLines.map((line) => ({
      menu_modifier_id: line.modifierId,
      ingredient_id: line.ingredient.id,
      effect: line.effect,
      quantity: line.quantity.trim(),
      unit: line.unit,
    })),
  }
}

// Same lines, quantities and units: saving would change nothing.
export function sameDraft(a: Draft, b: Draft): boolean {
  const key = (draft: Draft) => JSON.stringify(toSave(draft, null))
  return key(a) === key(b)
}

// A date picked in the date field ("2026-12-01") starts at local midnight. Today or earlier
// means now: the backend refuses a start in the past.
export function effectiveFromDate(date: string, now: Date): string | null {
  if (date === '') return null
  const start = new Date(`${date}T00:00:00`)
  return Number.isNaN(start.getTime()) || start <= now ? null : start.toISOString()
}

// The modifiers worth showing: those sold with the item or already mapped, unless all are asked
// for. The backend lists the most sold first.
export function visibleModifiers(modifiers: MenuModifier[], draft: Draft, showAll: boolean): MenuModifier[] {
  if (showAll) return modifiers
  const mapped = new Set(draft.modifierLines.map((line) => line.modifierId))
  return modifiers.filter((m) => m.sold_with_item > 0 || mapped.has(m.id))
}

export const REVIEW_REASONS: Record<ReviewReason, string> = {
  inactive_ingredient: 'uses an archived ingredient',
  menu_item_changed: 'changed in the POS since it was mapped',
  unmapped_modifier: 'a modifier that sold is not mapped',
}

export type ItemFilter = 'all' | MenuItemStatus

export function filterItems(items: MenuItemSummary[], query: string, filter: ItemFilter): MenuItemSummary[] {
  const q = query.trim().toLowerCase()
  return items.filter((item) => (filter === 'all' || item.status === filter) && item.name.toLowerCase().includes(q))
}

export function countItems(items: MenuItemSummary[]): Record<ItemFilter, number> {
  const count = (status: MenuItemStatus) => items.filter((item) => item.status === status).length
  return { all: items.length, unmapped: count('unmapped'), needs_review: count('needs_review'), mapped: count('mapped') }
}
