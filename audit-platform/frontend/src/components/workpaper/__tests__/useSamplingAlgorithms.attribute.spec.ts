/**
 * 属性抽样（控制测试）权威向量 + 不变量 PBT（voucher-sampling-hardening Task 13）
 *
 * 属性抽样以「偏差率」而非「金额」为度量，复用与 MUS 同源的 CAS 1314 泊松可信赖度
 * 系数表（reliabilityFactor）。本文件锁定：
 * - 固定权威向量：手算样本量 n=ceil(R/gap) 与偏差率上限 CUDR=R(conf,devs)/n。
 * - 不变量 PBT：可容忍偏差率↑→样本量不增；置信度↑→样本量不减；CUDR 上限≥实测偏差率；
 *   精度余量≤0 时样本量为 0；样本量非法时保守返回上限 1、无效。
 *
 * 纯附加（design B.2 / Req13.1-13.3），不改动金额法。
 *
 * Validates: Requirements 13.1, 13.2, 13.3
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  computeAttributeSampleSize,
  evaluateDeviationRate,
  reliabilityFactor,
  DEFAULT_TOLERABLE_DEVIATION_RATE,
} from '../composables/useSamplingAlgorithms'

// ─── 权威向量：computeAttributeSampleSize（n = ceil(R(conf,0) / (tol − exp))）────

describe('权威向量 — computeAttributeSampleSize', () => {
  it('exp=0, tol=0.05, conf=0.95 → ceil(3.00/0.05)=60', () => {
    expect(computeAttributeSampleSize(0, 0.05, 0.95)).toBe(60)
  })

  it('exp=0.01, tol=0.05, conf=0.95 → ceil(3.00/0.04)=75', () => {
    expect(computeAttributeSampleSize(0.01, 0.05, 0.95)).toBe(75)
  })

  it('exp=0, tol=0.10, conf=0.95 → ceil(3.00/0.10)=30', () => {
    expect(computeAttributeSampleSize(0, 0.1, 0.95)).toBe(30)
  })

  it('exp=0, tol=0.05, conf=0.90 → ceil(2.31/0.05)=47', () => {
    // R(0.90, 0) = 2.31（泊松表 90% 基准）
    expect(reliabilityFactor(0.9, 0)).toBe(2.31)
    expect(computeAttributeSampleSize(0, 0.05, 0.9)).toBe(47)
  })

  it('精度余量=0（exp=tol）→ 0（无法推导）', () => {
    expect(computeAttributeSampleSize(0.05, 0.05, 0.95)).toBe(0)
  })

  it('精度余量<0（exp>tol，非法配置）→ 0', () => {
    expect(computeAttributeSampleSize(0.06, 0.05, 0.95)).toBe(0)
  })

  it('偏差率钳制到 [0,1]：负预期按 0，超界可容忍按 1', () => {
    // exp 钳到 0，tol 钳到 1 → gap=1 → ceil(3.00/1)=3
    expect(computeAttributeSampleSize(-0.5, 2, 0.95)).toBe(3)
  })
})

// ─── 权威向量：evaluateDeviationRate（CUDR = R(conf,devs)/n）──────────────────

describe('权威向量 — evaluateDeviationRate', () => {
  it('n=60, devs=0, conf=0.95, tol=0.05 → CUDR=3.00/60=0.05，有效', () => {
    const r = evaluateDeviationRate(60, 0, 0.95, 0.05)
    expect(r.upperDevRate).toBe(0.05)
    expect(r.effective).toBe(true)
  })

  it('n=60, devs=1, conf=0.95, tol=0.05 → CUDR=4.75/60≈0.079167，无效', () => {
    // R(0.95, 1) = 3.00 + 1.75 = 4.75
    expect(reliabilityFactor(0.95, 1)).toBe(4.75)
    const r = evaluateDeviationRate(60, 1, 0.95, 0.05)
    expect(r.upperDevRate).toBe(0.079167)
    expect(r.effective).toBe(false)
  })

  it('n=100, devs=0, conf=0.95, tol=0.05 → CUDR=0.03，有效', () => {
    const r = evaluateDeviationRate(100, 0, 0.95, 0.05)
    expect(r.upperDevRate).toBe(0.03)
    expect(r.effective).toBe(true)
  })

  it('样本量≤0 → 保守返回上限 1、无效', () => {
    expect(evaluateDeviationRate(0, 0, 0.95, 0.05)).toEqual({ upperDevRate: 1, effective: false })
    expect(evaluateDeviationRate(-10, 0, 0.95, 0.05)).toEqual({ upperDevRate: 1, effective: false })
  })

  it('缺省可容忍偏差率使用 DEFAULT_TOLERABLE_DEVIATION_RATE(0.05)', () => {
    expect(DEFAULT_TOLERABLE_DEVIATION_RATE).toBe(0.05)
    const withDefault = evaluateDeviationRate(60, 0, 0.95)
    const explicit = evaluateDeviationRate(60, 0, 0.95, 0.05)
    expect(withDefault).toEqual(explicit)
  })

  it('偏差数钳制到 [0, n]：超样本量按 n 计', () => {
    // devs=999 钳到 n=10 → R(0.95,10)=3.00+10*1.75=20.5 → 20.5/10=2.05 钳到 1
    const r = evaluateDeviationRate(10, 999, 0.95, 0.05)
    expect(r.upperDevRate).toBe(1)
    expect(r.effective).toBe(false)
  })
})

// ─── 不变量 PBT ───────────────────────────────────────────────────────────────

describe('属性抽样不变量（PBT）', () => {
  it('可容忍偏差率↑ → 样本量不增', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 0.02, noNaN: true }),
        fc.double({ min: 0.03, max: 0.15, noNaN: true }),
        fc.double({ min: 0.0001, max: 0.1, noNaN: true }),
        (exp, tolLow, delta) => {
          const conf = 0.95
          const nLow = computeAttributeSampleSize(exp, tolLow, conf)
          const nHigh = computeAttributeSampleSize(exp, tolLow + delta, conf)
          expect(nHigh).toBeLessThanOrEqual(nLow)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('置信度↑ → 样本量不减', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 0.02, noNaN: true }),
        (exp) => {
          const tol = 0.05
          const nLow = computeAttributeSampleSize(exp, tol, 0.8)
          const nHigh = computeAttributeSampleSize(exp, tol, 0.95)
          // R(0.80,0)=1.61 ≤ R(0.95,0)=3.00 → 样本量不减
          expect(nHigh).toBeGreaterThanOrEqual(nLow)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('CUDR 偏差率上限 ≥ 实测偏差率（devs/n）', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 500 }),
        fc.integer({ min: 0, max: 50 }),
        (n, rawDevs) => {
          const devs = Math.min(rawDevs, n)
          const { upperDevRate } = evaluateDeviationRate(n, devs, 0.95, 0.05)
          const observed = devs / n
          // 允许 6 位小数舍入的极小容差
          expect(upperDevRate).toBeGreaterThanOrEqual(Math.round(observed * 1e6) / 1e6 - 1e-6)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('样本量恒为非负整数', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 0.2, noNaN: true }),
        fc.double({ min: 0, max: 0.2, noNaN: true }),
        fc.double({ min: 0.5, max: 0.99, noNaN: true }),
        (exp, tol, conf) => {
          const n = computeAttributeSampleSize(exp, tol, conf)
          expect(Number.isInteger(n)).toBe(true)
          expect(n).toBeGreaterThanOrEqual(0)
        },
      ),
      { numRuns: 20 },
    )
  })
})
