/**
 * K8 销售费用 — 实质性分析引擎 Property-Based Testing (CP-K8-03, CP-K8-04, CP-K8-05)
 *
 * 覆盖 useK8AnalysisEngine 三个纯函数的数学正确性。
 * 使用 fast-check 验证同比变动率、占收入比、异常波动判断。
 *
 * Spec: .kiro/specs/k8-selling-expenses/design.md → Correctness Properties CP-K8-03~05
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcYoYChange,
  calcRatioToRevenue,
  isAbnormalFluctuation,
} from '../composables/useK8AnalysisEngine'

describe('useK8AnalysisEngine PBT', () => {
  // 安全浮点生成器（避免 NaN/Infinity，32-bit bounds）
  const safeFloat = fc.float({
    noNaN: true,
    noDefaultInfinity: true,
    min: Math.fround(-1e9),
    max: Math.fround(1e9),
  })

  // prior ≠ 0 生成器
  const nonZeroFloat = safeFloat.filter((x) => x !== 0)

  // revenue > 0 生成器
  const positiveFloat = fc.float({
    noNaN: true,
    noDefaultInfinity: true,
    min: Math.fround(0.01),
    max: Math.fround(1e9),
  })

  // threshold > 0 生成器
  const positiveThreshold = fc.float({
    noNaN: true,
    noDefaultInfinity: true,
    min: Math.fround(0.001),
    max: Math.fround(10),
  })

  // ═══ CP-K8-03: 同比变动率 ═══
  // **Validates: Requirements 4.2**
  it('Property CP-K8-03: calcYoYChange(cur, prior) === (cur - prior) / Math.abs(prior)', () => {
    fc.assert(
      fc.property(safeFloat, nonZeroFloat, (cur, prior) => {
        const result = calcYoYChange(cur, prior)
        const expected = (cur - prior) / Math.abs(prior)
        expect(result).toBeCloseTo(expected, 5)
      }),
      { numRuns: 200 },
    )
  })

  // ═══ CP-K8-04: 占收入比 ═══
  // **Validates: Requirements 4.3**
  it('Property CP-K8-04: calcRatioToRevenue(exp, rev) === exp / rev', () => {
    fc.assert(
      fc.property(safeFloat, positiveFloat, (exp, rev) => {
        const result = calcRatioToRevenue(exp, rev)
        const expected = exp / rev
        expect(result).toBeCloseTo(expected, 5)
      }),
      { numRuns: 200 },
    )
  })

  // ═══ CP-K8-05: 异常波动判断 ═══
  // **Validates: Requirements 4.4**
  it('Property CP-K8-05: isAbnormalFluctuation(rate, th) === (Math.abs(rate) > th)', () => {
    fc.assert(
      fc.property(safeFloat, positiveThreshold, (rate, th) => {
        const result = isAbnormalFluctuation(rate, th)
        const expected = Math.abs(rate) > th
        expect(result).toBe(expected)
      }),
      { numRuns: 200 },
    )
  })
})
