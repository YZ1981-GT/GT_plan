/**
 * useS34FormulaEngine.spec.ts — S34 子表公式引擎 PBT + 单元测试
 *
 * Spec: .kiro/specs/s34-ipo-review-bundle/ Task 7.2
 * Property 8: 子表汇总公式确定性
 *
 * **Validates: Requirements 5.2, 5.5**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  sumRange,
  safeDivide,
  calcRatio,
  extractColumnRange,
  getCellValue,
  computeFormulas,
  getReadonlyCells,
  isFormulaCell,
  createSumFormula,
  createRatioFormula,
  createThresholdFormula,
  S34_HAS_SUBTABLE_PARENTS,
  S34_16_1_FORMULAS,
  S34_16_2_FORMULAS,
  S34_20_1_FORMULAS,
  S34_34_1_FORMULAS,
  S34_34_2_FORMULAS,
  getS34FormulaDefinitions,
  getS34ParentFormulaDefinitions,
  getS34SubTableDefinitions,
  computeS34SubTableFormulas,
} from './useS34FormulaEngine'

// ─── 浮点容差 ───
const TOL = 1e-9
const approxEqual = (a: number | null, b: number | null, tol = TOL) => {
  if (a === null && b === null) return true
  if (a === null || b === null) return false
  return Math.abs(a - b) <= tol
}

describe('useS34FormulaEngine — 单元测试', () => {
  describe('parseNum', () => {
    it('正常数值透传', () => {
      expect(parseNum(42)).toBe(42)
      expect(parseNum('3.14')).toBeCloseTo(3.14)
    })
    it('null/undefined/空→0', () => {
      expect(parseNum(null)).toBe(0)
      expect(parseNum(undefined)).toBe(0)
      expect(parseNum('')).toBe(0)
    })
    it('NaN→0', () => {
      expect(parseNum(NaN)).toBe(0)
      expect(parseNum('abc')).toBe(0)
    })
  })

  describe('sumRange', () => {
    it('空数组→0', () => {
      expect(sumRange([])).toBe(0)
    })
    it('正常求和', () => {
      expect(sumRange([1, 2, 3, 4, 5])).toBe(15)
    })
    it('含负数', () => {
      expect(sumRange([10, -3, 5])).toBe(12)
    })
  })

  describe('safeDivide', () => {
    it('正常除法', () => {
      expect(safeDivide(10, 2)).toBe(5)
    })
    it('分母=0→null', () => {
      expect(safeDivide(10, 0)).toBeNull()
      expect(safeDivide(0, 0)).toBeNull()
    })
    it('分子=0→0', () => {
      expect(safeDivide(0, 5)).toBe(0)
    })
  })

  describe('calcRatio', () => {
    it('百分比计算', () => {
      expect(calcRatio(1, 4)).toBe(25)
    })
    it('分母=0→null', () => {
      expect(calcRatio(5, 0)).toBeNull()
    })
  })

  describe('S34-16-1 公式计算', () => {
    it('E19 = SUM(E8:E18)，F19 = SUM(F8:F18)', () => {
      // 构造 25 行数据，行 7~17 (0-based) 为明细
      const data: Record<string, number | null>[] = Array.from({ length: 25 }, () => ({
        E: null,
        F: null,
        C: null,
      }))
      // 填入明细行
      for (let i = 7; i <= 17; i++) {
        data[i] = { E: 100, F: 30, C: null }
      }
      // C23 是模板要求人工填写的当期营业收入，不是 E19 的隐式引用。
      data[22] = { E: null, F: null, C: 1100 }
      const result = computeFormulas(data, S34_16_1_FORMULAS)
      // E19 = 11 * 100 = 1100
      expect(result['18:E']).toBe(1100)
      // F19 = 11 * 30 = 330
      expect(result['18:F']).toBe(330)
      // C24 = F19 = 330
      expect(result['23:C']).toBe(330)
      // C25 = C24/C23 = 330/1100 = 0.3
      expect(result['24:C']).toBeCloseTo(0.3)
    })

    it('所有明细为0→C25=null（0/0）', () => {
      const data: Record<string, number | null>[] = Array.from({ length: 25 }, () => ({
        E: 0,
        F: 0,
        C: null,
      }))
      data[22] = { E: null, F: null, C: 0 }
      const result = computeFormulas(data, S34_16_1_FORMULAS)
      expect(result['18:E']).toBe(0)
      expect(result['18:F']).toBe(0)
      expect(result['24:C']).toBeNull()
    })
  })

  describe('getReadonlyCells / isFormulaCell', () => {
    it('S34-16-1 按模板有 4 个只读计算单元格（C23 是输入）', () => {
      const cells = getReadonlyCells(S34_16_1_FORMULAS)
      expect(cells.size).toBe(4)
      expect(cells.has('18:E')).toBe(true)
      expect(cells.has('18:F')).toBe(true)
      expect(cells.has('22:C')).toBe(false)
      expect(cells.has('23:C')).toBe(true)
      expect(cells.has('24:C')).toBe(true)
    })
    it('isFormulaCell 正确识别', () => {
      expect(isFormulaCell(18, 'E', S34_16_1_FORMULAS)).toBe(true)
      expect(isFormulaCell(7, 'E', S34_16_1_FORMULAS)).toBe(false)
    })
  })

  describe('工厂函数', () => {
    it('createSumFormula 正确求和', () => {
      const formula = createSumFormula(5, 'D', 0, 4)
      const data: Record<string, number | null>[] = [
        { D: 10 }, { D: 20 }, { D: 30 }, { D: 40 }, { D: 50 },
        { D: null }, // row 5 = 合计行
      ]
      expect(formula.compute(data)).toBe(150)
      expect(formula.readonly).toBe(true)
    })

    it('createRatioFormula 正确计算占比', () => {
      const formula = createRatioFormula(0, 'G', 'E', 3)
      const data: Record<string, number | null>[] = [
        { E: 25 }, { E: 50 }, { E: 75 }, { E: 100 },
      ]
      expect(formula.compute(data)).toBeCloseTo(0.25)
    })

    it('createThresholdFormula 正确判断', () => {
      const formula = createThresholdFormula(0, 'H', 'E', 100)
      expect(formula.compute([{ E: 150 }])).toBe(1)
      expect(formula.compute([{ E: 50 }])).toBe(0)
      expect(formula.compute([{ E: 100 }])).toBe(0) // > threshold, not >=
    })
  })
})

describe('P1.4 — S34 12 个 hasSubTable 模板公式清册', () => {
  const expectedParents = [
    'S34-2', 'S34-3', 'S34-4', 'S34-8', 'S34-9', 'S34-11',
    'S34-16', 'S34-18', 'S34-20', 'S34-25', 'S34-30', 'S34-34',
  ]

  it('父码清册精确为 12 个，且包含 S34-3', () => {
    expect([...S34_HAS_SUBTABLE_PARENTS]).toEqual(expectedParents)
    expect(S34_HAS_SUBTABLE_PARENTS).toHaveLength(12)
    expect(S34_HAS_SUBTABLE_PARENTS).toContain('S34-3')
  })

  // 每个父码至少有一条独立契约测试；没有模板计算公式的结构化表也必须显式登记为空。
  for (const parentCode of S34_HAS_SUBTABLE_PARENTS) {
    it(`${parentCode} 有模板子表定义且 runtime 公式与清册一致`, () => {
      const tables = getS34SubTableDefinitions(parentCode)
      const parentFormulas = getS34ParentFormulaDefinitions(parentCode)
      expect(tables.length).toBeGreaterThan(0)
      expect(tables.every((table) => table.parentCode === parentCode)).toBe(true)
      expect(parentFormulas).toEqual(tables.flatMap((table) => table.formulas))
      expect(tables.every((table) =>
        table.formulas.every((formula) => formula.readonly === true),
      )).toBe(true)

      const firstSheet = tables[0].sheetCode
      const result = computeS34SubTableFormulas(
        firstSheet,
        Array.from({ length: 45 }, () => ({})),
      )
      expect(result).toBeDefined()
      if (tables.some((table) => table.formulas.length > 0)) {
        expect(Object.keys(result).length).toBeGreaterThan(0)
      } else {
        expect(parentFormulas).toHaveLength(0)
      }
    })
  }

  it('S34-16-2 按模板计算 G19 合计，并安全保留 #REF! 来源', () => {
    const data: Record<string, number | null>[] = Array.from({ length: 27 }, () => ({
      E: null,
      G: null,
    }))
    for (let row = 7; row <= 17; row += 1) data[row].G = 10
    data[22].E = 100
    const result = computeS34SubTableFormulas('S34-16-2', data)
    expect(result['18:G']).toBe(110)
    expect(result['23:E']).toBeNull()
    expect(result['24:E']).toBeNull()
  })

  it('S34-20-1 按模板计算外包占比和合计', () => {
    const data: Record<string, number | null>[] = Array.from({ length: 43 }, () => ({}))
    data[12] = { C: 100, G: 200 }
    data[15] = { C: 25, E: 50 }
    data[16] = { C: 25, E: 50 }
    data[17] = { C: 50, E: 100 }
    const result = computeS34SubTableFormulas('S34-20-1', data)
    expect(result['15:D']).toBeCloseTo(0.25)
    expect(result['15:F']).toBeCloseTo(0.25)
    expect(result['18:D']).toBe(0)
    expect(result['19:F']).toBe(0)
    expect(result['20:C']).toBe(100)
    expect(result['20:E']).toBe(200)
  })

  it('S34-34-1 按模板计算自然人客户占比与明细合计', () => {
    const data: Record<string, number | null>[] = Array.from({ length: 26 }, () => ({}))
    data[8] = { D: 100, N: 200 }
    data[9] = { D: 1000, N: 2000 }
    for (let row = 11; row <= 20; row += 1) {
      data[row] = { G: 10, I: 20 }
    }
    const result = computeS34SubTableFormulas('S34-34-1', data)
    expect(result['8:E']).toBeCloseTo(0.1)
    expect(result['11:H']).toBeCloseTo(0.01)
    expect(result['21:G']).toBe(100)
    expect(result['21:H']).toBeCloseTo(0.1)
    expect(result['21:J']).toBeCloseTo(0.1)
  })

  it('公式计算不修改输入网格，且 S34-34-2 与客户表共享同一模板公式语义', () => {
    const data: Record<string, number | null>[] = Array.from({ length: 26 }, () => ({
      D: 0,
      N: 0,
      G: 0,
      I: 0,
    }))
    const before = JSON.stringify(data)
    computeS34SubTableFormulas('S34-34-2', data)
    expect(JSON.stringify(data)).toBe(before)
    expect(S34_34_1_FORMULAS.map((cell) => cell.formula)).toEqual(
      S34_34_2_FORMULAS.map((cell) => cell.formula),
    )
  })

  it('结构化子表不凭空新增计算公式，S34-3-1 明确为空', () => {
    expect(getS34FormulaDefinitions('S34-3-1')).toEqual([])
    expect(getS34SubTableDefinitions('S34-3')[0]?.templateSheetName).toBe('S34-3-1股份支付核查')
  })
})

describe('useS34FormulaEngine — PBT Property 8: 子表汇总公式确定性', () => {
  /**
   * Property 8: 子表汇总公式确定性
   * **Validates: Requirements 5.2, 5.5**
   *
   * For any 子检查表明细行金额数组，汇总单元格应等于对应纯函数计算结果，
   * 且不受手工覆盖影响（公式列只读）。
   */

  // --- P8.1: SUM 确定性 ---
  it('P8.1: sumRange(values) === values.reduce(+, 0) for any float array', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }), { minLength: 0, maxLength: 50 }),
        (values) => {
          const expected = values.reduce((s, v) => s + v, 0)
          expect(approxEqual(sumRange(values), expected)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- P8.2: safeDivide 确定性 ---
  it('P8.2: safeDivide(n, d) === null when d=0, else n/d', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (numerator, denominator) => {
          const result = safeDivide(numerator, denominator)
          if (denominator === 0) {
            expect(result).toBeNull()
          } else {
            expect(approxEqual(result, numerator / denominator)).toBe(true)
          }
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- P8.3: S34-16-1 SUM 公式 E19=SUM(E8:E18) ---
  it('P8.3: S34-16-1 E19 === SUM of rows 7..17 column E', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }), { minLength: 11, maxLength: 11 }),
        (amounts) => {
          // 构造 25 行数据网格
          const data: Record<string, number | null>[] = Array.from({ length: 25 }, () => ({
            E: 0,
            F: 0,
            C: null,
          }))
          // 填入行 7~17
          for (let i = 0; i < 11; i++) {
            data[7 + i] = { E: amounts[i], F: 0, C: null }
          }
          const result = computeFormulas(data, S34_16_1_FORMULAS)
          const expectedSum = amounts.reduce((s, v) => s + v, 0)
          expect(approxEqual(result['18:E'], expectedSum)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- P8.4: S34-16-1 占比 C25 = C24/C23 确定性 ---
  it('P8.4: S34-16-1 C25 === F_total / E_total (null when E_total=0)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }), { minLength: 11, maxLength: 11 }),
        fc.array(fc.float({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }), { minLength: 11, maxLength: 11 }),
        (eAmounts, fAmounts) => {
          const data: Record<string, number | null>[] = Array.from({ length: 25 }, () => ({
            E: 0,
            F: 0,
            C: null,
          }))
          for (let i = 0; i < 11; i++) {
            data[7 + i] = { E: eAmounts[i], F: fAmounts[i], C: null }
          }
          const eTotal = eAmounts.reduce((s, v) => s + v, 0)
          // C23 是模板中的人工录入营业收入，测试以该次网格的总收入作为有效输入。
          data[22] = { E: null, F: null, C: eTotal }
          const result = computeFormulas(data, S34_16_1_FORMULAS)
          const fTotal = fAmounts.reduce((s, v) => s + v, 0)
          if (eTotal === 0) {
            expect(result['24:C']).toBeNull()
          } else {
            expect(approxEqual(result['24:C'], fTotal / eTotal)).toBe(true)
          }
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- P8.5: 公式单元格只读 —— 所有 FormulaCell.readonly === true ---
  it('P8.5: all formula cells in S34_16_1_FORMULAS have readonly=true', () => {
    for (const cell of S34_16_1_FORMULAS) {
      expect(cell.readonly).toBe(true)
    }
    for (const cell of S34_16_2_FORMULAS) {
      expect(cell.readonly).toBe(true)
    }
  })

  // --- P8.6: computeFormulas 不受手工覆盖影响 ---
  it('P8.6: 公式计算结果仅依赖源数据行，不依赖公式行原始值', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }), { minLength: 11, maxLength: 11 }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (amounts, manualOverride) => {
          // 构造数据网格，在公式行放入手工覆盖值
          const data: Record<string, number | null>[] = Array.from({ length: 25 }, () => ({
            E: 0,
            F: 0,
            C: null,
          }))
          for (let i = 0; i < 11; i++) {
            data[7 + i] = { E: amounts[i], F: amounts[i] * 0.3, C: null }
          }
          data[22] = {
            E: null,
            F: null,
            C: amounts.reduce((s, v) => s + v, 0),
          }
          // 手工在公式行写入覆盖值（模拟用户尝试修改公式单元格）
          data[18] = { E: manualOverride, F: manualOverride, C: null }

          const result = computeFormulas(data, S34_16_1_FORMULAS)
          const expectedE = amounts.reduce((s, v) => s + v, 0)
          // 公式重算结果不受 row 18 原始值影响（因为 SUM 范围是 7~17）
          expect(approxEqual(result['18:E'], expectedE)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- P8.7: extractColumnRange 边界安全 ---
  it('P8.7: extractColumnRange 对超出范围的行返回已有值', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }), { minLength: 1, maxLength: 20 }),
        fc.nat({ max: 30 }),
        fc.nat({ max: 30 }),
        (values, startRow, extraEnd) => {
          const data: Record<string, number | null>[] = values.map((v) => ({ X: v }))
          const endRow = startRow + extraEnd
          const extracted = extractColumnRange(data, 'X', startRow, endRow)
          // 提取的值应等于 data[startRow..min(endRow, data.length-1)] 的 X 列
          const expected: number[] = []
          for (let i = startRow; i <= endRow && i < data.length; i++) {
            expected.push(parseNum(data[i]?.['X']))
          }
          expect(extracted).toEqual(expected)
        },
      ),
      { numRuns: 200 },
    )
  })
})
