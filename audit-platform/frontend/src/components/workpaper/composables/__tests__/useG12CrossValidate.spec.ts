import { describe, it, expect } from 'vitest'
import {
  findG12FvCrossMismatches,
  findG12AdjudicationHedgeMismatches,
  formatG12AdjudicationHedgeCrossMessage,
  formatG12FvCrossSummaryMessage,
  hasG12HedgeDetailData,
  hasG12FvTestData,
  parseG12FvTestRows,
} from '../useG12CrossValidate'
import { isVoucherAbnormal } from '../useG12FormulaEngine'
import type { ChecklistResponse } from '../useF1FormData'

describe('useG12CrossValidate', () => {
  it('findG12AdjudicationHedgeMismatches compares unadjusted vs G12-2 totals', () => {
    const adjRows = [
      { rowKey: 'instrument_fv', label: '套期工具公允价值变动', currentUnadjusted: 100 },
      { rowKey: 'net_hedge', label: '净敞口套期收益', currentUnadjusted: 50 },
    ]
    const mismatches = findG12AdjudicationHedgeMismatches(adjRows, {
      instrumentFVChange: 80,
      itemFVChange: 0,
      ineffectiveness: 0,
      profitLossAmount: 50,
    })
    expect(mismatches).toHaveLength(1)
    expect(mismatches[0].rowKey).toBe('instrument_fv')
    expect(mismatches[0].variance).toBe(20)
    const msg = formatG12AdjudicationHedgeCrossMessage(mismatches)
    expect(msg).toMatch(/G12-1 与 G12-2/)
    expect(msg).toMatch(/未审 100\.00/)
  })

  it('findG12AdjudicationHedgeMismatches ignores matching totals within tolerance', () => {
    const adjRows = [
      { rowKey: 'instrument_fv', label: '套期工具公允价值变动', currentUnadjusted: 100.005 },
    ]
    expect(findG12AdjudicationHedgeMismatches(adjRows, {
      instrumentFVChange: 100,
      itemFVChange: 0,
      ineffectiveness: 0,
      profitLossAmount: 0,
    })).toHaveLength(0)
  })

  it('hasG12HedgeDetailData detects stored hedge rows', () => {
    const empty = new Map<string, ChecklistResponse>()
    expect(hasG12HedgeDetailData(empty)).toBe(false)
    const withRows = new Map<string, ChecklistResponse>([
      ['G12-hedge-detail-rows', { remark: JSON.stringify([{ hedgeRelationId: 'HR-1' }]) } as ChecklistResponse],
    ])
    expect(hasG12HedgeDetailData(withRows)).toBe(true)
  })

  it('hasG12FvTestData detects stored fv test rows', () => {
    expect(hasG12FvTestData(new Map())).toBe(false)
    const withRows = new Map<string, ChecklistResponse>([
      ['G12-fv-test-rows', { remark: JSON.stringify([{ hedgeRelationId: 'HR-1' }]) } as ChecklistResponse],
    ])
    expect(hasG12FvTestData(withRows)).toBe(true)
  })

  it('formatG12FvCrossSummaryMessage summarizes mismatches', () => {
    const mismatches = [{
      hedgeRelationId: 'HR-001',
      field: 'instrumentFVChange' as const,
      hedgeValue: 100,
      fvTestValue: 80,
      variance: 20,
    }]
    const msg = formatG12FvCrossSummaryMessage(mismatches)
    expect(msg).toMatch(/G12-2 与 G12-4/)
    expect(msg).toMatch(/HR-001/)
  })

  it('parseG12FvTestRows reads instrument/item FV changes', () => {
    const map = new Map<string, ChecklistResponse>([
      ['G12-fv-test-rows', {
        remark: JSON.stringify([
          { hedgeRelationId: 'HR-001', instrumentFVChange: 100, itemFVChange: -95 },
        ]),
      } as ChecklistResponse],
    ])
    const parsed = parseG12FvTestRows(map)
    expect(parsed.get('HR-001')).toEqual({ instrumentFVChange: 100, itemFVChange: -95 })
  })

  it('findG12FvCrossMismatches flags variance > tolerance', () => {
    const hedgeRows = [{ hedgeRelationId: 'HR-001', instrumentFVChange: 100, itemFVChange: 80 }]
    const allResponses = new Map<string, ChecklistResponse>([
      ['G12-fv-test-rows', {
        remark: JSON.stringify([
          { hedgeRelationId: 'HR-001', instrumentFVChange: 50, itemFVChange: 80 },
        ]),
      } as ChecklistResponse],
    ])
    const mismatches = findG12FvCrossMismatches(hedgeRows, allResponses)
    expect(mismatches).toHaveLength(1)
    expect(mismatches[0].field).toBe('instrumentFVChange')
    expect(mismatches[0].variance).toBe(50)
  })

  it('findG12FvCrossMismatches ignores matching values within tolerance', () => {
    const hedgeRows = [{ hedgeRelationId: 'HR-002', instrumentFVChange: 100.005, itemFVChange: 100 }]
    const allResponses = new Map<string, ChecklistResponse>([
      ['G12-fv-test-rows', {
        remark: JSON.stringify([
          { hedgeRelationId: 'HR-002', instrumentFVChange: 100, itemFVChange: 100 },
        ]),
      } as ChecklistResponse],
    ])
    expect(findG12FvCrossMismatches(hedgeRows, allResponses)).toHaveLength(0)
  })
})

describe('G12 voucher abnormal', () => {
  it('isVoucherAbnormal true when any check fails', () => {
    expect(isVoucherAbnormal([true, true, false, true, true, true])).toBe(true)
    expect(isVoucherAbnormal([true, true, true, true, true, true])).toBe(false)
    expect(isVoucherAbnormal([null, true, true, null, true, true])).toBe(false)
  })
})
