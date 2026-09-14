import { describe, it, expect, beforeEach } from 'vitest'
import { useK1DetailColumnPrefs } from '../useK1DetailColumnPrefs'

describe('useK1DetailColumnPrefs', () => {
  beforeEach(() => {
    localStorage.removeItem('K1-2-detail-column-prefs')
  })

  it('defaults to all columns visible', () => {
    const prefs = useK1DetailColumnPrefs()
    expect(prefs.activePreset.value).toBe('all')
    expect(prefs.isColVisible('nature')).toBe(true)
    expect(prefs.isColVisible('agingBands')).toBe(true)
  })

  it('applyPreset core hides optional meta cols', () => {
    const prefs = useK1DetailColumnPrefs()
    prefs.applyPreset('core')
    expect(prefs.activePreset.value).toBe('core')
    expect(prefs.isColVisible('endBalance')).toBe(true)
    expect(prefs.isColVisible('remark')).toBe(false)
  })

  it('toggleCol switches to custom', () => {
    const prefs = useK1DetailColumnPrefs()
    prefs.toggleCol('nature', false)
    expect(prefs.activePreset.value).toBe('custom')
    expect(prefs.isColVisible('nature')).toBe(false)
  })
})
