// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { Ingredient, UnitGroup } from '../../api/recipes'
import { AddIngredientBar } from './AddIngredientBar'

const GROUPS: UnitGroup[] = [{ kind: 'mass', base_unit: 'g', units: ['g', 'kg'], factors: { g: '1', kg: '1000' } }]
const beef: Ingredient = {
  id: 'beef', name: 'Beef', kind: 'mass', base_unit: 'g', vendor_id: null, vendor_name: null,
  pack_size: null, pack_price: null, unit_cost: null, is_active: true,
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

it('shows the ingredients found on the server and adds the one picked', async () => {
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => Response.json([beef])))
  const onAdd = vi.fn()
  render(<AddIngredientBar groups={GROUPS} disabled={false} excludeIds={[]} onAdd={onAdd} onCreate={vi.fn()} />)

  fireEvent.change(screen.getByLabelText('Ingredient'), { target: { value: 'be' } })
  fireEvent.click(await screen.findByRole('button', { name: 'Beef' }))
  fireEvent.change(screen.getByLabelText('Quantity'), { target: { value: '150' } })
  fireEvent.click(screen.getByRole('button', { name: 'Add' }))

  expect(onAdd).toHaveBeenCalledWith({
    ingredient: expect.objectContaining({ id: 'beef', name: 'Beef' }), quantity: '150', unit: 'g',
  })
})

it('offers to create an ingredient that does not exist', async () => {
  vi.stubGlobal('fetch', vi.fn<typeof fetch>(async () => Response.json([])))
  const onCreate = vi.fn()
  render(<AddIngredientBar groups={GROUPS} disabled={false} excludeIds={[]} onAdd={vi.fn()} onCreate={onCreate} />)

  fireEvent.change(screen.getByLabelText('Ingredient'), { target: { value: 'Lamb' } })
  fireEvent.click(await screen.findByRole('button', { name: 'Create “Lamb”' }))

  expect(onCreate).toHaveBeenCalledWith('Lamb', expect.any(Function))
})
