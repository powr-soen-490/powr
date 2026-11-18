// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useCallback, useEffect, useState } from 'react'
import {
  getMenuOverview, getRecipe, getUnits, listItemModifiers, listRecipeVersions, RecipeApiError, saveRecipe,
  type MenuModifier, type MenuOverview, type Recipe, type RecipeVersion, type UnitGroup,
} from '../api/recipes'
import { PageHeader } from '../layout/PageHeader'
import { Button } from '../components/Button'
import { Dialog } from '../components/Dialog'
import { FilterChips } from '../components/FilterChips'
import { Icon } from '../components/Icon'
import { DateField, SearchField } from '../components/fields'
import { useToast } from '../components/Toast'
import { DishList } from './menu-mapping/DishList'
import { IngredientsCard } from './menu-mapping/IngredientsCard'
import { ModifierDialog } from './menu-mapping/ModifierDialog'
import { ModifiersCard } from './menu-mapping/ModifiersCard'
import { NewIngredientDialog } from './menu-mapping/NewIngredientDialog'
import {
  countItems, draftFromRecipe, draftProblem, effectiveFromDate, filterItems, REVIEW_REASONS, sameDraft, toSave,
  visibleModifiers,
  type Draft, type IngredientRef, type ItemFilter,
} from './menu-mapping/recipeDraft'

interface Detail {
  itemId: string
  recipe: Recipe | null
  versions: RecipeVersion[]
  modifiers: MenuModifier[]
}

const message = (e: unknown) => (e instanceof RecipeApiError ? e.message : 'Something went wrong. Try again.')
const percent = (share: string | null) => (share === null ? '—' : `${Math.round(Number(share) * 100)}%`)
const formatDate = (iso: string) => new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })

function loadDetail(itemId: string): Promise<Detail> {
  return Promise.all([getRecipe(itemId), listRecipeVersions(itemId), listItemModifiers(itemId)])
    .then(([recipe, versions, modifiers]) => ({ itemId, recipe, versions, modifiers }))
}

function todayIso(): string {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
}

export function MenuMapping() {
  const { showToast } = useToast()
  const [overview, setOverview] = useState<MenuOverview | null>(null)
  const [groups, setGroups] = useState<UnitGroup[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<ItemFilter>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Detail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [startDate, setStartDate] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [editing, setEditing] = useState<MenuModifier | null>(null)
  const [creating, setCreating] = useState<{ name: string; pick: (i: IngredientRef) => void } | null>(null)
  const [showAllModifiers, setShowAllModifiers] = useState(false)

  const refreshOverview = useCallback(() => getMenuOverview().then((next) => {
    setOverview(next)
    setSelectedId((current) => current ?? next.items[0]?.id ?? null)
  }), [])

  useEffect(() => {
    Promise.all([refreshOverview(), getUnits().then(setGroups)])
      .catch((e: unknown) => setLoadError(message(e)))
  }, [refreshOverview])

  useEffect(() => {
    if (selectedId === null) return
    let cancelled = false
    loadDetail(selectedId)
      .then((next) => { if (!cancelled) setDetail(next) })
      .catch((e: unknown) => { if (!cancelled) setDetailError(message(e)) })
    return () => { cancelled = true }
  }, [selectedId])

  if (loadError) {
    return (
      <>
        <PageHeader title="Menu Mapping" subtitle="Tell the forecast how much of each ingredient one order uses." />
        <p className="field-error" role="alert">{loadError}</p>
      </>
    )
  }
  if (overview === null) return <p role="status">Loading the menu…</p>

  const item = overview.items.find((i) => i.id === selectedId) ?? null
  const loaded = detail !== null && detail.itemId === selectedId ? detail : null
  const saved = draftFromRecipe(loaded?.recipe ?? null)
  const current = draft ?? saved
  const dirty = draft !== null && !sameDraft(draft, saved)
  const readOnly = item !== null && !item.is_active
  const modifierNames = new Map((loaded?.modifiers ?? []).map((m) => [m.id, m.name]))
  const problem = dirty ? draftProblem(current, modifierNames) : null
  const scheduled = loaded?.versions.find((v) => v.status === 'scheduled') ?? null
  const counts = countItems(overview.items)
  const coverage = overview.coverage

  function select(id: string) {
    if (id === selectedId) return
    if (dirty) {
      setPendingId(id)
      return
    }
    switchTo(id)
  }

  function switchTo(id: string) {
    setDraft(null)
    setSaveError(null)
    setDetailError(null)
    setStartDate('')
    setShowAllModifiers(false)
    setPendingId(null)
    setSelectedId(id)
  }

  async function save() {
    if (!item || !draft) return
    setSaving(true)
    setSaveError(null)
    try {
      const effectiveFrom = effectiveFromDate(startDate, new Date())
      await saveRecipe(item.id, toSave(draft, effectiveFrom))
      const [next] = await Promise.all([loadDetail(item.id), refreshOverview()])
      setDetail(next)
      setDraft(null)
      setStartDate('')
      showToast(effectiveFrom
        ? `${item.name} mapping saved; it applies from ${formatDate(effectiveFrom)}`
        : `${item.name} mapping saved`)
    } catch (e) {
      setSaveError(message(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <PageHeader title="Menu Mapping" subtitle="Tell the forecast how much of each ingredient one order uses." />

      <div className="note">
        <Icon name="info" />
        {coverage.items_mapped} of {coverage.items_total} menu items mapped ({percent(coverage.item_share)}),
        covering {percent(coverage.revenue_share)} of the last 90 days' sales. Unmapped items with the most sales come first.
      </div>

      <div className="split">
        <section className="card flush dish-panel" aria-label="Menu items">
          <div className="panel-filters">
            <SearchField label="Search menu items" placeholder="e.g. souvlaki" value={query} onChange={setQuery} />
            <FilterChips
              label="Filter by status"
              value={filter}
              onChange={setFilter}
              options={[
                { value: 'all', label: 'All', count: counts.all },
                { value: 'unmapped', label: 'Unmapped', count: counts.unmapped },
                { value: 'needs_review', label: 'Needs review', count: counts.needs_review },
                { value: 'mapped', label: 'Mapped', count: counts.mapped },
              ]}
            />
          </div>
          <DishList items={filterItems(overview.items, query, filter)} selectedId={selectedId} onSelect={select} />
        </section>

        <div className="editor" aria-label="Selected menu item">
          {item === null ? (
            <p className="list-empty">No menu items yet. Import sales from Toast to bring in the menu.</p>
          ) : detailError ? (
            <p className="field-error" role="alert">{detailError}</p>
          ) : loaded === null ? (
            <p role="status">Loading {item.name}…</p>
          ) : (
            <>
              {readOnly && (
                <div className="note"><Icon name="info" />Removed from the POS. Mapping is kept for past sales.</div>
              )}
              {item.status === 'needs_review' && (
                <div className="note">
                  <Icon name="warning" />
                  Needs review: {item.review_reasons.map((r) => REVIEW_REASONS[r]).join('; ')}
                  {item.unmapped_modifiers.length > 0 && ` (${item.unmapped_modifiers.join(', ')})`}.
                </div>
              )}
              <IngredientsCard
                item={item}
                draft={current}
                groups={groups}
                readOnly={readOnly}
                onChange={setDraft}
                onCreate={(name, pick) => setCreating({ name, pick })}
              />
              <ModifiersCard
                modifiers={visibleModifiers(loaded.modifiers, current, showAllModifiers)}
                totalCount={loaded.modifiers.length}
                showAll={showAllModifiers}
                draft={current}
                readOnly={readOnly}
                onToggleAll={() => setShowAllModifiers(!showAllModifiers)}
                onEdit={setEditing}
              />
              <div className="editor-footer">
                <div>
                  <span className="caption">
                    {loaded.recipe
                      ? `Current mapping since ${formatDate(loaded.recipe.version.effective_from)}. `
                      : ''}
                    {scheduled
                      ? `A change is scheduled for ${formatDate(scheduled.effective_from)}; saving replaces it. `
                      : ''}
                    Past sales keep the mapping they were sold with.
                  </span>
                  {(problem || saveError) && <p className="field-error" role="alert">{problem ?? saveError}</p>}
                </div>
                <div className="actions">
                  <DateField
                    compact
                    label="Applies from"
                    help="Empty means now"
                    value={startDate}
                    min={todayIso()}
                    disabled={readOnly}
                    onChange={setStartDate}
                  />
                  <Button disabled={!dirty || saving} onClick={() => { setDraft(null); setSaveError(null) }}>Discard</Button>
                  <Button variant="primary" disabled={!dirty || saving || problem !== null} onClick={() => void save()}>
                    {saving ? 'Saving…' : 'Save mapping'}
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {editing && (
        <ModifierDialog
          modifier={editing}
          lines={current.modifierLines.filter((line) => line.modifierId === editing.id)}
          groups={groups}
          hidden={creating !== null}
          onClose={() => setEditing(null)}
          onCreate={(name, pick) => setCreating({ name, pick })}
          onApply={(lines) => {
            setDraft({ ...current, modifierLines: [...current.modifierLines.filter((l) => l.modifierId !== editing.id), ...lines] })
            setEditing(null)
          }}
        />
      )}

      {creating && (
        <NewIngredientDialog
          name={creating.name}
          groups={groups}
          onClose={() => setCreating(null)}
          onCreated={(ingredient) => {
            creating.pick(ingredient)
            setCreating(null)
            showToast(`${ingredient.name} created`)
          }}
        />
      )}

      <Dialog
        open={pendingId !== null}
        title="Leave without saving?"
        onClose={() => setPendingId(null)}
        actions={<>
          <Button onClick={() => setPendingId(null)}>Keep editing</Button>
          <Button variant="danger" onClick={() => pendingId && switchTo(pendingId)}>Discard changes</Button>
        </>}
      >
        You have unsaved changes to {item?.name}. If you leave, they'll be lost.
      </Dialog>
    </>
  )
}
