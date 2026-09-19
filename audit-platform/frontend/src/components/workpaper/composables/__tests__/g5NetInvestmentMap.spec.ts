/**
 * G5 → G7-16 实质净投资长期应收 Map
 */
import { describe, expect, it } from 'vitest'
import { buildG52NetInvestmentMap } from '../../composables/g5CrossHelpers'

describe('buildG52NetInvestmentMap', () => {
  it('sums related-party net amounts and skips one-year rows', () => {
    const map = buildG52NetInvestmentMap([
      { debtorName: '联营甲', netAmount: 100, isRelatedParty: true, isWithinOneYear: false },
      { debtorName: '联营甲', netAmount: 20, isRelatedParty: true, isWithinOneYear: false },
      { debtorName: '联营甲', netAmount: 50, isRelatedParty: true, isWithinOneYear: true },
      { debtorName: '外部客户', netAmount: 999, isRelatedParty: false },
    ])
    expect(map.get('联营甲')).toBe(120)
    expect(map.has('外部客户')).toBe(false)
  })

  it('relatedPartyOnly=false includes non-related', () => {
    const map = buildG52NetInvestmentMap(
      [{ debtorName: '外部客户', closingBalance: 80, isRelatedParty: false }],
      { relatedPartyOnly: false },
    )
    expect(map.get('外部客户')).toBe(80)
  })
})
