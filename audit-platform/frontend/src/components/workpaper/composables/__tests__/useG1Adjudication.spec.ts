import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { buildG1AdjudicationRows, useG1Adjudication } from '../useG1Adjudication'
import {
  G1_ADJUDICATION_ITEMS,
  leafKeysForSection,
  applyG1AdjustmentWriteback,
  G1_ADJ_WRITEBACK_ROW_KEY,
} from '../g1AdjudicationItems'
import type { ChecklistResponse } from '../useF1FormData'

describe('applyG1AdjustmentWriteback', () => {
  it('写入默认回写行期末账项调整', () => {
    const next = applyG1AdjustmentWriteback({}, 1200)
    expect(next[G1_ADJ_WRITEBACK_ROW_KEY].closingAdjustment).toBe(1200)
    expect(next[G1_ADJ_WRITEBACK_ROW_KEY].reasonAnalysis).toContain('G1-3')
  })
})

describe('buildG1AdjudicationRows', () => {
  it('行数与模板定义一致', () => {
    const rows = buildG1AdjudicationRows({})
    expect(rows).toHaveLength(G1_ADJUDICATION_ITEMS.length)
  })

  it('投资成本明细可编辑；账面余额由成本+FV 自动汇总', () => {
    const rows = buildG1AdjudicationRows({
      'cost-trading-debt': {
        openingUnadjusted: 100,
        openingAdjustment: 10,
        closingUnadjusted: 200,
        closingAdjustment: 20,
      },
      'fv-trading-debt': {
        openingUnadjusted: 5,
        openingAdjustment: 0,
        closingUnadjusted: 15,
        closingAdjustment: 5,
      },
    })

    const cost = rows.find((r) => r.rowKey === 'cost-trading-debt')!
    expect(cost.editable).toBe(true)
    expect(cost.openingAudited).toBe(110)
    expect(cost.closingAudited).toBe(220)

    const carrying = rows.find((r) => r.rowKey === 'carrying-trading-debt')!
    expect(carrying.editable).toBe(false)
    expect(carrying.openingAudited).toBe(115)
    expect(carrying.closingAudited).toBe(240)
  })

  it('分类行与小计汇总叶子；账面余额合计扣减一年以上到期', () => {
    const store: Record<string, { closingUnadjusted: number }> = {
      'footer-over-one-year': { closingUnadjusted: 50 },
    }
    for (const key of leafKeysForSection('cost')) {
      store[key] = { closingUnadjusted: 10 }
    }
    for (const key of leafKeysForSection('fv')) {
      store[key] = { closingUnadjusted: 2 }
    }

    const rows = buildG1AdjudicationRows(store)
    const costSub = rows.find((r) => r.rowKey === 'cost__subtotal')!
    const fvSub = rows.find((r) => r.rowKey === 'fv__subtotal')!
    const carryingSub = rows.find((r) => r.rowKey === 'carrying__subtotal')!
    const book = rows.find((r) => r.rowKey === 'footer-book-total')!

    expect(costSub.closingAudited).toBe(10 * leafKeysForSection('cost').length)
    expect(fvSub.closingAudited).toBe(2 * leafKeysForSection('fv').length)
    expect(carryingSub.closingAudited).toBe(costSub.closingAudited + fvSub.closingAudited)
    expect(book.closingAudited).toBe(carryingSub.closingAudited - 50)
  })

  it('|变动率|>30% 时高亮并要求原因分析', () => {
    const rows = buildG1AdjudicationRows({
      'cost-trading-equity': {
        openingUnadjusted: 100,
        closingUnadjusted: 150,
      },
    })
    const row = rows.find((r) => r.rowKey === 'cost-trading-equity')!
    expect(row.changeRateHighlight).toBe(true)
    expect(row.reasonRequired).toBe(true)
  })
})

describe('useG1Adjudication.syncFromDetail', () => {
  it('从 G1-2 汇总未审并保留调整', () => {
    const allResponses = ref(
      new Map<string, ChecklistResponse>([
        [
          'G1-2-rows',
          {
            conclusion: JSON.stringify([
              {
                id: '1',
                securityName: '债A',
                acctClass: 'trading',
                investType: 'bond',
                openingCost: 100,
                closingCost: 120,
                openingCumulativeFv: 5,
                cumulativeFVChange: 8,
                closingLtDeduction: 10,
              },
            ]),
          } as ChecklistResponse,
        ],
        [
          'G1-1-rows',
          {
            remark: JSON.stringify({
              'cost-trading-debt': { openingAdjustment: 2, closingAdjustment: 3 },
            }),
          } as ChecklistResponse,
        ],
      ]),
    )
    const adj = useG1Adjudication({
      allResponses,
      debouncedSave: () => {},
      isReadonly: ref(false),
    })
    expect(adj.syncFromDetail()).toBe(1)
    const cost = adj.rows.value.find((r) => r.rowKey === 'cost-trading-debt')
    expect(cost?.openingUnadjusted).toBe(100)
    expect(cost?.closingUnadjusted).toBe(120)
    expect(cost?.openingAdjustment).toBe(2)
    expect(cost?.closingAdjustment).toBe(3)
    const fv = adj.rows.value.find((r) => r.rowKey === 'fv-trading-debt')
    expect(fv?.openingUnadjusted).toBe(5)
    expect(fv?.closingUnadjusted).toBe(8)
  })
})
