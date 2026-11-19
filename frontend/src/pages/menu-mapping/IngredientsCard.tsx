// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import type { MenuItemSummary, UnitGroup } from '../../api/recipes'
import { Badge } from '../../components/Badge'
import { IconButton } from '../../components/Button'
import { NumberField, Select } from '../../components/fields'
import { formatMoney, plural } from '../../mocks/helpers'
import { AddIngredientBar, type CreateIngredient } from './AddIngredientBar'
import { StatusBadge } from './DishList'
import { draftCost, lineCost, parseQuantity, unitsFor, type Draft, type DraftLine } from './recipeDraft'

type Props = {
  item: MenuItemSummary
  draft: Draft
  groups: UnitGroup[]
  readOnly: boolean
  onChange: (draft: Draft) => void
  onCreate: CreateIngredient
}

export function IngredientsCard({ item, draft, groups, readOnly, onChange, onCreate }: Props) {
  const cost = draftCost(groups, draft.lines)

  function update(index: number, patch: Partial<DraftLine>) {
    onChange({ ...draft, lines: draft.lines.map((line, i) => (i === index ? { ...line, ...patch } : line)) })
  }

  return (
    <section className="card">
      <div className="card-head">
        <div>
          <div className="caption">
            From POS{item.price !== null && ` · ${formatMoney(Number(item.price))}`}
            {` · ${formatMoney(Number(item.revenue_90d))} sold in the last 90 days`}
          </div>
          <h2>{item.name}</h2>
        </div>
        {item.status === 'mapped'
          ? <Badge tone="success">Mapped · {plural(draft.lines.length, 'ingredient')}</Badge>
          : <StatusBadge item={item} />}
      </div>

      <h3 className="section-title">Ingredients per one order</h3>
      {draft.lines.length === 0 ? (
        <p className="list-empty">No ingredients yet. Add the first one below so the forecast can count this dish.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Ingredient</th>
                <th className="w-120">Quantity</th>
                <th className="w-100">Unit</th>
                <th>Vendor</th>
                <th className="num w-100">Est. cost</th>
                <th className="w-44"><span className="visually-hidden">Remove</span></th>
              </tr>
            </thead>
            <tbody>
              {draft.lines.map((line, index) => {
                const name = line.ingredient.name
                const amount = lineCost(groups, line)
                const invalid = parseQuantity(line.quantity) === null
                return (
                  <tr key={line.ingredient.id}>
                    <td className="strong nowrap">
                      {name}
                      {!line.ingredient.active && <> <Badge tone="warning">Archived</Badge></>}
                    </td>
                    <td>
                      <NumberField label={`Quantity of ${name}`} hideLabel compact value={line.quantity} disabled={readOnly}
                        error={invalid ? 'Above 0' : undefined} onChange={(quantity) => update(index, { quantity })} />
                    </td>
                    <td>
                      <Select label={`Unit for ${name}`} hideLabel compact value={line.unit} disabled={readOnly}
                        options={unitsFor(groups, line.ingredient).map((u) => ({ value: u, label: u }))}
                        onChange={(unit) => update(index, { unit })} />
                    </td>
                    <td className={`nowrap ${line.ingredient.vendorName ? 'secondary' : 'missing'}`}>
                      {line.ingredient.vendorName ?? 'No vendor'}
                    </td>
                    <td className="num">{amount === null ? '—' : formatMoney(amount)}</td>
                    <td>
                      <IconButton icon="bin" label={`Remove ${name}`} size="sm" disabled={readOnly}
                        onClick={() => onChange({ ...draft, lines: draft.lines.filter((_, i) => i !== index) })} />
                    </td>
                  </tr>
                )
              })}
              <tr className="total-row">
                <td colSpan={4}>
                  Estimated cost per order
                  {cost.missingPrice && <span className="caption"> · excludes ingredients without a price</span>}
                </td>
                <td className="num">{formatMoney(cost.total)}</td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
      )}

      <AddIngredientBar
        groups={groups}
        disabled={readOnly}
        excludeIds={draft.lines.map((line) => line.ingredient.id)}
        onCreate={onCreate}
        onAdd={(line) => onChange({ ...draft, lines: [...draft.lines, line] })}
      />
    </section>
  )
}
