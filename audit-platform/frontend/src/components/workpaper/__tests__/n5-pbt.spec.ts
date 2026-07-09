/**
 * Property-Based Tests — N5 所得税费用公式引擎 + 所得税引擎 + 纳税调整引擎
 *
 * Spec: .kiro/specs/n5-income-tax-expense/
 * Tasks: 2.4 ~ 2.13
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1~P10。
 * 科目：6801 所得税费用（损益类！取本期发生额）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcPeriodAmount,
  calcSubtotal,
} from '../composables/useN5FormulaEngine'
import {
  calcTaxableIncome,
  calcCurrentTax,
  calcIncomeTaxExpense,
  calcDeferredTaxExpense,
  calcRdSuperDeduction,
} from '../composables/useN5IncomeTaxEngine'
import {
  calcNetAdjustment,
  calcPropertyLossAdjustment,
} from '../composables/useN5TaxAdjustmentEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 安全浮点数生成器（避免NaN/Infinity） */
const arbFloat = fc.float({ min: -1e9, max: 1e9, noNaN: true })

/** 数组生成器（用于P8/P9） */
const arbArray = fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true }), { maxLength: 20 })

// ─── P1: 审定数公式链 ───────────────────────────────────────────────────────

describe('P1: 审定数公式链', () => {
  /**
   * **Validates: Requirements 1.5**
   *
   * ∀ u, a, r: calcAuditedAmount(u, a, r) ≈ u + a + r
   * 审定数 = 未审数 + AJE + RJE
   */
  it('calcAuditedAmount(u, a, r) ≈ u + a + r', () => {
    fc.assert(
      fc.property(arbFloat, arbFloat, arbFloat, (u, a, r) => {
        expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 2)
      }),
      { numRuns: 5 },
    )
  })
})

// ─── P2: 损益类本期发生额 ───────────────────────────────────────────────────

describe('P2: 损益类本期发生额（发生额！）', () => {
  /**
   * **Validates: Requirements 2.3**
   *
   * ∀ d, c: calcPeriodAmount(d, c) ≈ d - c
   * 本期发生额 = 借方发生 - 贷方发生（损益类/费用类）
   */
  it('calcPeriodAmount(d, c) ≈ d - c', () => {
    fc.assert(
      fc.property(arbFloat, arbFloat, (d, c) => {
        expect(calcPeriodAmount(d, c)).toBeCloseTo(d - c, 2)
      }),
      { numRuns: 5 },
    )
  })
})

// ─── P3: 应纳税所得额 ──────────────────────────────────────────────────────

describe('P3: 应纳税所得额=会计利润+调增-调减', () => {
  /**
   * **Validates: Requirements 3.2**
   *
   * ∀ ap, add, ded: calcTaxableIncome(ap, add, ded) ≈ ap + add - ded
   */
  it('calcTaxableIncome(ap, add, ded) ≈ ap + add - ded', () => {
    fc.assert(
      fc.property(arbFloat, arbFloat, arbFloat, (ap, add, ded) => {
        expect(calcTaxableIncome(ap, add, ded)).toBeCloseTo(ap + add - ded, 2)
      }),
      { numRuns: 5 },
    )
  })
})

// ─── P4: 当期所得税 ────────────────────────────────────────────────────────

describe('P4: 当期所得税=应纳税所得额×税率', () => {
  /**
   * **Validates: Requirements 3.3**
   *
   * ∀ ti, rate∈{0.15, 0.25}: calcCurrentTax(ti, rate) ≈ ti × rate
   */
  it('calcCurrentTax(ti, rate) ≈ ti × rate', () => {
    fc.assert(
      fc.property(arbFloat, fc.constantFrom(0.15, 0.25), (ti, rate) => {
        expect(calcCurrentTax(ti, rate)).toBeCloseTo(ti * rate, 2)
      }),
      { numRuns: 5 },
    )
  })
})

// ─── P5: 所得税费用 ────────────────────────────────────────────────────────

describe('P5: 所得税费用=当期+递延', () => {
  /**
   * **Validates: Requirements 3.3**
   *
   * ∀ cur, def: calcIncomeTaxExpense(cur, def) ≈ cur + def
   */
  it('calcIncomeTaxExpense(cur, def) ≈ cur + def', () => {
    fc.assert(
      fc.property(arbFloat, arbFloat, (cur, def) => {
        expect(calcIncomeTaxExpense(cur, def)).toBeCloseTo(cur + def, 2)
      }),
      { numRuns: 5 },
    )
  })
})

// ─── P6: 递延所得税费用 ────────────────────────────────────────────────────

describe('P6: 递延所得税费用=递延税负债增-递延税资产增', () => {
  /**
   * **Validates: Requirements 8.2**
   *
   * ∀ li, ai: calcDeferredTaxExpense(li, ai) ≈ li - ai
   */
  it('calcDeferredTaxExpense(li, ai) ≈ li - ai', () => {
    fc.assert(
      fc.property(arbFloat, arbFloat, (li, ai) => {
        expect(calcDeferredTaxExpense(li, ai)).toBeCloseTo(li - ai, 2)
      }),
      { numRuns: 5 },
    )
  })
})

// ─── P7: 研发费用加计扣除 ──────────────────────────────────────────────────

describe('P7: 研发费用加计扣除=研发费用×加计比例', () => {
  /**
   * **Validates: Requirements 5.2**
   *
   * ∀ rd, rate∈{1.0, 0.75, 0.5}: calcRdSuperDeduction(rd, rate) ≈ rd × rate
   */
  it('calcRdSuperDeduction(rd, rate) ≈ rd × rate', () => {
    fc.assert(
      fc.property(arbFloat, fc.constantFrom(1.0, 0.75, 0.5), (rd, rate) => {
        expect(calcRdSuperDeduction(rd, rate)).toBeCloseTo(rd * rate, 2)
      }),
      { numRuns: 5 },
    )
  })
})

// ─── P8: 纳税调整净额 ─────────────────────────────────────────────────────

describe('P8: 纳税调整净额=Σ调增-Σ调减', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * ∀ adds[], deds[]: calcNetAdjustment(adds, deds) ≈ Σadds - Σdeds
   */
  it('calcNetAdjustment(adds, deds) ≈ Σadds - Σdeds', () => {
    fc.assert(
      fc.property(arbArray, arbArray, (adds, deds) => {
        const expected = adds.reduce((s, v) => s + v, 0) - deds.reduce((s, v) => s + v, 0)
        expect(calcNetAdjustment(adds, deds)).toBeCloseTo(expected, 2)
      }),
      { numRuns: 5 },
    )
  })
})

// ─── P9: 合计行恒等 ────────────────────────────────────────────────────────

describe('P9: 合计行恒等', () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * ∀ arr[]: calcSubtotal(arr) ≈ Σarr
   */
  it('calcSubtotal(arr) ≈ Σarr', () => {
    fc.assert(
      fc.property(arbArray, (arr) => {
        const expected = arr.reduce((s, v) => s + v, 0)
        expect(calcSubtotal(arr)).toBeCloseTo(expected, 2)
      }),
      { numRuns: 5 },
    )
  })
})

// ─── P10: 财产损失纳税调整额 ───────────────────────────────────────────────

describe('P10: 财产损失纳税调整额=账面损失-税前扣除额', () => {
  /**
   * **Validates: Requirements 7.2**
   *
   * ∀ bl, dl: calcPropertyLossAdjustment(bl, dl) ≈ bl - dl
   */
  it('calcPropertyLossAdjustment(bl, dl) ≈ bl - dl', () => {
    fc.assert(
      fc.property(arbFloat, arbFloat, (bl, dl) => {
        expect(calcPropertyLossAdjustment(bl, dl)).toBeCloseTo(bl - dl, 2)
      }),
      { numRuns: 5 },
    )
  })
})
