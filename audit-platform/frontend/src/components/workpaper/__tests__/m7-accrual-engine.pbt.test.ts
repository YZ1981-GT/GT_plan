/**
 * Property-Based Tests — M7 安全生产费计提引擎（P3~P5）
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Tasks: 2.5 ~ 2.7
 *
 * 使用 fast-check + vitest 验证 Correctness Properties P3, P4, P5。
 * 科目：4201 专项储备（**贷方/权益类！**）
 *
 * 计提引擎覆盖：
 * - P3: 按产量分档计提 Σ(output×rate)
 * - P4: 按营业收入计提 revenue×rate
 * - P5: 计提差异 estimated-booked（正差=少提=审计风险）
 *
 * ⚠️ P5方向说明（m7_conflict_resolution.md 冲突#2）：
 *   xlsx: H=B-G（差异=账面-应计，正差=多计提）
 *   设计: calcAccrualDiff(est, booked)=est-booked（正差=少提=需关注）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAccrualByOutput,
  calcAccrualByRevenue,
  calcAccrualDiff,
} from '../composables/useM7AccrualEngine'

// ─── P3: 按产量分档计提 ─────────────────────────────────────────────────────

describe('P3: 按产量分档计提', () => {
  /**
   * **Validates: Requirements 4.2**
   *
   * ∀ tiers: calcAccrualByOutput(tiers) === Σ(output×rate)
   * 按产量计提 = 各档产量×档位标准求和
   */
  it('calcAccrualByOutput(tiers) === Σ(output×rate)', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            output: fc.float({ min: 0, max: 1e6, noNaN: true }),
            rate: fc.float({ min: 0, max: 100, noNaN: true }),
          }),
          { minLength: 0, maxLength: 10 },
        ),
        (tiers) => {
          const result = calcAccrualByOutput(tiers)
          const expected = tiers.reduce((sum, t) => sum + t.output * t.rate, 0)
          expect(result).toBeCloseTo(expected, 3)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P4: 按营业收入计提 ─────────────────────────────────────────────────────

describe('P4: 按营业收入计提', () => {
  /**
   * **Validates: Requirements 4.3**
   *
   * ∀ rev, rate ∈ float: calcAccrualByRevenue(rev, rate) === rev × rate
   * 按收入计提 = 营业收入 × 计提比例
   */
  it('calcAccrualByRevenue(rev, rate) === rev × rate', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: Math.fround(1e9), noNaN: true }),
        fc.float({ min: 0, max: Math.fround(0.1), noNaN: true }),
        (rev, rate) => {
          const result = calcAccrualByRevenue(rev, rate)
          const expected = rev * rate
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P5: 计提差异 ───────────────────────────────────────────────────────────

describe('P5: 计提差异', () => {
  /**
   * **Validates: Requirements 4.4**
   *
   * ∀ est, booked ∈ float[0, 1e9]: calcAccrualDiff(est, booked) === est - booked
   * 计提差异 = 应计提金额 - 账面计提金额
   * - 正差 → 少计提 = 审计风险点（需补提）
   * - 负差 → 多计提（需冲回）
   *
   * 方向与xlsx相反：xlsx H=B-G（正=多提），设计 est-booked（正=少提）
   */
  it('calcAccrualDiff(est, booked) === est - booked', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (est, booked) => {
          const result = calcAccrualDiff(est, booked)
          const expected = est - booked
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
