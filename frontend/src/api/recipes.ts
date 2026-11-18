// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

// Client for the recipe builder: units, vendors, ingredients, the menu mapping list and recipes.
// Money and quantities arrive as decimal strings (the backend never uses floats); the page turns
// them into numbers only to display them.

export type UnitKind = 'mass' | 'volume' | 'count'

export interface UnitGroup {
  kind: UnitKind
  base_unit: string
  units: string[]
  factors: Record<string, string> // base units in one of each unit, e.g. kg: "1000"
}

export interface Vendor {
  id: string
  name: string
  contact_email: string | null
}

export interface Ingredient {
  id: string
  name: string
  kind: UnitKind
  base_unit: string
  vendor_id: string | null
  vendor_name: string | null
  pack_size: string | null // in base_unit
  pack_price: string | null
  unit_cost: string | null // price of one base unit
  is_active: boolean
}

export interface NewIngredient {
  name: string
  base_unit: string // any unit of the ingredient's kind
  vendor_id?: string | null
  pack_size?: string | null
  pack_unit?: string | null
  pack_price?: string | null
}

export type MenuItemStatus = 'unmapped' | 'needs_review' | 'mapped'
export type ReviewReason = 'inactive_ingredient' | 'menu_item_changed' | 'unmapped_modifier'

export interface Coverage {
  items_total: number
  items_mapped: number
  item_share: string | null // 0 to 1
  revenue_total: string
  revenue_mapped: string
  revenue_share: string | null // 0 to 1
}

export interface MenuItemSummary {
  id: string
  name: string
  price: string | null
  is_active: boolean
  status: MenuItemStatus
  review_reasons: ReviewReason[]
  unmapped_modifiers: string[]
  revenue_90d: string
  recipe_effective_from: string | null
}

export interface MenuOverview {
  coverage: Coverage
  items: MenuItemSummary[]
}

export interface RecipeLine {
  ingredient_id: string
  ingredient_name: string
  quantity: string // in base_unit
  base_unit: string
  entered_quantity: string
  entered_unit: string
  cost: string | null
  unit_cost: string | null
  vendor_name: string | null
  ingredient_active: boolean
}

export interface ModifierLine extends RecipeLine {
  menu_modifier_id: string
  modifier_name: string
  effect: 'add' | 'remove'
}

export interface RecipeVersion {
  id: string
  effective_from: string
  status: 'past' | 'current' | 'scheduled' | null
  menu_item_name: string
  menu_item_price: string | null
  created_by_email: string | null
  created_at: string
}

export interface Recipe {
  menu_item_id: string
  menu_item_name: string
  version: RecipeVersion
  lines: RecipeLine[]
  modifier_lines: ModifierLine[]
  total_cost: string | null
}

export interface MenuModifier {
  id: string
  name: string
  group_name: string
  price: string | null
  sold_with_item: number // in the last 90 days
}

export interface RecipeSave {
  effective_from?: string | null
  lines: { ingredient_id: string; quantity: string; unit: string }[]
  modifier_lines: {
    menu_modifier_id: string
    ingredient_id: string
    effect: 'add' | 'remove'
    quantity: string
    unit: string
  }[]
}

export class RecipeApiError extends Error {
  status: number
  requestId: string | null

  constructor(message: string, status = 0, requestId: string | null = null) {
    super(message)
    this.name = 'RecipeApiError'
    this.status = status
    this.requestId = requestId
  }
}

const API_BASE_URL: string = import.meta.env.VITE_API_URL ?? ''

// The backend words its 409 and 422 messages for the kitchen manager ("Pita is listed twice;
// combine it into one line."), so those are shown as they are. Field validation errors come
// as a list from FastAPI; the first one is shown.
async function errorMessage(response: Response): Promise<string> {
  if (response.status === 401) return 'Your session has expired. Log in again.'
  if (response.status === 403) return 'Only owners and kitchen managers can change recipes.'
  if (response.status === 404) return 'This item no longer exists. Refresh the page.'
  if (response.status === 409 || response.status === 422) {
    try {
      const body = await response.json() as { detail?: unknown }
      if (typeof body.detail === 'string') return body.detail
      if (Array.isArray(body.detail) && body.detail.length > 0) {
        const first = body.detail[0] as { msg?: unknown }
        if (typeof first.msg === 'string') return first.msg
      }
    } catch {
      // Fall through to the generic message.
    }
  }
  return 'Something went wrong. Try again.'
}

// A GET that answers 404 returns null instead of failing (an item with no recipe yet).
async function request<T>(method: string, path: string, body?: unknown): Promise<T | null> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      credentials: 'include',
      ...(body === undefined ? {} : {
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    })
  } catch {
    throw new RecipeApiError('Could not reach the server. Check your connection and try again.')
  }
  if (method === 'GET' && response.status === 404) return null
  if (!response.ok) {
    throw new RecipeApiError(
      await errorMessage(response), response.status, response.headers.get('X-Request-ID'),
    )
  }
  return await response.json() as T
}

async function required<T>(method: string, path: string, body?: unknown): Promise<T> {
  const result = await request<T>(method, path, body)
  if (result === null) throw new RecipeApiError('This item no longer exists. Refresh the page.', 404)
  return result
}

export function getUnits(): Promise<UnitGroup[]> {
  return required('GET', '/api/units')
}

export function listVendors(): Promise<Vendor[]> {
  return required('GET', '/api/vendors')
}

export function createVendor(name: string): Promise<Vendor> {
  return required('POST', '/api/vendors', { name })
}

// Active ingredients whose name contains `query`, names starting with it first (50 at most).
export function searchIngredients(query: string): Promise<Ingredient[]> {
  return required('GET', `/api/ingredients?q=${encodeURIComponent(query)}`)
}

export function createIngredient(ingredient: NewIngredient): Promise<Ingredient> {
  return required('POST', '/api/ingredients', ingredient)
}

export function getMenuOverview(): Promise<MenuOverview> {
  return required('GET', '/api/menu-items')
}

// The recipe in effect now, or null when the item is not mapped yet.
export function getRecipe(menuItemId: string): Promise<Recipe | null> {
  return request('GET', `/api/menu-items/${encodeURIComponent(menuItemId)}/recipe`)
}

export function saveRecipe(menuItemId: string, recipe: RecipeSave): Promise<Recipe> {
  return required('PUT', `/api/menu-items/${encodeURIComponent(menuItemId)}/recipe`, recipe)
}

export function listRecipeVersions(menuItemId: string): Promise<RecipeVersion[]> {
  return required('GET', `/api/menu-items/${encodeURIComponent(menuItemId)}/recipe/versions`)
}

// Modifiers, those sold with this item most often in the last 90 days first.
export function listItemModifiers(menuItemId: string): Promise<MenuModifier[]> {
  return required('GET', `/api/menu-items/${encodeURIComponent(menuItemId)}/modifiers`)
}
