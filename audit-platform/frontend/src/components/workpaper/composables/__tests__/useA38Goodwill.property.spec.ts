/**
 * Property-Based Tests — A3-8 商誉减值测试公式引擎
 *
 * Spec: .kiro/specs/a3-8-goodwill-impairment/ Task 6
 * 使用 fast-check + vitest 验证公式 correctness properties。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcTotal, calcDiff, calcImpairment, calcWacc, calcKe,
  discountFactor, calcDcfPv, calcRecoverableAmount, allocateImpairment,
  type A38ImpairmentRow, type A38AllocationRow, type A38RecoverableData,
} from '../useA38Goodwill'

const arbMoney = fc.oneof(fc.constant(null), fc.double({ min: -1e6, max: 1e9, noNaN: true }))
const arbPosMoney = fc.double({ min: 0, max: 1e9, noNaN: true })
const arbRate = fc.double({ min: 0, max: 0.99, noNaN: true })

function mkRow(a: number | null, b1: number | null, b2: number | null, rec: number | null): A38ImpairmentRow {
  return { id: 'r1', name: '', carrying_a: a, goodwill_b1: b1, minority_b2: b2, recoverable: rec, reason: '', remark: '' }
}

describe('Feature: a3-8-goodwill-impairment, Property 1: 合计=A+B1+B2', () => {
  it('total equals sum of three carrying components (null→0)', () => {
    fc.assert(
      fc.property(arbMoney, arbMoney, arbMoney, (a, b1, b2) => {
        const expected = (a ?? 0) + (b1 ?? 0) + (b2 ?? 0)
        expect(calcTotal(mkRow(a, b1, b2, null))).toBeCloseTo(expected, 6)
      }),
      { numRuns: 50 },
    )
  })
})

describe('Feature: a3-8-goodwill-impairment, Property 2: 减值准备非负且=max(diff,0)', () => {
  it('impairment is non-negative and equals max(diff, 0)', () => {
    fc.assert(
      fc.property(arbMoney, arbMoney, arbMoney, arbMoney, (a, b1, b2, rec) => {
        const row = mkRow(a, b1, b2, rec)
        const imp = calcImpairment(row)
        expect(imp).toBeGreaterThanOrEqual(0)
        expect(imp).toBeCloseTo(Math.max(calcDiff(row), 0), 6)
      }),
      { numRuns: 50 },
    )
  })

  it('diff = total - recoverable', () => {
    fc.assert(
      fc.property(arbMoney, arbMoney, arbMoney, arbMoney, (a, b1, b2, rec) => {
        const row = mkRow(a, b1, b2, rec)
        expect(calcDiff(row)).toBeCloseTo(calcTotal(row) - (rec ?? 0), 6)
      }),
      { numRuns: 50 },
    )
  })
})

describe('Feature: a3-8-goodwill-impairment, Property 3: WACC 边界 D+E=0→null', () => {
  it('WACC returns null when D+E=0', () => {
    const w: A38RecoverableData['wacc'] = {
      tax_rate: 0.25, debt_d: 0, equity_e: 0, cost_debt_kd: 0.05, rf: 0.03, beta: 1, rm: 0.08,
    }
    expect(calcWacc(w)).toBeNull()
  })

  it('Ke = Rf + β(Rm-Rf) (CAPM)', () => {
    fc.assert(
      fc.property(arbRate, fc.double({ min: 0, max: 3, noNaN: true }), arbRate, (rf, beta, rm) => {
        const w: A38RecoverableData['wacc'] = { tax_rate: null, debt_d: null, equity_e: null, cost_debt_kd: null, rf, beta, rm }
        expect(calcKe(w)).toBeCloseTo(rf + beta * (rm - rf), 6)
      }),
      { numRuns: 50 },
    )
  })

  it('WACC within [min(Kd_at,Ke), max(Kd_at,Ke)] when D,E>0', () => {
    fc.assert(
      fc.property(arbPosMoney, arbPosMoney, arbRate, arbRate, fc.double({ min: 0, max: 2, noNaN: true }), arbRate, arbRate,
        (D, E, tax, kd, beta, rf, rm) => {
          fc.pre(D > 0 && E > 0)
          const w: A38RecoverableData['wacc'] = { tax_rate: tax, debt_d: D, equity_e: E, cost_debt_kd: kd, rf, beta, rm }
          const wacc = calcWacc(w)!
          const ke = rf + beta * (rm - rf)
          const kdAfterTax = kd * (1 - tax)
          const lo = Math.min(ke, kdAfterTax)
          const hi = Math.max(ke, kdAfterTax)
          expect(wacc).toBeGreaterThanOrEqual(lo - 1e-6)
          expect(wacc).toBeLessThanOrEqual(hi + 1e-6)
        }),
      { numRuns: 50 },
    )
  })
})

describe('Feature: a3-8-goodwill-impairment, Property 4: 折现系数随年份递减', () => {
  it('discount factor strictly decreases with year for positive rate', () => {
    fc.assert(
      fc.property(fc.double({ min: 0.001, max: 0.99, noNaN: true }), (r) => {
        const f1 = discountFactor(r, 1)!
        const f2 = discountFactor(r, 2)!
        const f3 = discountFactor(r, 3)!
        expect(f1).toBeGreaterThan(f2)
        expect(f2).toBeGreaterThan(f3)
        expect(f1).toBeLessThanOrEqual(1)
      }),
      { numRuns: 50 },
    )
  })

  it('null rate → null factor', () => {
    expect(discountFactor(null, 1)).toBeNull()
  })
})

describe('Feature: a3-8-goodwill-impairment, Property 5: 减值损失分摊总和守恒', () => {
  const arbAllocRows = fc.array(
    fc.record({
      id: fc.string({ minLength: 1, maxLength: 8 }),
      asset_type: fc.constantFrom('流动资产', '固定资产', '无形资产', '商誉'),
      carrying: arbPosMoney,
      minority: fc.constant(null),
      recoverable: fc.constant(null),
    }),
    { minLength: 1, maxLength: 6 },
  ).map((rows) => rows.map((r, i) => ({ ...r, id: `al-${i}` })) as A38AllocationRow[])

  it('Σ(alloc_first+alloc_second) === loss when other-asset carrying exists or goodwill covers', () => {
    fc.assert(
      fc.property(arbAllocRows, arbPosMoney, (rows, loss) => {
        const result = allocateImpairment(rows, loss)
        const sum = result.reduce((s, x) => s + x.alloc_first + x.alloc_second, 0)
        const goodwill = rows.find((r) => r.asset_type === '商誉')
        const others = rows.filter((r) => r.asset_type !== '商誉')
        const gwCarry = goodwill ? (goodwill.carrying ?? 0) : 0
        const otherCarry = others.reduce((s, r) => s + (r.carrying ?? 0), 0)
        // 可分摊上限 = 商誉账面 + (若有其他资产则无限) ；otherCarry>0 时可全分摊
        if (otherCarry > 0 || loss <= gwCarry) {
          expect(sum).toBeCloseTo(loss, 4)
        } else {
          // 无其他资产且 loss>商誉 → 只能冲到商誉账面
          expect(sum).toBeCloseTo(gwCarry, 4)
        }
      }),
      { numRuns: 50 },
    )
  })

  it('alloc_first never exceeds goodwill carrying', () => {
    fc.assert(
      fc.property(arbAllocRows, arbPosMoney, (rows, loss) => {
        const result = allocateImpairment(rows, loss)
        const goodwill = rows.find((r) => r.asset_type === '商誉')
        if (goodwill) {
          const g = result.find((x) => x.id === goodwill.id)!
          expect(g.alloc_first).toBeLessThanOrEqual((goodwill.carrying ?? 0) + 1e-6)
        }
      }),
      { numRuns: 50 },
    )
  })

  it('loss<=0 → all allocations zero', () => {
    fc.assert(
      fc.property(arbAllocRows, (rows) => {
        const result = allocateImpairment(rows, 0)
        expect(result.every((x) => x.alloc_first === 0 && x.alloc_second === 0)).toBe(true)
      }),
      { numRuns: 30 },
    )
  })
})

describe('Feature: a3-8-goodwill-impairment, Property 6: 可收回金额=孰高', () => {
  it('recoverable amount = max(fairValueNet, dcfTotal), picks correct path', () => {
    fc.assert(
      fc.property(
        fc.array(fc.record({ fair_value: arbPosMoney, disposal_cost: arbPosMoney }), { minLength: 1, maxLength: 3 }),
        fc.double({ min: 0.01, max: 0.5, noNaN: true }),
        fc.array(arbPosMoney, { minLength: 1, maxLength: 5 }),
        (fvRows, rate, cfs) => {
          const rec: A38RecoverableData = {
            fair_value_rows: fvRows.map((r, i) => ({ id: `fv-${i}`, name: '', fair_value: r.fair_value, disposal_cost: r.disposal_cost })),
            dcf: { cash_flows: cfs, base_cash_flow: null, perpetual_growth: null, discount_rate: rate },
            wacc: { tax_rate: null, debt_d: null, equity_e: null, cost_debt_kd: null, rf: null, beta: null, rm: null },
          }
          const fv = rec.fair_value_rows.reduce((s, r) => s + ((r.fair_value ?? 0) - (r.disposal_cost ?? 0)), 0)
          const dcfPv = calcDcfPv(rec.dcf) ?? 0
          const res = calcRecoverableAmount(rec)
          // 终值为 null（无永续增长），dcfTotal = dcfPv
          expect(res.value).toBeCloseTo(Math.max(fv, dcfPv), 4)
          expect(res.path).toBe(fv >= dcfPv ? 'fair_value' : 'dcf')
        }),
      { numRuns: 50 },
    )
  })
})
