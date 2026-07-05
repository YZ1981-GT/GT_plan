/**
 * G10 可选单元测试 — 3.2 / 4.2 / 6.3 / 7.3 / 8.2 / 9.2
 */
import { describe, it, expect } from 'vitest'
import {
  calcCreditBalance,
  calcAdjustedAmount,
  calcChangeRate,
  isChangeRateExceeding,
  isDebitCreditBalanced,
  calcSubtotal,
} from '../composables/useG10FormulaEngine'
import {
  G10_ADJUDICATION_ITEMS,
  G10_GROUP_LABELS,
  G10_CHANGE_RATE_THRESHOLD,
  G10_COMPLIANCE_OPTIONS,
} from '../composables/g10Constants'
import { G10_CLASSIFICATION_SEED } from '../composables/g10ClassificationSeed'
import { G10_DERIVATIVE_SEED } from '../composables/g10DerivativeSeed'
import { enrichG10DetailRow } from '../composables/useG10Detail'
import { createEmptyG10AdjustmentRow } from '../composables/useG10Adjustment'
import { validateG10Level3Row, type G10FairValueRow } from '../composables/useG10FairValueTest'
import { enrichG10L3Row } from '../composables/useG10L3Reconciliation'
import { enrichG10VoucherRow, recalcG10VoucherAbnormal } from '../composables/useG10VoucherCheck'

describe('G10-1 审定表 — 贷方方向与分组', () => {
  it('贷方余额 = 期初审定 + 贷方 - 借方', () => {
    expect(calcCreditBalance(100, 40, 10)).toBe(130)
    expect(calcCreditBalance(100, 10, 40)).toBe(70)
  })

  it('24 行 × 3 分组对齐源模板', () => {
    expect(G10_ADJUDICATION_ITEMS).toHaveLength(24)
    const groups = new Set(G10_ADJUDICATION_ITEMS.map((r) => r.group))
    expect(groups).toEqual(new Set(['initial', 'fv_accum', 'book_fv']))
    expect(G10_GROUP_LABELS.initial).toContain('初始金额')
    expect(G10_GROUP_LABELS.fv_accum).toContain('公允价值变动')
    expect(G10_GROUP_LABELS.book_fv).toContain('账面余额')
  })

  it('|变动率|>20% 触发高亮与原因必填', () => {
    const rate = calcChangeRate(100, 130)
    expect(rate).toBeCloseTo(0.3)
    expect(isChangeRateExceeding(rate, G10_CHANGE_RATE_THRESHOLD)).toBe(true)
    expect(isChangeRateExceeding(0.1, G10_CHANGE_RATE_THRESHOLD)).toBe(false)
  })
})

describe('G10-2 明细 — 区段 Tab 与合计', () => {
  it('enrich 保持两区段字段同步', () => {
    const row = enrichG10DetailRow({ rowId: 't1', liabilityName: '债券A', seq: 1 })
    expect(row.liabilityName).toBe('债券A')
    expect(row.closingAdjusted).toBe(row.closingBalance)
  })

  it('合计行累加', () => {
    const a = enrichG10DetailRow({ rowId: 'a', openingAdjusted: 100 }, 1)
    const b = enrichG10DetailRow({ rowId: 'b', openingAdjusted: 50 }, 2)
    expect(calcSubtotal([a.closingAdjusted, b.closingAdjusted])).toBe(150)
  })
})

describe('G10-3/4 — 借贷平衡与问卷', () => {
  it('G10-3 借贷平衡', () => {
    const rows = [
      { ...createEmptyG10AdjustmentRow(), debitAmount: 100, creditAmount: 0 },
      { ...createEmptyG10AdjustmentRow(), debitAmount: 0, creditAmount: 100 },
    ]
    expect(isDebitCreditBalanced(rows.map((r) => r.debitAmount), rows.map((r) => r.creditAmount))).toBe(true)
  })

  it('G10-4 种子 28 行 + 合规下拉选项', () => {
    expect(G10_CLASSIFICATION_SEED).toHaveLength(28)
    expect(G10_COMPLIANCE_OPTIONS.map((o) => o.value)).toContain('compliant')
  })
})

describe('G10-5/6 — Level3 与 L3 调节', () => {
  it('Level3 缺估值技术/不可观察输入值', () => {
    const row = {
      fairValueLevel: 'Level3',
      valuationTechnique: '',
      unobservableInputDesc: '',
    } as G10FairValueRow
    expect(validateG10Level3Row(row)).toEqual(['估值技术', '不可观察输入值描述'])
  })

  it('L3 调节差异 = 企业期末 - 计算期末', () => {
    const row = enrichG10L3Row({
      rowId: 'l1',
      openingBalance: 100,
      currentNew: 20,
      currentTerminated: 5,
      transferIntoL3: 0,
      transferOutOfL3: 0,
      fairValueChange: 3,
      interestExpense: 1,
      otherChanges: 0,
      reportedClosing: 200,
    })
    expect(row.closingBalance).toBe(119)
    expect(row.variance).toBe(81)
  })
})

describe('G10-7 — 异常检测与借贷', () => {
  it('任一核对✗ → isAbnormal', () => {
    const row = enrichG10VoucherRow({ id: 'v1', check3Accounting: false }, 1)
    expect(row.isAbnormal).toBe(true)
    const ok = recalcG10VoucherAbnormal({
      ...row,
      check1OriginalComplete: true,
      check2Authorization: true,
      check3Accounting: true,
      check4FairValueCorrect: true,
    })
    expect(ok.isAbnormal).toBe(false)
  })

  it('借贷差额汇总', () => {
    expect(isDebitCreditBalanced([50, 30], [80])).toBe(true)
    expect(calcAdjustedAmount(100, 10)).toBe(110)
  })
})

describe('G10-8 — 衍生工具 78 行问卷', () => {
  it('5 section 共 78 行', () => {
    expect(G10_DERIVATIVE_SEED).toHaveLength(78)
    const sections = new Set(G10_DERIVATIVE_SEED.map((r) => r.sectionNo))
    expect(sections.size).toBe(5)
  })
})
