/**
 * F1 Property 1 PBT: 借方科目期末余额公式
 *
 * 验证核心公式：
 * - calcEndUnadjustedDebit(priorAudited, debit, credit) === priorAudited + debit - credit
 *
 * 借方科目（资产类 1123 预付账款）期末余额 = 期初审定 + 借方发生 - 贷方发生
 *
 * **Validates: Requirements 1.4, 13.3**
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { calcEndUnadjustedDebit } from '../composables/useF1FormulaEngine'

// ─── Generators ──────────────────────────────────────────────────────────────

const positiveFloatArb = fc.float({ min: 0, max: 1e9, noNaN: true })

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('F1 Property 1: 借方科目期末余额公式', () => {
  /**
   * **Property 1: 期末余额 === 期初审定 + 借方发生 - 贷方发生**
   *
   * 对任意非负 (priorAudited, debit, credit)，
   * calcEndUnadjustedDebit 应返回三者的线性组合。
   *
   * **Validates: Requirements 1.4, 13.3**
   */
  it('calcEndUnadjustedDebit(prior, debit, credit) === prior + debit - credit', () => {
    fc.assert(
      fc.property(
        positiveFloatArb,
        positiveFloatArb,
        positiveFloatArb,
        (priorAudited, debit, credit) => {
          const result = calcEndUnadjustedDebit(priorAudited, debit, credit)
          const expected = priorAudited + debit - credit
          return Math.abs(result - expected) < 1e-6
        },
      ),
      { numRuns: 100 },
    )
  })
})
