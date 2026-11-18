// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import type { MenuModifier } from '../../api/recipes'
import { Button } from '../../components/Button'
import { Icon } from '../../components/Icon'
import { formatQty, plural } from '../../mocks/helpers'
import type { Draft, DraftModifierLine } from './recipeDraft'

function describeLine(line: DraftModifierLine): string {
  const verb = line.effect === 'add' ? 'Adds' : 'Removes'
  return `${verb} ${formatQty(Number(line.quantity) || 0, line.unit)} ${line.ingredient.name}`
}

export function ModifiersCard({ modifiers, totalCount, showAll, draft, readOnly, onToggleAll, onEdit }: {
  modifiers: MenuModifier[]
  totalCount: number
  showAll: boolean
  draft: Draft
  readOnly: boolean
  onToggleAll: () => void
  onEdit: (modifier: MenuModifier) => void
}) {
  return (
    <section className="card">
      <h3>Modifiers &amp; substitutions</h3>
      <p className="caption card-intro">
        From the POS. A modifier adds or removes ingredients when ordered; a substitution removes one and adds another.
      </p>
      {modifiers.length === 0 ? (
        <p className="list-empty">
          {totalCount === 0 ? 'No modifiers in the POS.' : 'No modifiers sold with this item in the last 90 days.'}
        </p>
      ) : (
        <ul className="modifier-list">
          {modifiers.map((m) => {
            const lines = draft.modifierLines.filter((line) => line.modifierId === m.id)
            const unmapped = lines.length === 0 && m.sold_with_item > 0
            const sold = m.sold_with_item > 0
              ? `Sold with it ${plural(m.sold_with_item, 'time')} in 90 days`
              : 'Not sold with it in 90 days'
            return (
              <li key={m.id} className={`modifier-row${unmapped ? ' unmapped' : ''}`}>
                <div className="modifier-name">
                  <div className="kicker">{unmapped && <Icon name="warning" size={14} />}{m.group_name}{unmapped && ' · unmapped'}</div>
                  <div className="strong">{m.name}</div>
                  <div className="caption">{sold}</div>
                </div>
                <div className="modifier-effect">
                  {lines.length > 0
                    ? lines.map(describeLine).join(' · ')
                    : unmapped
                      ? "Orders with this modifier don't change the ingredients counted yet."
                      : 'No ingredient changes.'}
                </div>
                {lines.length === 0
                  ? <Button size="sm" variant={unmapped ? 'primary' : 'secondary'} disabled={readOnly} onClick={() => onEdit(m)}>Map ingredients</Button>
                  : <Button size="sm" icon="pencil" disabled={readOnly} onClick={() => onEdit(m)}>Edit</Button>}
              </li>
            )
          })}
        </ul>
      )}
      {totalCount > modifiers.length || showAll ? (
        <Button size="sm" className="card-more" onClick={onToggleAll}>
          {showAll ? 'Show only modifiers sold with this item' : `Show all ${totalCount} modifiers`}
        </Button>
      ) : null}
    </section>
  )
}
