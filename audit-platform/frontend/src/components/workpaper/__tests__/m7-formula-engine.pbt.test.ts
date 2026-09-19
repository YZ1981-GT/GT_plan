/**
 * Property-Based Tests — M7 专项储备公式引擎
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Task: 2.4
 *
 * 使用 fast-check + vitest 验证 Correctness Property P2。
 * 科目：4201 专项储备（**贷方/权益类！**）
 *
 * ⚠️ 方向与M3库存股（借方备抵）完全相反！
 *   M7专项储备（贷方权益）：期末 = 期初 + 贷方 - 借方
 *   M3库存股（借方备抵）：  期末 = 期初 + 借方 - 贷方
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcEquityEndBalance } from '../composables/useM7FormulaEngine'

// ─── P2: 权益类期末余额（贷方！） ───────────────────────────────────────────

describe('P2: 权益类贷方期末余额', () => {
  /**
   * **Validates: Requirements 2.4**
   *
   * ∀ b, cr, dr ∈ float[0, 1e9]: calcEquityEndBalance(b, cr, dr) === b + cr - dr
   * 权益类（贷方科目）期末余额 = 期初 + 贷方发生额(计提增加) - 借方发生额(使用减少)
   *
   * 专项储备贷方增加场景：安全生产费计提
   * 专项储备借方减少场景：费用性支出直接冲减 / 资本性支出转固
   *
   * ⚠️ 与M3库存股（借方备抵类）方向相反！
   */
  it('calcEquityEndBalance(b, cr, dr) === b + cr - dr', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (b, cr, dr) => {
          const result = calcEquityEndBalance(b, cr, dr)
          const expected = b + cr - dr
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
