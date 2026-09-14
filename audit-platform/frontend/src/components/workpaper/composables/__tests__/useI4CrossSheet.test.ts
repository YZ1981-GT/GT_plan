/**
 * useI4CrossSheet 单元测试 — I4-2/3/6·7 聚合
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useI4CrossSheet } from '../useI4CrossSheet'

function makeMap(extra?: Record<string, unknown>) {
  const m = new Map<string, { item_id: string; conclusion: null; remark: string | null }>()
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      m.set(k, {
        item_id: k,
        conclusion: null,
        remark: typeof v === 'string' ? v : JSON.stringify(v),
      })
    }
  }
  return ref(m)
}

describe('useI4CrossSheet', () => {
  it('detailTotals 聚合 I4-2 滚转字段（含审定别名）', () => {
    const allResponses = makeMap({
      'I4-2-rows': [
        {
          projectName: '装修A',
          originalAmount: 120,
          auditedOpening: 100,
          auditedIncrease: 30,
          auditedAmortization: 20,
          auditedOtherDecrease: 5,
          auditedEnding: 105,
        },
        { projectName: '合计', endBalance: 999 },
      ],
    })
    const { detailTotals, adjudicationFromDetail } = useI4CrossSheet(allResponses as any)
    expect(detailTotals.value.beginBalance).toBe(100)
    expect(detailTotals.value.increase).toBe(30)
    expect(detailTotals.value.amortization).toBe(20)
    expect(detailTotals.value.decrease).toBe(5)
    expect(detailTotals.value.endBalance).toBe(105)
    expect(detailTotals.value.total).toBe(120)
    expect(adjudicationFromDetail.value.audited).toBe(105)
  })

  it('amortizationRowsRaw 优先 I4-6，无则回退 I4-7', () => {
    const both = makeMap({
      'I4-6-rows': [{ name: '直线', yearTotal: 12 }],
      'I4-7-rows': [{ name: '工作量', yearTotal: 99 }],
    })
    expect(useI4CrossSheet(both as any).amortizationRowsRaw.value[0].yearTotal).toBe(12)

    const only7 = makeMap({
      'I4-7-rows': [{ name: '工作量', yearTotal: 48, monthlyAmorts: Array(12).fill(4) }],
    })
    const cs = useI4CrossSheet(only7 as any)
    expect(cs.amortizationRowsRaw.value[0].yearTotal).toBe(48)
    expect(cs.amortizationMatrix.value[0]).toEqual(Array(12).fill(4))
  })

  it('adjustmentRowsRaw 解析 I4-3', () => {
    const allResponses = makeMap({
      'I4-3-rows': [
        { description: '费用化', accountCode: '1801', debitAmount: 0, creditAmount: 10 },
      ],
    })
    const { adjustmentRowsRaw } = useI4CrossSheet(allResponses as any)
    expect(adjustmentRowsRaw.value).toHaveLength(1)
    expect(adjustmentRowsRaw.value[0].accountCode).toBe('1801')
  })
})
