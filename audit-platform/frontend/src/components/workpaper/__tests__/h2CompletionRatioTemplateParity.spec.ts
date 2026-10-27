/**
 * H2-2 明细表 D 列「工程累计投入占预算比例%」与权威模板同口径
 * （spec oo-writeback-template-parity-closure R2）。
 *
 * 模板 D = IF(B=0,0,AG/B)：审定期末余额 / 预算，单元格格式 0.00% ⇒ 存比值、展示百分数。
 * 模板原为 IF(AH=0,0,AH/B)（取成右边一列「其中：累计资本化金额」），与同表 AV / AW 一样错一列，
 * 已修模板；表单原先按「累计投入 / 预算 × 100」存百分数，与 OnlyOffice 重算值永远对不上。
 */
import { describe, expect, it } from 'vitest'

import { normalizeH2DetailRows } from '../composables/useH2Detail'
import { calcBudgetInputRatio, calcCompletionRate } from '../composables/useH2FormulaEngine'

describe('H2-2 D 列与模板同口径', () => {
  it('比值 = 审定期末余额 / 预算；预算为 0 时为 0（模板 IF(B=0,0,…)）', () => {
    expect(calcBudgetInputRatio(3_000_000, 10_000_000)).toBe(0.3)
    expect(calcBudgetInputRatio(12_000_000, 10_000_000)).toBe(1.2)
    expect(calcBudgetInputRatio(5, 0)).toBe(0)
  })

  it('明细行按审定期末余额算，不再用「累计投入」；期末审定净值 = AG − AS', () => {
    const [row] = normalizeH2DetailRows([{
      rowId: 'r1', name: '厂房扩建', budget: 10_000_000, accumulatedInput: 9_000_000,
      cipBegin: 2_000_000, adjustBegin: 500_000, increaseMaterial: 1_500_000,
      transferAmount: 1_000_000, decrease: 0, impairmentBegin: 100_000,
    }])
    // AG = Z + AB − AD − AE = (2,000,000 + 500,000) + 1,500,000 − 1,000,000 − 0
    expect(row.endAudited).toBe(3_000_000)
    expect(row.completionRate).toBeCloseTo(0.3, 10)
    // 旧口径（累计投入 / 预算 × 100）会得 90，样例能区分两种口径
    expect(calcCompletionRate(9_000_000, 10_000_000)).toBe(90)
    expect(row.netEndAud).toBe(3_000_000 - 100_000)
  })

  it('预算为 0 的行比值为 0（与模板一致，不是 null）', () => {
    const [row] = normalizeH2DetailRows([{ rowId: 'r2', name: '待立项', budget: 0, cipBegin: 100 }])
    expect(row.completionRate).toBe(0)
  })

  it('期初调整为 0 是合法录入：不按存库的期初审定反推（模板 Z = J + S）', () => {
    // OO 侧把期初调整清成 0，存库的 beginAudited 还是上一版公式缓存值 1,200
    const [row] = normalizeH2DetailRows([{ rowId: 'r3', name: '仓库', cipBegin: 1_000, adjustBegin: 0, beginAudited: 1_200 }])
    expect(row.adjustBegin).toBe(0)
    expect(row.beginAudited).toBe(1_000)
  })

  it('只有旧行（根本没有 adjustBegin 键）才按期初审定反推调整额', () => {
    const [row] = normalizeH2DetailRows([{ rowId: 'r4', name: '旧行', cipBegin: 1_000, beginAudited: 1_200 }])
    expect(row.adjustBegin).toBe(200)
    expect(row.beginAudited).toBe(1_200)
  })
})
