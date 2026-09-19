/**
 * useF2CrossSheet — 单元测试
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useF2CrossSheet } from '../useF2CrossSheet'
import type { ChecklistResponse } from '../useF2FormData'

function makeResponses(rowsJson: string): Map<string, ChecklistResponse> {
  const map = new Map<string, ChecklistResponse>()
  map.set('F2-3-rows', {
    item_id: 'F2-3-rows',
    conclusion: null,
    remark: rowsJson,
  })
  return map
}

describe('useF2CrossSheet', () => {
  it('aggregates detail closing amounts from F2-3 remark', () => {
    const rows = JSON.stringify([
      {
        id: '1',
        itemName: 'A',
        openingAmt: 100,
        increaseAmt: 50,
        decreaseAmt: 20,
        closingAmt: 130,
        openingQty: 0,
        increaseQty: 0,
        decreaseQty: 0,
        closingQty: 0,
        unitPrice: 0,
        agingLt1: 0,
        aging1to2: 0,
        aging2to3: 0,
        agingGt3: 0,
        agingTotal: 0,
      },
    ])
    const allResponses = ref(makeResponses(rows))
    const cross = useF2CrossSheet({
      allResponses,
      projectContext: ref({}),
    })

    expect(cross.hasDetailData.value).toBe(true)
    expect(cross.detailGrandTotal.value).toBe(130)
    const raw = cross.categorySummaries.value.find((s) => s.sheetCode === 'F2-3')
    expect(raw?.closingAmt).toBe(130)
    expect(raw?.rowKey).toBe('raw-materials')
  })

  it('reports gross cross validation when totals differ', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const cross = useF2CrossSheet({
      allResponses,
      projectContext: ref({}),
    })
    expect(cross.grossCrossValidation(1000)).toBeNull()

    allResponses.value = makeResponses(JSON.stringify([{
      id: '1', itemName: 'x', openingAmt: 0, increaseAmt: 0, decreaseAmt: 0, closingAmt: 500,
      openingQty: 0, increaseQty: 0, decreaseQty: 0, closingQty: 0, unitPrice: 0,
      agingLt1: 0, aging1to2: 0, aging2to3: 0, agingGt3: 0, agingTotal: 0,
    }]))
    const msg = cross.grossCrossValidation(1000)
    expect(msg).toContain('差异')
  })

  it('routes 1471 AJE to impairment and 1412 AJE to price-difference', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F2-14-rows', {
      item_id: 'F2-14-rows',
      conclusion: null,
      remark: JSON.stringify([
        { entryType: 'AJE', accountCode: '1471', debitAmount: 0, creditAmount: 80 },
        { entryType: 'AJE', accountCode: '1412', debitAmount: 20, creditAmount: 0 },
        { entryType: 'AJE', accountCode: '1406', debitAmount: 50, creditAmount: 0 },
      ]),
    })
    const cross = useF2CrossSheet({
      allResponses: ref(map),
      projectContext: ref({}),
    })
    expect(cross.impairmentAdjustmentByRowKey.value['impairment-provision']).toBe(80)
    expect(cross.grossAdjustmentByRowKey.value['price-difference']).toBe(20)
    expect(cross.grossAdjustmentByRowKey.value['finished-goods']).toBe(50)
  })
})
