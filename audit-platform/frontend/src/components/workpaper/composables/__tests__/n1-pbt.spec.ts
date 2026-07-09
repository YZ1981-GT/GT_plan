/**
 * Property-Based Tests — N1 递延所得税资产公式引擎 + 税务引擎 + 亏损确认引擎
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Tasks: 2.4 ~ 2.10
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P1~P7。
 * 科目：1811 递延所得税资产（借方/资产类）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcSubtotal,
} from '../useN1FormulaEngine'
import {
  calcTemporaryDifference,
  calcDeferredTax,
} from '../useN1DeferredTaxEngine'
import {
  calcUnrecoveredLoss,
  calcRecognizableAsset,
} from '../useN1LossCompensationEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 安全浮点数生成器（避免NaN/Infinity/极端浮点精度问题） */
const arbSafeFloat = fc.integer({ min: -1_000_000_00, max: 1_000_000_00 }).map(n => n / 100)

/** 非负安全浮点 */
const arbNonNegFloat = fc.integer({ min: 0, max: 1_000_000_00 }).map(n => n / 100)

/** 正浮点（>0） */
const arbPositiveFloat = fc.integer({ min: 1, max: 1_000_000_00 }).map(n => n / 100)

/** 税率生成器 rate∈[0, 0.25] */
const arbTaxRate = fc.integer({ min: 0, max: 2500 }).map(n => n / 10000)

/** 正税率 rate∈(0, 0.25] */
const arbPositiveTaxRate = fc.integer({ min: 1, max: 2500 }).map(n => n / 10000)

// ─── P1: 审定数公式链 ───────────────────────────────────────────────────────

describe('P1: 审定数公式链', () => {
  /**
   * **Validates: Requirements 2.3**
   *
   * ∀ u, a, r: calcAuditedAmount(u, a, r) === u + a + r
   * 审定数 = 未审数 + 审计调整 + 重分类调整
   */
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        arbSafeFloat,
        arbSafeFloat,
        arbSafeFloat,
        (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P2: 资产类期末余额（期初+借-贷） ──────────────────────────────────────

describe('P2: 资产类期末余额（期初+借-贷）', () => {
  /**
   * **Validates: Requirements 2.4, 8.1**
   *
   * ∀ b, d, c: calcAssetEndBalance(b, d, c) === b + d - c
   * 资产类（借方科目）期末余额 = 期初 + 本期借方 - 本期贷方
   */
  it('calcAssetEndBalance(b, d, c) === b + d - c', () => {
    fc.assert(
      fc.property(
        arbSafeFloat,
        arbSafeFloat,
        arbSafeFloat,
        (b, d, c) => {
          const result = calcAssetEndBalance(b, d, c)
          const expected = b + d - c
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P3: 暂时性差异（账面-计税基础） ───────────────────────────────────────

describe('P3: 暂时性差异（账面-计税基础）', () => {
  /**
   * **Validates: Requirements 3.2, 4.2**
   *
   * ∀ bv, tb: calcTemporaryDifference(bv, tb) === bv - tb
   * 暂时性差异 = 账面价值 - 计税基础
   */
  it('calcTemporaryDifference(bv, tb) === bv - tb', () => {
    fc.assert(
      fc.property(
        arbSafeFloat,
        arbSafeFloat,
        (bv, tb) => {
          const result = calcTemporaryDifference(bv, tb)
          const expected = bv - tb
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P4: 递延所得税=差异×税率 ───────────────────────────────────────────────

describe('P4: 递延所得税=差异×税率', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * ∀ diff, rate∈[0,0.25]: calcDeferredTax(diff, rate) === diff × rate
   * 递延所得税 = 暂时性差异 × 适用税率
   */
  it('calcDeferredTax(diff, rate) === diff × rate', () => {
    fc.assert(
      fc.property(
        arbSafeFloat,
        arbTaxRate,
        (diff, rate) => {
          const result = calcDeferredTax(diff, rate)
          const expected = diff * rate
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P5: 合计行恒等 ────────────────────────────────────────────────────────

describe('P5: 合计行恒等', () => {
  /**
   * **Validates: Requirements 2.5**
   *
   * ∀ arr (number[]): calcSubtotal(arr) === arr.reduce((a, b) => a + b, 0)
   * 合计行 = Σ各项金额
   */
  it('calcSubtotal(arr) === Σarr', () => {
    fc.assert(
      fc.property(
        fc.array(arbSafeFloat, { minLength: 0, maxLength: 50 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(result).toBeCloseTo(expected, 8)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P6: 未弥补亏损 ────────────────────────────────────────────────────────

describe('P6: 未弥补亏损', () => {
  /**
   * **Validates: Requirements 5.2**
   *
   * ∀ loss≥0, rec≥0: calcUnrecoveredLoss(loss, rec) === max(0, loss - rec)
   * 未弥补亏损 = max(0, 亏损金额 - 已弥补金额)
   * 注：函数内部对输入 clamp 到非负，结果也 clamp 到非负
   */
  it('calcUnrecoveredLoss(loss, rec) === max(0, loss - rec) for non-negative inputs', () => {
    fc.assert(
      fc.property(
        arbNonNegFloat,
        arbNonNegFloat,
        (loss, rec) => {
          const result = calcUnrecoveredLoss(loss, rec)
          const expected = Math.max(0, loss - rec)
          expect(result).toBeCloseTo(expected, 10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── P7: 可确认递延税资产（谨慎性限额） ─────────────────────────────────────

describe('P7: 可确认递延税资产（min限额×税率）', () => {
  /**
   * **Validates: Requirements 5.2**
   *
   * ∀ unrec>0, fti>0, rate∈(0,0.25]:
   *   calcRecognizableAsset(unrec, fti, rate) === min(unrec, fti) × rate
   * 可确认递延税资产 = min(未弥补亏损, 预计未来应纳税所得额) × 适用税率
   */
  it('calcRecognizableAsset(unrec, fti, rate) === min(unrec, fti) × rate', () => {
    fc.assert(
      fc.property(
        arbPositiveFloat,
        arbPositiveFloat,
        arbPositiveTaxRate,
        (unrec, fti, rate) => {
          const result = calcRecognizableAsset(unrec, fti, rate)
          const expected = Math.min(unrec, fti) * rate
          expect(Math.abs(result - expected)).toBeLessThan(1e-10)
        },
      ),
      { numRuns: 100 },
    )
  })
})
