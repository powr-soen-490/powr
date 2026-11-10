// Source-File AI Declaration
// AI contribution: 50% or more AI-generated

import { describe, expect, it } from 'vitest'
import { getVisibleNavigation, PAGE_FLAGS } from './navigation'

describe('getVisibleNavigation', () => {
  it('only includes pages with enabled flags', () => {
    const navigation = getVisibleNavigation((flag) => flag !== PAGE_FLAGS.inventory)

    expect(navigation.map(({ id }) => id)).not.toContain('inventory')
    expect(navigation).toHaveLength(5)
  })

  it('returns no pages when all page flags are disabled', () => {
    expect(getVisibleNavigation(() => false)).toEqual([])
  })
})
