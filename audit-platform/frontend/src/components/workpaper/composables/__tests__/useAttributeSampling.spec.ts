/**
 * 属性抽样（控制测试）纯函数 — 单元测试 + 属性测试（PBT）
 *
 * Spec: .kiro/specs/voucher-check-sampling-integration/
 * Task: 14（可选/后续，design B.2）
 *
 * 覆盖 computeAttributeSampleSize / evaluateDeviationRate：
 * - Property A1 样本量单调性：可容忍偏差率 ↑ → 样本量不增；置信度 ↑ → 样本量不减
 * - Property A2 偏差率上限下界：upperDevRate ≥ 实测偏差率(=deviations/sampleSize)
 * - Property A3 有效性判定：effective ⇔ upperDevRate ≤ 可容忍偏差率
 *
 * 使用 fast-check + vitest，numRuns≈5。
 *
 * **Validates: Requirements 23.1, 23.2, 23.3**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  computeAttributeSampleSize,
  evaluateDeviationRate,
  DEFAULT_TOLERABLE_DEVIATION_RATE,
  CAS1314_RELIABILITY_TABLE,
} from '../useSamplingAlgorithms'

const RUNS = { numRuns: 5 }

/** 置信度取自 CAS1314 表的精确档位，避免最近邻映射歧义 */
const arbConfidence: fc.Arbitrary<number> = fc.constantFrom(
  ...CAS1314_RELIABILITY_TABLE.map((r) => r.confidence),
)

/** 偏差率生成器（以千分比整数派生，规避 fast-check 32-bit float 约束） */
function rateArb(minPermille: number, maxPermille: number): fc.Arbitrary<number> {
  return fc.integer({ min: minPermille, max: maxPermille }).map((n) => n / 1000)
}

// ─── Unit Tests ──────────────────────────────────────────────────────────────

describe('computeAttributeSampleSize（属性抽样样本量）', () => {
  it('典型控制测试参数返回正整数样本量', () => {
    // 预期偏差率 1%、可容忍偏差率 5%、置信度 95% → R(0.95,0)=3.0 / 0.04 = 75
    const n = computeAttributeSampleSize(0.01, 0.05, 0.95)
    expect(n).toBe(75)
  })

  it('预期偏差率为 0 时 n = ceil(R / 可容忍)', () => {
    // 3.0 / 0.05 = 60
    expect(computeAttributeSampleSize(0, 0.05, 0.95)).toBe(60)
  })

  it('精度余量 ≤ 0（预期 ≥ 可容忍）返回 0', () => {
    expect(computeAttributeSampleSize(0.05, 0.05, 0.95)).toBe(0)
    expect(computeAttributeSampleSize(0.08, 0.05, 0.95)).toBe(0)
  })

  it('偏差率越界被钳制到 [0,1]', () => {
    // expected 负数按 0，tolerable 超 1 按 1 → 3.0 / 1 = 3
    expect(computeAttributeSampleSize(-0.5, 2, 0.95)).toBe(3)
  })

  it('置信度越高样本量越大（90% < 95% < 99%）', () => {
    const n90 = computeAttributeSampleSize(0.01, 0.05, 0.9)
    const n95 = computeAttributeSampleSize(0.01, 0.05, 0.95)
    const n99 = computeAttributeSampleSize(0.01, 0.05, 0.99)
    expect(n90).toBeLessThan(n95)
    expect(n95).toBeLessThan(n99)
  })
})

describe('evaluateDeviationRate（偏差率评价）', () => {
  it('零偏差时上限 = R(置信度,0)/样本量，且有效', () => {
    // n=60, deviations=0, 95% → 3.0/60 = 0.05 ≤ 0.05(默认) → effective
    const r = evaluateDeviationRate(60, 0, 0.95)
    expect(r.upperDevRate).toBeCloseTo(0.05, 6)
    expect(r.effective).toBe(true)
  })

  it('偏差数增加抬高偏差率上限，可能判定为无效', () => {
    const r = evaluateDeviationRate(60, 3, 0.95, 0.05)
    // R(0.95,3) = 3.0 + 3*1.75 = 8.25 → 8.25/60 = 0.1375 > 0.05 → 无效
    expect(r.upperDevRate).toBeCloseTo(0.1375, 6)
    expect(r.effective).toBe(false)
  })

  it('样本量非法返回上限 1、无效', () => {
    expect(evaluateDeviationRate(0, 0, 0.95)).toEqual({ upperDevRate: 1, effective: false })
    expect(evaluateDeviationRate(-5, 2, 0.95)).toEqual({ upperDevRate: 1, effective: false })
  })

  it('偏差数被钳制到 [0, sampleSize]', () => {
    // deviations 超过 sampleSize → 按 sampleSize 计
    const r = evaluateDeviationRate(10, 999, 0.95)
    const rClamped = evaluateDeviationRate(10, 10, 0.95)
    expect(r.upperDevRate).toBe(rClamped.upperDevRate)
  })

  it('默认可容忍偏差率为 5%', () => {
    expect(DEFAULT_TOLERABLE_DEVIATION_RATE).toBe(0.05)
  })
})

// ─── Property-Based Tests ────────────────────────────────────────────────────

describe('属性抽样 PBT', () => {
  // Property A1a：可容忍偏差率 ↑ → 样本量不增（更小/相等）
  it('Property A1a — 可容忍偏差率越高样本量不增', () => {
    fc.assert(
      fc.property(
        rateArb(0, 20),      // expected 0~0.02
        rateArb(30, 60),     // tolerable 低档 0.03~0.06
        rateArb(70, 150),    // tolerable 高档 0.07~0.15
        arbConfidence,
        (expected, tolLow, tolHigh, cl) => {
          const nLow = computeAttributeSampleSize(expected, tolLow, cl)
          const nHigh = computeAttributeSampleSize(expected, tolHigh, cl)
          // 高可容忍偏差率对应样本量不大于低可容忍偏差率
          expect(nHigh).toBeLessThanOrEqual(nLow)
        },
      ),
      RUNS,
    )
  })

  // Property A1b：置信度 ↑ → 样本量不减（更大/相等）
  it('Property A1b — 置信度越高样本量不减', () => {
    fc.assert(
      fc.property(
        rateArb(0, 20),      // expected 0~0.02
        rateArb(40, 100),    // tolerable 0.04~0.10
        (expected, tolerable) => {
          const n90 = computeAttributeSampleSize(expected, tolerable, 0.9)
          const n95 = computeAttributeSampleSize(expected, tolerable, 0.95)
          const n99 = computeAttributeSampleSize(expected, tolerable, 0.99)
          expect(n95).toBeGreaterThanOrEqual(n90)
          expect(n99).toBeGreaterThanOrEqual(n95)
        },
      ),
      RUNS,
    )
  })

  // Property A2：偏差率上限 ≥ 实测偏差率
  it('Property A2 — 偏差率上限不低于样本实测偏差率', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 300 }),   // sampleSize
        fc.integer({ min: 0, max: 300 }),   // deviations
        arbConfidence,
        (sampleSize, deviations, cl) => {
          const { upperDevRate } = evaluateDeviationRate(sampleSize, deviations, cl)
          const observed = Math.min(deviations, sampleSize) / sampleSize
          expect(upperDevRate).toBeGreaterThanOrEqual(observed - 1e-9)
        },
      ),
      RUNS,
    )
  })

  // Property A3：有效性判定 ⇔ upperDevRate ≤ 可容忍偏差率
  it('Property A3 — effective 当且仅当上限 ≤ 可容忍偏差率', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 300 }),
        fc.integer({ min: 0, max: 300 }),
        arbConfidence,
        rateArb(10, 200),    // tolerable 0.01~0.20
        (sampleSize, deviations, cl, tolerable) => {
          const { upperDevRate, effective } = evaluateDeviationRate(
            sampleSize, deviations, cl, tolerable,
          )
          expect(effective).toBe(upperDevRate <= tolerable)
        },
      ),
      RUNS,
    )
  })
})
