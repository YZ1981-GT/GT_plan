/**
 * useC1SampleEngine 单元测试 + 属性测试
 *
 * Feature: c1-entity-level-control
 * 覆盖 C1-4-4 样本借贷勾稽纯函数 calcSampleBalance（Task 3.2）。
 * 兼顾 Property 4「样本借贷勾稽正确性」的口径验证。
 * **Validates: Requirements 4.4**
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  calcSampleBalance,
  amountsEqual,
  parseNum,
  SAMPLE_BALANCE_TOLERANCE,
  type JeSample,
} from '../useC1SampleEngine'

// ─── 辅助 ───

function mkSample(debit: number, credit: number, i = 0): JeSample {
  return {
    date: `2025-01-${String((i % 28) + 1).padStart(2, '0')}`,
    account: `100${i}`,
    ref: `REF-${i}`,
    desc: `样本分录 ${i}`,
    debit,
    credit,
  }
}

// ─── 单元测试 ───

describe('parseNum', () => {
  it('无效值统一为 0', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum(Infinity)).toBe(0)
    expect(parseNum(-Infinity)).toBe(0)
  })
  it('有效数值/数字串正常解析', () => {
    expect(parseNum(123.45)).toBe(123.45)
    expect(parseNum('678.9')).toBeCloseTo(678.9)
    expect(parseNum(0)).toBe(0)
  })
})

describe('amountsEqual', () => {
  it('容差内视为相等', () => {
    expect(amountsEqual(100, 100)).toBe(true)
    expect(amountsEqual(100, 100 + 1e-9)).toBe(true)
  })
  it('超出容差视为不等', () => {
    expect(amountsEqual(100, 100.5)).toBe(false)
    expect(amountsEqual(0, 1)).toBe(false)
  })
  it('大额累加的浮点漂移仍判为相等（相对容差）', () => {
    expect(amountsEqual(1_000_000.0, 1_000_000.0 + 1e-4)).toBe(true)
  })
})

describe('calcSampleBalance', () => {
  it('空数组返回 0/0/平衡', () => {
    expect(calcSampleBalance([])).toEqual({ debitTotal: 0, creditTotal: 0, balanced: true })
  })

  it('借贷相等 → balanced=true', () => {
    const samples = [mkSample(100, 0, 1), mkSample(0, 100, 2)]
    const r = calcSampleBalance(samples)
    expect(r.debitTotal).toBe(100)
    expect(r.creditTotal).toBe(100)
    expect(r.balanced).toBe(true)
  })

  it('借贷不等 → balanced=false', () => {
    const samples = [mkSample(100, 0, 1), mkSample(0, 60, 2)]
    const r = calcSampleBalance(samples)
    expect(r.debitTotal).toBe(100)
    expect(r.creditTotal).toBe(60)
    expect(r.balanced).toBe(false)
  })

  it('镜像分录（源模板 C1-4-4 口径）借贷平衡', () => {
    // 借 500 贷 500；借 300 贷 200 + 100，整表 Σ借=Σ贷
    const samples = [
      mkSample(500, 0, 1),
      mkSample(0, 500, 2),
      mkSample(300, 0, 3),
      mkSample(0, 200, 4),
      mkSample(0, 100, 5),
    ]
    const r = calcSampleBalance(samples)
    expect(r.debitTotal).toBe(800)
    expect(r.creditTotal).toBe(800)
    expect(r.balanced).toBe(true)
  })

  it('含空/无效金额字段视为 0', () => {
    const samples: JeSample[] = [
      { ...mkSample(0, 0, 1), debit: NaN as unknown as number, credit: 50 },
      { ...mkSample(0, 0, 2), debit: 50, credit: undefined as unknown as number },
    ]
    const r = calcSampleBalance(samples)
    expect(r.debitTotal).toBe(50)
    expect(r.creditTotal).toBe(50)
    expect(r.balanced).toBe(true)
  })

  it('不修改入参（纯函数）', () => {
    const samples = [mkSample(10, 0, 1)]
    const snapshot = JSON.parse(JSON.stringify(samples))
    calcSampleBalance(samples)
    expect(samples).toEqual(snapshot)
  })
})

// ─── 属性测试（Property 4 口径） ───

describe('Property 4: 样本借贷勾稽正确性', () => {
  const financeAmount = fc.float({
    min: Math.fround(-1_000_000),
    max: Math.fround(1_000_000),
    noNaN: true,
    noDefaultInfinity: true,
  })

  const sampleArb: fc.Arbitrary<JeSample> = fc.record({
    date: fc.string(),
    account: fc.string(),
    ref: fc.string(),
    desc: fc.string(),
    debit: financeAmount,
    credit: financeAmount,
  })

  it('debitTotal=Σdebit, creditTotal=Σcredit, balanced=相等判定（容差内）', () => {
    fc.assert(
      fc.property(fc.array(sampleArb, { maxLength: 100 }), (samples) => {
        const r = calcSampleBalance(samples)
        const expectedDebit = samples.reduce((s, x) => s + parseNum(x.debit), 0)
        const expectedCredit = samples.reduce((s, x) => s + parseNum(x.credit), 0)
        expect(r.debitTotal).toBeCloseTo(expectedDebit, 6)
        expect(r.creditTotal).toBeCloseTo(expectedCredit, 6)
        expect(r.balanced).toBe(amountsEqual(r.debitTotal, r.creditTotal, SAMPLE_BALANCE_TOLERANCE))
      }),
      { numRuns: 25 },
    )
  })

  it('借贷完全镜像的样本集恒平衡', () => {
    fc.assert(
      fc.property(fc.array(financeAmount, { maxLength: 50 }), (amounts) => {
        // 每个金额生成一借一贷两行，整表必平衡
        const samples: JeSample[] = []
        amounts.forEach((a, i) => {
          samples.push(mkSample(a, 0, i * 2))
          samples.push(mkSample(0, a, i * 2 + 1))
        })
        expect(calcSampleBalance(samples).balanced).toBe(true)
      }),
      { numRuns: 25 },
    )
  })
})
