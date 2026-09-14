/**
 * 核心方法学权威向量 + 不变量 PBT（voucher-sampling-hardening Task 2.2 / Task 12）
 *
 * - 固定权威向量：手算 CAS 1314 泊松表用例锁定 reliabilityFactor / computeMusInterval /
 *   computeSampleSize / projectMisstatement / computeUpperMisstatementLimit / deriveSamplingConclusion。
 * - 不变量 PBT：UML 单调不降 / 样本量单调不增 / UML≥projected≥0 / 高值 100%。
 *
 * Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5
 * Properties: Property 3, Property 17, Property 18, Property 19, Property 22
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  reliabilityFactor,
  computeMusInterval,
  computeSampleSize,
  projectMisstatement,
  computeUpperMisstatementLimit,
  deriveSamplingConclusion,
  markHighValueItems,
  type SampledVoucher,
} from '../composables/useSamplingAlgorithms'

function makeSample(over: Partial<SampledVoucher>): SampledVoucher {
  return {
    voucherNo: 'V',
    voucherDate: '2025-01-01',
    summary: null,
    debitAmount: null,
    creditAmount: null,
    accountCode: '1122',
    accountName: null,
    counterpartAccount: null,
    voucherType: null,
    accountingPeriod: null,
    checkResult: 'Y',
    abnormal: false,
    remark: '',
    selected: true,
    phase: 'final',
    editTrail: [],
    ...over,
  }
}

// ─── Property 22：固定权威向量 ───────────────────────────────────────────────

describe('权威向量 — reliabilityFactor / MUS 间隔 / 样本量（Property 22）', () => {
  it('reliabilityFactor(0.95, 0) = 3.0（泊松表 95% 基准）', () => {
    expect(reliabilityFactor(0.95, 0)).toBe(3.0)
  })

  it('reliabilityFactor(0.90, 0) = 2.31', () => {
    expect(reliabilityFactor(0.90, 0)).toBe(2.31)
  })

  it('computeMusInterval("100000",0.95,"0") = "33333.33"（100000/3.0）', () => {
    expect(computeMusInterval('100000', 0.95, '0')).toBe('33333.33')
  })

  it('computeSampleSize("1234567","100000","0",0.95) = 38（ceil(1234567/33333.33)）', () => {
    expect(computeSampleSize('1234567', '100000', '0', 0.95)).toBe(38)
  })

  it('deriveSamplingConclusion 边界：UML==可容忍 → 可接受', () => {
    expect(deriveSamplingConclusion('100000', '100000').accepted).toBe(true)
    expect(deriveSamplingConclusion('100000.01', '100000').accepted).toBe(false)
  })

  it('projectMisstatement 经典比率法权威向量：projected=500 / UML=750', () => {
    const samples = [
      makeSample({ voucherNo: 'A', debitAmount: '1000', actualMisstatement: '100' }),
      makeSample({ voucherNo: 'B', debitAmount: '1000', actualMisstatement: '0' }),
    ]
    const r = projectMisstatement(samples, 'random', '0', '10000', 0.95)
    // ratioProjected = 100/2000*10000 = 500；classic margin=0.5 → incremental=250；UML=750
    expect(r.projected).toBe('500.00')
    expect(r.upperLimit).toBe('750.00')
  })
})

// ─── Property 3：高值必选 ───────────────────────────────────────────────────

describe('高值必选 markHighValueItems（Property 3）', () => {
  it('金额 ≥ interval → isHighValue=true 且 selected=true', () => {
    const items = [
      makeSample({ voucherNo: 'H', debitAmount: '50000', selected: false }),
      makeSample({ voucherNo: 'L', debitAmount: '100', selected: false }),
    ]
    const marked = markHighValueItems(items, '33333.33')
    const h = marked.find(v => v.voucherNo === 'H')!
    const l = marked.find(v => v.voucherNo === 'L')!
    expect(h.isHighValue).toBe(true)
    expect(h.selected).toBe(true)
    expect(l.isHighValue).toBe(false)
  })

  it('PBT：金额 ≥ interval 的项必被标记且选中', () => {
    fc.assert(
      fc.property(
        fc.array(fc.integer({ min: 0, max: 200000 }), { minLength: 1, maxLength: 20 }),
        (amounts) => {
          const interval = '50000'
          const items = amounts.map((a, i) =>
            makeSample({ voucherNo: `V${i}`, debitAmount: String(a), selected: false }),
          )
          const marked = markHighValueItems(items, interval)
          for (const m of marked) {
            const amt = Number(m.debitAmount)
            if (amt >= 50000) {
              expect(m.isHighValue).toBe(true)
              expect(m.selected).toBe(true)
            }
          }
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ─── Property 19：UML ≥ projected ≥ 0 ───────────────────────────────────────

describe('错报上限下界（Property 19）', () => {
  it('PBT：任意实际错报下恒有 UML ≥ projected ≥ 0（经典与 MUS）', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            book: fc.integer({ min: 1, max: 100000 }),
            err: fc.integer({ min: 0, max: 100000 }),
            high: fc.boolean(),
          }),
          { minLength: 1, maxLength: 15 },
        ),
        fc.constantFrom('random', 'mus'),
        (rows, method) => {
          const samples = rows.map((r, i) =>
            makeSample({
              voucherNo: `V${i}`,
              debitAmount: String(r.book),
              actualMisstatement: String(Math.min(r.err, r.book)),
              isHighValue: r.high,
            }),
          )
          const r = projectMisstatement(samples, method as any, '20000', '500000', 0.95)
          const projected = parseFloat(r.projected)
          const uml = parseFloat(r.upperLimit)
          expect(projected).toBeGreaterThanOrEqual(0)
          expect(uml).toBeGreaterThanOrEqual(projected - 1e-6)
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ─── Property 17：UML 单调不降 ──────────────────────────────────────────────

describe('UML 随错报单调不降（Property 17）', () => {
  it('PBT：增大某样本实际错报，UML 不下降（经典比率法）', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 5000 }),
        fc.integer({ min: 0, max: 5000 }),
        (base, delta) => {
          const mk = (err: number) => [
            makeSample({ voucherNo: 'A', debitAmount: '10000', actualMisstatement: String(err) }),
            makeSample({ voucherNo: 'B', debitAmount: '10000', actualMisstatement: '0' }),
          ]
          const low = projectMisstatement(mk(base), 'random', '0', '100000', 0.95)
          const high = projectMisstatement(mk(base + delta), 'random', '0', '100000', 0.95)
          expect(parseFloat(high.upperLimit)).toBeGreaterThanOrEqual(
            parseFloat(low.upperLimit) - 1e-6,
          )
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ─── Property 18：样本量随可容忍错报单调不增 ────────────────────────────────

describe('建议样本量随可容忍错报单调不增（Property 18）', () => {
  it('PBT：可容忍错报增大，computeSampleSize 不增加', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 10000, max: 100000 }),
        fc.integer({ min: 1, max: 100000 }),
        (tol, delta) => {
          const pop = '5000000'
          const small = computeSampleSize(pop, String(tol), '0', 0.95)
          const large = computeSampleSize(pop, String(tol + delta), '0', 0.95)
          expect(large).toBeLessThanOrEqual(small)
        },
      ),
      { numRuns: 20 },
    )
  })
})
