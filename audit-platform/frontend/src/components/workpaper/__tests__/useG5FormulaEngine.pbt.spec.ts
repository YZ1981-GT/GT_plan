/**
 * useG5FormulaEngine — Property-Based Testing
 *
 * 18 correctness properties for G5 长期应收款公式引擎。
 * numRuns ≥ 100 per property.
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcNetValue,
  calcReportAmount,
  calcChangeRate,
  calcNetInvestment,
  calcLeaseFinancingIncome,
  calcEndingReceivable,
  calcEndingUnrealizedIncome,
  calcInstallmentFinancingIncome,
  calcSalesAmortizedCost,
  calcImpairmentProvision,
  calcImpairmentAdjustment,
  calcAdjustedBalance,
  calcAdjustedImpairment,
  calcAdjustedBookValue,
  determineStage,
  isDebitCreditBalanced,
  isReversalValid,
  calcAgingTotal,
} from '@/composables/useG5FormulaEngine'

const NUM_RUNS = 100
const fin = fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })
const posFin = fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true })
const rate = fc.double({ min: 0.0001, max: 0.9999, noNaN: true, noDefaultInfinity: true })

describe('useG5FormulaEngine PBT', () => {
  // P1: 借方余额公式
  it('P1: calcDebitBalance(opening, debit, credit) === opening + debit - credit', () => {
    fc.assert(
      fc.property(posFin, posFin, posFin, (opening, debit, credit) => {
        const result = calcDebitBalance(opening, debit, credit)
        expect(result).toBeCloseTo(opening + debit - credit, 6)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P2: 审定数公式
  it('P2: calcAdjustedAmount(unadjusted, aje, rje) === unadjusted + aje + rje', () => {
    fc.assert(
      fc.property(fin, fin, fin, (u, a, r) => {
        expect(calcAdjustedAmount(u, a, r)).toBeCloseTo(u + a + r, 6)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P3: 内含利率法核心
  it('P3: calcLeaseFinancingIncome(netInvestment, implicitRate) === netInvestment × implicitRate', () => {
    fc.assert(
      fc.property(posFin, rate, (ni, ir) => {
        expect(calcLeaseFinancingIncome(ni, ir)).toBeCloseTo(ni * ir, 6)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P4: 实际利率法核心
  it('P4: calcInstallmentFinancingIncome(amortizedCost, effectiveRate) === amortizedCost × effectiveRate', () => {
    fc.assert(
      fc.property(posFin, rate, (cost, er) => {
        expect(calcInstallmentFinancingIncome(cost, er)).toBeCloseTo(cost * er, 6)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P5: 融资租赁期间连续性
  it('P5: calcNetInvestment(calcEndingReceivable(...), calcEndingUnrealizedIncome(...)) === (openRec-coll)-(openUnr-income)', () => {
    fc.assert(
      fc.property(posFin, posFin, posFin, posFin, (openRec, coll, openUnr, income) => {
        const endRec = calcEndingReceivable(openRec, coll)
        const endUnr = calcEndingUnrealizedIncome(openUnr, income)
        const ni = calcNetInvestment(endRec, endUnr)
        const expected = (openRec - coll) - (openUnr - income)
        expect(ni).toBeCloseTo(expected, 6)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P6: 分期销售摊余成本递推
  it('P6: calcSalesAmortizedCost(cost, cost×rate, collection) === cost×(1+rate)-collection', () => {
    fc.assert(
      fc.property(posFin, rate, posFin, (cost, r, coll) => {
        const income = calcInstallmentFinancingIncome(cost, r)
        const result = calcSalesAmortizedCost(cost, income, coll)
        const expected = cost * (1 + r) - coll
        expect(result).toBeCloseTo(expected, 4)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P7: ECL公式链一致性
  it('P7: ECL chain — adjustedBookValue === (①+⑤) - (①×②+⑤×②A+①×(②A-②))', () => {
    fc.assert(
      fc.property(posFin, rate, posFin, rate, (bal, lossRate, balAdj, adjRate) => {
        const provision = calcImpairmentProvision(bal, lossRate)        // ③=①×②
        const impAdj = calcImpairmentAdjustment(balAdj, adjRate, bal, lossRate) // ⑥
        const adjBal = calcAdjustedBalance(bal, balAdj)                 // ⑦=①+⑤
        const adjImp = calcAdjustedImpairment(provision, impAdj)        // ⑧=③+⑥
        const bookValue = calcAdjustedBookValue(adjBal, adjImp)         // ⑨=⑦-⑧
        // Expected: (①+⑤) - (①×② + ⑤×②A + ①×(②A-②))
        const expected = (bal + balAdj) - (bal * lossRate + balAdj * adjRate + bal * (adjRate - lossRate))
        expect(bookValue).toBeCloseTo(expected, 4)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P8: 坏账调整公式展开
  it('P8: calcImpairmentAdjustment === balanceAdj×adjRate + origBalance×(adjRate-origRate)', () => {
    fc.assert(
      fc.property(fin, rate, fin, rate, (ba, ar, ob, or2) => {
        const result = calcImpairmentAdjustment(ba, ar, ob, or2)
        const expected = ba * ar + ob * (ar - or2)
        expect(result).toBeCloseTo(expected, 6)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P9: 三阶段确定性
  it('P9: determineStage output ∈ {Stage1, Stage2, Stage3}', () => {
    fc.assert(
      fc.property(fc.boolean(), fc.boolean(), fc.boolean(), (sig, low, imp) => {
        const result = determineStage(sig, low, imp)
        expect(['Stage1', 'Stage2', 'Stage3']).toContain(result)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P10: Stage3 优先级
  it('P10: hasCreditImpairment=true → Stage3', () => {
    fc.assert(
      fc.property(fc.boolean(), fc.boolean(), (sig, low) => {
        expect(determineStage(sig, low, true)).toBe('Stage3')
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P11: 借贷平衡恒等
  it('P11: isDebitCreditBalanced ↔ |SUM(debits)-SUM(credits)|<0.01', () => {
    fc.assert(
      fc.property(
        fc.array(fin, { minLength: 1, maxLength: 10 }),
        fc.array(fin, { minLength: 1, maxLength: 10 }),
        (debits, credits) => {
          const sumD = debits.reduce((s, v) => s + v, 0)
          const sumC = credits.reduce((s, v) => s + v, 0)
          const expected = Math.abs(sumD - sumC) < 0.01
          expect(isDebitCreditBalanced(debits, credits)).toBe(expected)
        },
      ),
      { numRuns: NUM_RUNS },
    )
  })

  // P12: 转回有效性
  it('P12: isReversalValid ↔ reversal ≤ accumulated', () => {
    fc.assert(
      fc.property(posFin, posFin, (rev, acc) => {
        expect(isReversalValid(rev, acc)).toBe(rev <= acc)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P13: 净值=原值-坏账
  it('P13: calcNetValue === gross - provision', () => {
    fc.assert(
      fc.property(posFin, posFin, (g, p) => {
        expect(calcNetValue(g, p)).toBeCloseTo(g - p, 6)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P14: 报表数=净值-一年内
  it('P14: calcReportAmount === net - oneYear', () => {
    fc.assert(
      fc.property(posFin, posFin, (net, oy) => {
        expect(calcReportAmount(net, oy)).toBeCloseTo(net - oy, 6)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P15: 账龄合计交换律
  it('P15: calcAgingTotal commutative (sum order-independent)', () => {
    fc.assert(
      fc.property(posFin, posFin, posFin, posFin, posFin, posFin, (a, b, c, d, e, f) => {
        const forward = calcAgingTotal(a, b, c, d, e, f)
        const reverse = calcAgingTotal(f, e, d, c, b, a)
        expect(forward).toBeCloseTo(reverse, 6)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P16: parseNum 健壮性
  it('P16: parseNum(null/undefined/NaN/empty) === 0; parseNum(n) === n', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum('  ')).toBe(0)
    expect(parseNum('abc')).toBe(0)
    fc.assert(
      fc.property(fin, (n) => {
        expect(parseNum(n)).toBe(n)
      }),
      { numRuns: NUM_RUNS },
    )
  })

  // P17: 变动率方向性
  it('P17: calcChangeRate directionality', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0.01, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (prior, delta) => {
          const current = prior + delta
          const result = calcChangeRate(prior, current)
          expect(result).not.toBeNull()
          expect(result!).toBeGreaterThan(0)
        },
      ),
      { numRuns: NUM_RUNS },
    )
    // prior=0 → null
    expect(calcChangeRate(0, 100)).toBeNull()
  })

  // P18: 净投资额恒等
  it('P18: calcNetInvestment(receivable, unrealized) === receivable - unrealized', () => {
    fc.assert(
      fc.property(posFin, posFin, (rec, unr) => {
        expect(calcNetInvestment(rec, unr)).toBeCloseTo(rec - unr, 6)
      }),
      { numRuns: NUM_RUNS },
    )
  })
})
