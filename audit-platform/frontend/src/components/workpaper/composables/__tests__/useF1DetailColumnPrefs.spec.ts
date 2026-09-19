/**
 * useF1DetailColumnPrefs — 列分组预设
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useF1DetailColumnPrefs } from '../useF1DetailColumnPrefs'

describe('useF1DetailColumnPrefs', () => {
  beforeEach(() => {
    localStorage.removeItem('F1-detail-column-prefs')
  })

  it('defaults to all groups visible', () => {
    const { isGroupVisible, activePreset } = useF1DetailColumnPrefs()
    expect(activePreset.value).toBe('all')
    expect(isGroupVisible('prior')).toBe(true)
    expect(isGroupVisible('auditedAging')).toBe(true)
  })

  it('core preset hides aging groups', () => {
    const { applyPreset, isGroupVisible, activePreset } = useF1DetailColumnPrefs()
    applyPreset('core')
    expect(activePreset.value).toBe('core')
    expect(isGroupVisible('movement')).toBe(true)
    expect(isGroupVisible('audited')).toBe(true)
    expect(isGroupVisible('priorAging')).toBe(false)
  })

  it('toggleGroup marks custom and persists', () => {
    const prefs = useF1DetailColumnPrefs()
    prefs.applyPreset('all')
    prefs.toggleGroup('prior', false)
    expect(prefs.activePreset.value).toBe('custom')
    expect(prefs.isGroupVisible('prior')).toBe(false)
    const raw = localStorage.getItem('F1-detail-column-prefs')
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw!).groups).not.toContain('prior')
  })
})
