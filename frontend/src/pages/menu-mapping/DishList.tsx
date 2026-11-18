// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import type { MenuItemSummary } from '../../api/recipes'
import { Badge } from '../../components/Badge'
import { formatMoney } from '../../mocks/helpers'
import { REVIEW_REASONS } from './recipeDraft'

function describe(item: MenuItemSummary): string {
  const revenue = `${formatMoney(Number(item.revenue_90d))} in 90 days`
  if (!item.is_active) return `Removed from POS · ${revenue}`
  if (item.status === 'needs_review') return REVIEW_REASONS[item.review_reasons[0]] ?? revenue
  return revenue
}

export function StatusBadge({ item }: { item: MenuItemSummary }) {
  if (item.status === 'mapped') return <Badge tone="success">Mapped</Badge>
  if (item.status === 'needs_review') return <Badge tone="info">Needs review</Badge>
  return <Badge tone="warning">Unmapped</Badge>
}

export function DishList({ items, selectedId, onSelect }: {
  items: MenuItemSummary[]
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  if (items.length === 0) return <p className="list-empty">No menu items match your filters.</p>
  return (
    <ul className="dish-list">
      {items.map((item) => {
        const on = item.id === selectedId
        return (
          <li key={item.id}>
            <button
              type="button"
              className={`dish-row${on ? ' on' : ''}${item.is_active ? '' : ' muted'}`}
              aria-current={on ? 'true' : undefined}
              onClick={() => onSelect(item.id)}
            >
              <span className="dish-text">
                <span className="dish-name">{item.name}</span>
                <span className="caption">{describe(item)}</span>
              </span>
              <StatusBadge item={item} />
            </button>
          </li>
        )
      })}
    </ul>
  )
}
