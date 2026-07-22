import { describe, expect, it } from 'vitest'
import {
  isFromG106,
  listG10Fv5VsG96AssetMismatches,
  pushG10L3VarianceToAdjustment,
  selectG10L3VarianceTargets,
} from '../g10L3CrossHelpers'
import { enrichG10L3Row } from '../useG10L3Reconciliation'
import type { ChecklistResponse } from '../useF1FormData'

function responses(data: Record<string, unknown>): Map<string, ChecklistResponse> {
  const m = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(data)) {
    m.set(k, { item_id: k, remark: typeof v === 'string' ? v : JSON.stringify(v) } as ChecklistResponse)
  }
  return m
}

describe('g10L3CrossHelpers', () => {
  it('isFromG106 识别 G10-6 来源', () => {
    expect(isFromG106({ summary: 'G10-6 L3调节差异：债券A', indexRef: 'G10-6' })).toBe(true)
    expect(isFromG106({ summary: 'G10-5 公允测试差异：A' })).toBe(false)
  })

  it('listG10Fv5VsG96AssetMismatches 逐笔勾稽', () => {
    const list = listG10Fv5VsG96AssetMismatches(responses({
      'G10-fv-test-rows': [{ liabilityName: '债券A', fairValueLevel: 'Level3', closingAuditedFV: 100 }],
      'G10-l3-rows': [{ liabilityName: '债券A', reportedClosing: 80 }],
    }))
    expect(list).toHaveLength(1)
    expect(list[0].diff).toBe(20)
  })

  it('selectG10L3VarianceTargets 选取差异行', () => {
    const rows = [
      enrichG10L3Row({
        rowId: '1',
        liabilityName: 'A',
        openingBalance: 100,
        reportedClosing: 120,
      }),
    ]
    expect(selectG10L3VarianceTargets(rows)).toHaveLength(1)
  })

  it('pushG10L3VarianceToAdjustment 负债上升 Dr6101/Cr2101', () => {
    const saves: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const m = responses({})
    const n = pushG10L3VarianceToAdjustment(
      m,
      (id, data) => { saves.push({ id, data }) },
      [{ liabilityName: '债券A', variance: 50, closingBalance: 100, reportedClosing: 150 }],
    )
    expect(n).toBe(1)
    const adjRaw = saves.find((s) => s.id === 'G10-aje-rows')?.data.remark
    expect(adjRaw).toBeTruthy()
    const rows = JSON.parse(String(adjRaw))
    const dr6101 = rows.find((r: { accountCode: string; debitAmount: number }) => r.accountCode === '6101')
    const cr2101 = rows.find((r: { accountCode: string; creditAmount: number }) => r.accountCode === '2101')
    expect(dr6101.debitAmount).toBe(50)
    expect(cr2101.creditAmount).toBe(50)
  })
})
