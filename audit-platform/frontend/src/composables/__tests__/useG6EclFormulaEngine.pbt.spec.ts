/**
 * Property-Based Tests — G6 其他债权投资(ECL组) 公式引擎
 *
 * Spec: .kiro/specs/g6-other-bond-investment-ecl/ Tasks 1.2 ~ 1.6, 5.3
 * Framework: vitest + fast-check, numRuns ≥ 100
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcImpairmentProvision,
  calcImpairmentAdjustment,
  calcAdjustedBalance,
  calcAdjustedImpairment,
  calcAdjustedBookValue,
  determineStage,
  isDebitCreditBalanced,
} from '../useG6EclFormulaEngine'
import { useG6EclStageClassification } from '../useG6EclStageClassification'
import type { ColumnarSourceData } from '../useG6EclStageClassification'

// ═══ Generators ═══
const amount = () => fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })
const rate = () => fc.float({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true })
const amountArray = () => fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }), { minLength: 0, maxLength: 50 })

// ═══ Helper: round to 2 decimal places ═══
function round2(n: number): number {
  return Math.round(n * 100) / 100
}

// ═══════════════════════════════════════════════════════════════════
// Feature: g6-other-bond-investment-ecl, Property 1: ECL公式链一致性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-ecl, Property 1: ECL公式链一致性', () => {
  /**
   * **Validates: Requirements 3.2, 6.1**
   *
   * 验证完整公式链: ⑨ = (①+⑤) - (①×② + ⑤×②A + ①×(②A-②))
   * 即 calcAdjustedBookValue(⑦, ⑧) 其中 ⑦=①+⑤, ⑧=③+⑥
   */
  it('full chain ⑨ = (①+⑤) - (①×② + ⑤×②A + ①×(②A-②)) holds for all inputs', () => {
    fc.assert(
      fc.property(
        amount(), // ① origBalance (摊余成本余额)
        rate(),   // ② origRate (预期信用损失率)
        amount(), // ⑤ balanceAdj (余额调整)
        rate(),   // ②A adjRate (调整后信用损失率)
        (origBal, origRate, balAdj, adjRate) => {
          // Compute through the chain
          const provision = calcImpairmentProvision(origBal, origRate)       // ③ = ① × ②
          const impAdj = calcImpairmentAdjustment(balAdj, adjRate, origBal, origRate) // ⑥
          const adjBalance = calcAdjustedBalance(origBal, balAdj)            // ⑦ = ① + ⑤
          const adjImpairment = calcAdjustedImpairment(provision, impAdj)    // ⑧ = ③ + ⑥
          const adjBookValue = calcAdjustedBookValue(adjBalance, adjImpairment) // ⑨ = ⑦ - ⑧

          // Expected: ⑨ = (①+⑤) - (①×② + ⑤×②A + ①×(②A-②))
          const expected = round2(
            (origBal + balAdj) - (origBal * origRate + balAdj * adjRate + origBal * (adjRate - origRate)),
          )

          // Allow for floating point rounding differences (chain applies round2 at each step)
          expect(Math.abs(adjBookValue - expected)).toBeLessThanOrEqual(0.02)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// Feature: g6-other-bond-investment-ecl, Property 2: 三阶段确定性
// Feature: g6-other-bond-investment-ecl, Property 3: Stage3优先级
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-ecl, Property 2+3: 三阶段确定性与Stage3优先级', () => {
  /**
   * **Validates: Requirements 2.3, 6.1**
   *
   * Property 2: determineStage输出∈{Stage1, Stage2, Stage3}
   * Property 3: hasCreditImpairment → Stage3 (highest priority)
   */
  it('P2: determineStage always returns a valid stage ∈ {Stage1, Stage2, Stage3}', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        fc.boolean(),
        fc.boolean(),
        (sigIncrease, lowRisk, creditImpaired) => {
          const result = determineStage(sigIncrease, lowRisk, creditImpaired)
          expect(['Stage1', 'Stage2', 'Stage3']).toContain(result)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('P3: hasCreditImpairment=true → Stage3 always (highest priority)', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        fc.boolean(),
        (sigIncrease, lowRisk) => {
          expect(determineStage(sigIncrease, lowRisk, true)).toBe('Stage3')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('P3 corollary: hasSignificantIncrease=true, !creditImpaired → Stage2', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        (lowRisk) => {
          expect(determineStage(true, lowRisk, false)).toBe('Stage2')
        },
      ),
      { numRuns: 100 },
    )
  })

  it('P3 corollary: !significantIncrease, !creditImpaired → Stage1', () => {
    fc.assert(
      fc.property(
        fc.boolean(),
        (lowRisk) => {
          expect(determineStage(false, lowRisk, false)).toBe('Stage1')
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// Feature: g6-other-bond-investment-ecl, Property 4: 坏账调整展开式
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-ecl, Property 4: 坏账调整展开式', () => {
  /**
   * **Validates: Requirements 3.2, 6.1**
   *
   * calcImpairmentAdjustment(ba, ar, ob, or) = round(ba×ar + ob×(ar-or), 2)
   */
  it('calcImpairmentAdjustment(ba, ar, ob, or) === round(ba×ar + ob×(ar-or), 2)', () => {
    fc.assert(
      fc.property(
        amount(), // ba (余额调整 ⑤)
        rate(),   // ar (调整后信用损失率 ②A)
        amount(), // ob (原始余额 ①)
        rate(),   // or (原始信用损失率 ②)
        (ba, ar, ob, or_) => {
          expect(calcImpairmentAdjustment(ba, ar, ob, or_)).toBe(
            round2(ba * ar + ob * (ar - or_)),
          )
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// Feature: g6-other-bond-investment-ecl, Property 5: 借贷平衡
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-ecl, Property 5: 借贷平衡', () => {
  /**
   * **Validates: Requirements 5.3, 6.1**
   *
   * isDebitCreditBalanced(debits, credits) ↔ |SUM(debits)-SUM(credits)| < 0.01
   */
  it('isDebitCreditBalanced(d, c) ↔ |SUM(d)-SUM(c)| < 0.01', () => {
    fc.assert(
      fc.property(
        amountArray(),
        amountArray(),
        (d, c) => {
          const sumD = d.reduce((s, v) => s + v, 0)
          const sumC = c.reduce((s, v) => s + v, 0)
          expect(isDebitCreditBalanced(d, c)).toBe(Math.abs(sumD - sumC) < 0.01)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════
// Feature: g6-other-bond-investment-ecl, Property 6: parseNum健壮性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-ecl, Property 6: parseNum健壮性', () => {
  /**
   * **Validates: Requirements 6.1**
   *
   * null/undefined/NaN/Infinity/空串 → 0, 有效数字透传
   */
  it('parseNum(null/undefined/\'\'/NaN/Infinity) === 0', () => {
    fc.assert(
      fc.property(
        fc.oneof(
          fc.constant(null),
          fc.constant(undefined),
          fc.constant(''),
          fc.constant(NaN),
          fc.constant(Infinity),
          fc.constant(-Infinity),
          fc.constant('abc'),
          fc.constant('  '),
        ),
        (v) => {
          expect(parseNum(v)).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('∀ finite n: parseNum(n) === n (有效数字透传)', () => {
    fc.assert(
      fc.property(
        fc.float({ noNaN: true, noDefaultInfinity: true }),
        (n) => {
          expect(parseNum(n)).toBe(n)
        },
      ),
      { numRuns: 100 },
    )
  })
})


// ═══════════════════════════════════════════════════════════════════
// Feature: g6-other-bond-investment-ecl, Property 6: 列式转置数据完整性
// ═══════════════════════════════════════════════════════════════════

describe('Feature: g6-other-bond-investment-ecl, Property 6: 列式转置数据完整性', () => {
  /**
   * **Validates: Requirements 2.1, 2.6**
   *
   * 有效列数 = 输出行数，且每行的investProject对应原始列头
   */

  // Generator: 列式源数据（每列有header + values）
  const columnDataGen = () =>
    fc.array(
      fc.record({
        header: fc.string({ minLength: 1 }),
        values: fc.array(fc.string()),
      }),
      { minLength: 1, maxLength: 20 },
    )

  it('P6: transposeToRows输出行数 === 有效列数(有列头的列)', () => {
    const { transposeToRows } = useG6EclStageClassification()

    fc.assert(
      fc.property(
        columnDataGen(),
        (columns) => {
          // 构建ColumnarSourceData，每列header作为columnHeaders，values分散到三个matrix
          const columnHeaders = columns.map(c => c.header)

          // 构建矩阵：为简化，将values均匀分配到sectionOneMatrix(13行)
          const sectionOneMatrix: string[][] = Array.from({ length: 13 }, (_, rowIdx) =>
            columns.map(c => c.values[rowIdx] ?? ''),
          )
          const sectionTwoMatrix: string[][] = Array.from({ length: 3 }, (_, rowIdx) =>
            columns.map(c => c.values[13 + rowIdx] ?? ''),
          )
          const sectionThreeMatrix: string[][] = Array.from({ length: 8 }, (_, rowIdx) =>
            columns.map(c => c.values[16 + rowIdx] ?? ''),
          )

          const source: ColumnarSourceData = {
            columnHeaders,
            sectionOneMatrix,
            sectionTwoMatrix,
            sectionThreeMatrix,
          }

          const result = transposeToRows(source)

          // 有效列 = 有header(minLength:1, 非空) 的列，所有列都有非空header
          // 因此输出行数 === 列数
          expect(result.length).toBe(columns.length)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('P6: 每行investProject对应原始列头', () => {
    const { transposeToRows } = useG6EclStageClassification()

    fc.assert(
      fc.property(
        columnDataGen(),
        (columns) => {
          const columnHeaders = columns.map(c => c.header)

          const sectionOneMatrix: string[][] = Array.from({ length: 13 }, (_, rowIdx) =>
            columns.map(c => c.values[rowIdx] ?? ''),
          )
          const sectionTwoMatrix: string[][] = Array.from({ length: 3 }, (_, rowIdx) =>
            columns.map(c => c.values[13 + rowIdx] ?? ''),
          )
          const sectionThreeMatrix: string[][] = Array.from({ length: 8 }, (_, rowIdx) =>
            columns.map(c => c.values[16 + rowIdx] ?? ''),
          )

          const source: ColumnarSourceData = {
            columnHeaders,
            sectionOneMatrix,
            sectionTwoMatrix,
            sectionThreeMatrix,
          }

          const result = transposeToRows(source)

          // 验证每行investProject === 对应列头(trim后)
          result.forEach((row, idx) => {
            const expectedHeader = columnHeaders[idx].trim()
            expect(row.investProject).toBe(expectedHeader)
          })
        },
      ),
      { numRuns: 100 },
    )
  })
})
