/**
 * K5 预计负债 — Property-Based Tests (CP-K5-01~07)
 *
 * 覆盖 useK5FormulaEngine + useK5ContingencyEngine + useK5BestEstimateEngine 全部核心纯函数。
 * 使用 fast-check 验证数学正确性。
 * 科目：2701预计负债（**贷方/负债类**）
 *
 * ⚠️ 负债类！方向与资产类（期初+借-贷）相反！
 *   负债类期末 = 期初 + 计提(增加) - 转销/冲回(减少)
 *
 * Spec: .kiro/specs/k5-provisions/design.md → Correctness Properties CP-K5-01~07
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
} from '../composables/useK5FormulaEngine'
import { determineRecognition } from '../composables/useK5ContingencyEngine'
import {
  calcRangeMidpoint,
  calcExpectedValue,
  calcWarrantyProvision,
  calcPresentValue,
} from '../composables/useK5BestEstimateEngine'

fc.configureGlobal({ numRuns: 200 })

// 安全浮点生成器（货币范围）
const safeFloat = (min = -1e12, max = 1e12) =>
  fc.double({ min, max, noNaN: true, noDefaultInfinity: true })

const EPSILON = 1e-4

describe('K5 Provisions PBT', () => {
  // ═══ CP-K5-01: 审定数公式链 ═══
  // **Validates: Requirements 10.1**
  describe('Feature: k5-provisions, Property CP-K5-01: 审定数公式链', () => {
    it('CP-K5-01: calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K5-02: 负债类期末余额 ═══
  // **Validates: Requirements 10.2**
  describe('Feature: k5-provisions, Property CP-K5-02: 负债类期末=期初+计提-转销', () => {
    it('CP-K5-02: calcLiabilityEndBalance(b, p, rel) === b + p - rel', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (b, p, rel) => {
          const result = calcLiabilityEndBalance(b, p, rel)
          const expected = b + p - rel
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K5-03: 或有确认决策确定性 ═══
  // **Validates: Requirements 4.1, 4.2, 10.3**
  describe('Feature: k5-provisions, Property CP-K5-03: 或有确认决策确定性', () => {
    it('CP-K5-03: very_likely → recognize', () => {
      expect(determineRecognition('very_likely')).toBe('recognize')
    })

    it('CP-K5-03: possible → disclose', () => {
      expect(determineRecognition('possible')).toBe('disclose')
    })

    it('CP-K5-03: remote → ignore', () => {
      expect(determineRecognition('remote')).toBe('ignore')
    })
  })

  // ═══ CP-K5-04: 区间中值 ═══
  // **Validates: Requirements 5.2, 10.4**
  describe('Feature: k5-provisions, Property CP-K5-04: 区间中值=(上限+下限)/2', () => {
    it('CP-K5-04: calcRangeMidpoint(u, l) === (u + l) / 2', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), (u, l) => {
          const result = calcRangeMidpoint(u, l)
          const expected = (u + l) / 2
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K5-05: 期望值加权 ═══
  // **Validates: Requirements 5.3, 10.5**
  describe('Feature: k5-provisions, Property CP-K5-05: 期望值=Σ(金额×概率)', () => {
    it('CP-K5-05: calcExpectedValue(amounts, probs) === Σ(amounts[i]×probs[i])', () => {
      // 生成等长的 amounts 和 probs 数组，probs 每项为正数且归一化为 sum=1
      const genAmountsAndProbs = fc
        .array(
          fc.tuple(
            fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
            fc.double({ min: 0.01, max: 100, noNaN: true, noDefaultInfinity: true }),
          ),
          { minLength: 1, maxLength: 10 },
        )
        .map((pairs) => {
          const amounts = pairs.map(([a]) => a)
          const rawWeights = pairs.map(([, w]) => w)
          const total = rawWeights.reduce((s, v) => s + v, 0)
          const probs = rawWeights.map((w) => w / total) // normalize to sum=1
          return { amounts, probs }
        })

      fc.assert(
        fc.property(genAmountsAndProbs, ({ amounts, probs }) => {
          const result = calcExpectedValue(amounts, probs)
          let expected = 0
          for (let i = 0; i < amounts.length; i++) {
            expected += amounts[i] * probs[i]
          }
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K5-06: 保修支出 ═══
  // **Validates: Requirements 6.2, 10.6**
  describe('Feature: k5-provisions, Property CP-K5-06: 保修支出=收入×保修率', () => {
    it('CP-K5-06: calcWarrantyProvision(rev, rate) === rev × rate', () => {
      fc.assert(
        fc.property(
          fc.double({ min: 0, max: 1e12, noNaN: true, noDefaultInfinity: true }),
          fc.double({ min: 0, max: 0.5, noNaN: true, noDefaultInfinity: true }),
          (rev, rate) => {
            const result = calcWarrantyProvision(rev, rate)
            const expected = rev * rate
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })

  // ═══ CP-K5-07: 现值折现 ═══
  // **Validates: Requirements 7.2, 7.3, 10.7**
  describe('Feature: k5-provisions, Property CP-K5-07: 现值=future/(1+rate)^years', () => {
    it('CP-K5-07: calcPresentValue(future, rate, years) === future/(1+rate)^years', () => {
      fc.assert(
        fc.property(
          fc.double({ min: 0, max: 1e10, noNaN: true, noDefaultInfinity: true }),
          fc.double({ min: 0.001, max: 1, noNaN: true, noDefaultInfinity: true }),
          fc.integer({ min: 1, max: 50 }),
          (future, rate, years) => {
            const result = calcPresentValue(future, rate, years)
            const expected = future / Math.pow(1 + rate, years)
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('CP-K5-07b: rate<=0 或 years<=0 → 返回 future（不折现兜底）', () => {
      fc.assert(
        fc.property(
          fc.double({ min: 0, max: 1e10, noNaN: true, noDefaultInfinity: true }),
          (future) => {
            // rate=0 → 不折现
            expect(calcPresentValue(future, 0, 5)).toBe(future)
            // rate<0 → 不折现
            expect(calcPresentValue(future, -0.05, 5)).toBe(future)
            // years=0 → 不折现
            expect(calcPresentValue(future, 0.05, 0)).toBe(future)
          },
        ),
      )
    })
  })
})
