/**
 * H9-1 fillFromDetail + 公式增强单测
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import {
  calcFsAmount,
  calcChangeAmount,
  calcChangeRate,
  calcMaturityBucketsSum,
} from '../useH9FormulaEngine'
import { useH9Adjudication } from '../useH9Adjudication'

function makeMap(entries: Record<string, unknown>) {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, remark: typeof v === 'string' ? v : JSON.stringify(v) })
  }
  return m
}

describe('useH9FormulaEngine — Excel 对齐公式', () => {
  it('报表数 = 审定 − 重分类', () => {
    expect(calcFsAmount(1000, 200)).toBe(800)
  })

  it('变动额/率对齐 Excel M 列边界', () => {
    expect(calcChangeAmount(800, 500)).toBe(300)
    expect(calcChangeRate(500, 300)).toBeCloseTo(0.6)
    expect(calcChangeRate(0, 0)).toBe(0)
    expect(calcChangeRate(0, 100)).toBe(1)
  })

  it('到期四档合计', () => {
    expect(calcMaturityBucketsSum(100, 50, 30, 20)).toBe(200)
  })
})

describe('useH9Adjudication — fillFromDetail', () => {
  it('book 模式从 H9-2/H9-3 写入未审并保留 AJE', () => {
    const saved: Record<string, any> = {}
    const allResponses = ref(makeMap({
      'H9-2-rows': [{
        lessor: '甲公司', beginBalance: 1000, repayment: 200, interestAccrued: 50,
        beginAje: 0, repayAje: 0, interestAje: 0, reclassification: 300,
      }],
      'H9-3-rows': [{
        lessor: '甲公司', beginBalance: 100, debitIncrease: 20, creditDecrease: 30,
        beginAje: 0, increaseAje: 0, confirmAje: 0, otherAje: 0, reclassification: 10,
      }],
      'H9-1-rows': [{
        rowId: 'L1', name: '租赁负债合计', block: 'liability',
        beginBalance: 0, creditAmount: 0, debitAmount: 0,
        unadjusted: 0, aje: 5, rje: 0, reclassification: 0,
      }],
    }))

    const api = useH9Adjudication({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses,
      onSave: (id, v) => { saved[id] = v },
    })

    const res = api.fillFromDetail('book')
    expect(res.liabilityFilled).toBe(true)
    expect(res.unearnedFilled).toBe(true)

    const liab = api.liabilityRows.value[0]
    expect(liab.beginBalance).toBe(1000)
    expect(liab.debitAmount).toBe(200)
    expect(liab.creditAmount).toBe(50)
    expect(liab.unadjusted).toBe(850) // 1000-200+50
    expect(liab.reclassification).toBe(300)
    expect(liab.aje).toBe(5) // 保留

    const une = api.unearnedRows.value[0]
    expect(une.beginBalance).toBe(100)
    expect(une.debitAmount).toBe(20)
    expect(une.creditAmount).toBe(30)
    expect(une.unadjusted).toBe(90) // 100+20-30
    expect(une.reclassification).toBe(10)

    expect(saved['H9-1-liability-total-audited']).toBeDefined()
  })

  it('full 模式用审定覆盖并清零 AJE/RJE', () => {
    const allResponses = ref(makeMap({
      'H9-2-rows': [{
        lessor: '乙', beginBalance: 500, repayment: 0, interestAccrued: 0,
        beginAje: 10, repayAje: 0, interestAje: 0, reclassification: 0,
      }],
    }))
    const api = useH9Adjudication({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses,
      onSave: vi.fn(),
    })
    const res = api.fillFromDetail('full')
    expect(res.liabilityFilled).toBe(true)
    const liab = api.liabilityRows.value[0]
    expect(liab.unadjusted).toBe(510) // audited begin end with aje
    expect(liab.aje).toBe(0)
    expect(liab.rje).toBe(0)
  })
})
