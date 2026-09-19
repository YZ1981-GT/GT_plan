import { describe, it, expect } from 'vitest'
import {
  computeK11ComboCrossCheck,
  draftVarianceReason,
  parseK16ComboBases,
  K1_VARIANCE_THRESHOLD,
} from '../k1AdjudicationCross'

describe('parseK16ComboBases', () => {
  it('parses combo basis names from JSON', () => {
    const raw = JSON.stringify([
      { basis: '账龄组合' },
      { basis: '客户类型组合' },
    ])
    expect(parseK16ComboBases(raw)).toEqual(['账龄组合', '客户类型组合'])
  })

  it('returns empty for invalid input', () => {
    expect(parseK16ComboBases('')).toEqual([])
    expect(parseK16ComboBases('not-json')).toEqual([])
  })
})

describe('computeK11ComboCrossCheck', () => {
  it('flags mismatch between K1-6 and K1-8 group names', () => {
    const map = new Map<string, any>()
    map.set('K1-6-combos', {
      remark: JSON.stringify([{ basis: '账龄组合' }, { basis: '客户类型组合' }]),
    })
    map.set('K1-8-bad-debt-calc', {
      remark: JSON.stringify({
        version: 2,
        creditGroups: [{ groupName: '账龄组合' }],
        agingGroups: [{ groupName: '其他组合' }],
        singleItems: [],
      }),
    })
    const result = computeK11ComboCrossCheck(map, ['单项计提', '账龄组合', '客户类型组合', '其他组合'])
    expect(result.hasK18Data).toBe(true)
    expect(result.isConsistent).toBe(false)
    expect(result.onlyInK16.length + result.onlyInK18.length).toBeGreaterThan(0)
  })

  it('falls back to K1-1 portfolio labels when K1-6 empty', () => {
    const map = new Map<string, any>()
    const labels = ['单项计提', '账龄组合']
    const result = computeK11ComboCrossCheck(map, labels)
    expect(result.k16Names).toEqual(['账龄组合'])
  })
})

describe('draftVarianceReason', () => {
  it('returns empty when below threshold', () => {
    expect(draftVarianceReason('账龄组合', 0.2)).toBe('')
    expect(draftVarianceReason('账龄组合', null)).toBe('')
  })

  it('drafts increase/decrease reason above threshold', () => {
    const up = draftVarianceReason('账龄组合', 0.35)
    expect(up).toContain('增加')
    expect(up).toContain('35.0%')
    const down = draftVarianceReason('客户类型', -0.4)
    expect(down).toContain('减少')
    expect(down).toContain('40.0%')
  })

  it('uses 30% threshold constant', () => {
    expect(K1_VARIANCE_THRESHOLD).toBe(0.3)
    expect(draftVarianceReason('x', 0.29)).toBe('')
    expect(draftVarianceReason('x', 0.31)).not.toBe('')
  })
})
