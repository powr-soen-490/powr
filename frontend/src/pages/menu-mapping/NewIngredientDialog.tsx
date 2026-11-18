// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { useEffect, useState } from 'react'
import {
  createIngredient, createVendor, listVendors, RecipeApiError, type UnitGroup, type Vendor,
} from '../../api/recipes'
import { Button } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { NumberField, Select, TextField } from '../../components/fields'
import { refFromIngredient, type IngredientRef } from './recipeDraft'

const NEW_VENDOR = '__new__'

// Creates a missing ingredient without leaving the recipe. Only the name and unit are needed;
// the vendor and pack (what one pack holds and costs) give the recipe its cost.
export function NewIngredientDialog({ name: initialName, groups, onCreated, onClose }: {
  name: string
  groups: UnitGroup[]
  onCreated: (ingredient: IngredientRef) => void
  onClose: () => void
}) {
  const [name, setName] = useState(initialName)
  const [unit, setUnit] = useState('g')
  const [vendors, setVendors] = useState<Vendor[]>([])
  const [vendorId, setVendorId] = useState('')
  const [vendorName, setVendorName] = useState('')
  const [packSize, setPackSize] = useState('')
  const [packUnit, setPackUnit] = useState('')
  const [packPrice, setPackPrice] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    listVendors().then(setVendors).catch(() => setVendors([]))
  }, [])

  const kindUnits = groups.find((g) => g.units.includes(unit))?.units ?? [unit]
  const chosenPackUnit = kindUnits.includes(packUnit) ? packUnit : unit
  const unitOptions = groups.flatMap((g) => g.units.map((u) => ({ value: u, label: `${u} (${g.kind})` })))
  const missingVendorName = vendorId === NEW_VENDOR && vendorName.trim() === ''

  async function create() {
    setSaving(true)
    setError(null)
    try {
      let vendor: string | null = vendorId === '' ? null : vendorId
      if (vendorId === NEW_VENDOR) {
        const created = await createVendor(vendorName.trim())
        setVendors((list) => [...list, created])
        setVendorId(created.id)
        vendor = created.id
      }
      const ingredient = await createIngredient({
        name: name.trim(),
        base_unit: unit,
        vendor_id: vendor,
        pack_size: packSize.trim() || null,
        pack_unit: packSize.trim() ? chosenPackUnit : null,
        pack_price: packPrice.trim() || null,
      })
      onCreated(refFromIngredient(ingredient))
    } catch (e) {
      setError(e instanceof RecipeApiError ? e.message : 'Could not create the ingredient. Try again.')
      setSaving(false)
    }
  }

  return (
    <Dialog
      open
      width={520}
      title="New ingredient"
      onClose={onClose}
      actions={<>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="primary" disabled={saving || name.trim() === '' || missingVendorName} onClick={() => void create()}>
          Create ingredient
        </Button>
      </>}
    >
      {error && <p className="field-error" role="alert">{error}</p>}
      <TextField label="Name" value={name} onChange={setName} />
      <Select
        label="Measured in"
        help="Recipes can use any unit of the same kind: an ingredient measured in g also takes kg, oz or lb."
        value={unit}
        options={unitOptions}
        onChange={setUnit}
      />
      <Select
        label="Vendor (optional)"
        value={vendorId}
        options={[
          { value: '', label: 'No vendor yet' },
          ...vendors.map((v) => ({ value: v.id, label: v.name })),
          { value: NEW_VENDOR, label: 'New vendor…' },
        ]}
        onChange={setVendorId}
      />
      {vendorId === NEW_VENDOR && (
        <TextField label="Vendor name" placeholder="e.g. Sysco" value={vendorName} onChange={setVendorName} />
      )}
      <div className="field-row">
        <NumberField className="grow" label="Pack holds (optional)" placeholder="e.g. 5" value={packSize} onChange={setPackSize} />
        <Select
          className="w-100"
          label="Unit"
          value={chosenPackUnit}
          options={kindUnits.map((u) => ({ value: u, label: u }))}
          onChange={setPackUnit}
        />
        <NumberField className="grow" label="Pack price (optional)" unit="$" placeholder="0.00" value={packPrice} onChange={setPackPrice} />
      </div>
    </Dialog>
  )
}
