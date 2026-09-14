/**
 * useH8DetailColumnPrefs — H8-2 列分组预设
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useH8DetailColumnPrefs } from '../useH8DetailColumnPrefs'

describe('useH8DetailColumnPrefs', () => {
  beforeEach(() => {
    localStorage.removeItem('H8-2-detail-column-prefs')
  })

  it('defaults to core (unadj + audited)', () => {
    const { isGroupVisible, activePreset } = useH8DetailColumnPrefs()
    expect(activePreset.value).toBe('core')
    expect(isGroupVisible('unadj')).toBe(true)
    expect(isGroupVisible('audited')).toBe(true)
    expect(isGroupVisible('openAdj')).toBe(false)
    expect(isGroupVisible('aje')).toBe(false)
  })

  it('full preset shows all groups', () => {
    const { applyPreset, isGroupVisible, activePreset } = useH8DetailColumnPrefs()
    applyPreset('full')
    expect(activePreset.value).toBe('full')
    expect(isGroupVisible('unadj')).toBe(true)
    expect(isGroupVisible('openAdj')).toBe(true)
    expect(isGroupVisible('aje')).toBe(true)
    expect(isGroupVisible('audited')).toBe(true)
  })

  it('toggleGroup marks custom and persists; keeps at least unadj or audited', () => {
    const prefs = useH8DetailColumnPrefs()
    prefs.applyPreset('full')
    prefs.toggleGroup('openAdj', false)
    expect(prefs.activePreset.value).toBe('custom')
    expect(prefs.isGroupVisible('openAdj')).toBe(false)

    prefs.toggleGroup('unadj', false)
    prefs.toggleGroup('audited', false)
    expect(prefs.isGroupVisible('unadj')).toBe(true)

    const raw = localStorage.getItem('H8-2-detail-column-prefs')
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!).preset).toBe('custom')
  })
})
