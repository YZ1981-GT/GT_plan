import { describe, it, expect } from 'vitest'
import {
  buildG714SuggestedG11Adjustments,
  mergeSuggestedIntoG11Aje,
  pushSuggestedAdjustmentsFromG714Seeds,
  G714_G11_SUGGESTED_SOURCE_KIND,
} from '../g11EquityMethodPushG113'
import type { G11EquityIncomeSeed } from '../g11CrossHelpers'

describe('g11EquityMethodPushG113', () => {
  const seed: G11EquityIncomeSeed = {
    investeeName: '甲公司',
    currentUnadjusted: 100000,
    equityShare: 95000,
    incomeDifference: 5000,
    reasonIndex: 'wp:G7-14',
  }

  it('buildG714SuggestedG11Adjustments 生成平衡 6111↔1511 分录', () => {
    const lines = buildG714SuggestedG11Adjustments([seed])
    expect(lines).toHaveLength(2)
    expect(lines[0].accountCode).toBe('6111')
    expect(lines[0].debitAmount).toBe(5000)
    expect(lines[1].accountCode).toBe('1511')
    expect(lines[1].creditAmount).toBe(5000)
    expect(lines[0].adjudicationRowKey).toBe('equity_method')
  })

  it('mergeSuggestedIntoG11Aje 替换同源 G7-14 草稿', () => {
    const existing = [
      {
        rowId: 'old',
        description: '【G7-14】旧草稿',
        remark: `sourceKind=${G714_G11_SUGGESTED_SOURCE_KIND}`,
        sourceKind: G714_G11_SUGGESTED_SOURCE_KIND,
      },
      { rowId: 'manual', description: '手工分录', remark: 'manual' },
    ]
    const suggested = buildG714SuggestedG11Adjustments([seed])
    const merged = mergeSuggestedIntoG11Aje(existing, suggested)
    expect(merged).toHaveLength(3)
    expect(merged.some((r) => r.rowId === 'manual')).toBe(true)
    expect(merged.some((r) => r.rowId === 'old')).toBe(false)
  })

  it('pushSuggestedAdjustmentsFromG714Seeds 写入并回写', () => {
    const responses = new Map<string, any>()
    const saved: Array<{ id: string; data: any }> = []
    const result = pushSuggestedAdjustmentsFromG714Seeds({
      responses,
      debouncedSave: (id, data) => {
        saved.push({ id, data })
        responses.set(id, { item_id: id, remark: data.remark })
      },
      seeds: [seed],
    })
    expect(result.ok).toBe(true)
    expect(result.written).toBe(2)
    expect(saved.some((s) => s.id === 'G11-aje-rows')).toBe(true)
    expect(saved.some((s) => s.id === 'G11-adj-rows')).toBe(true)
  })
})
