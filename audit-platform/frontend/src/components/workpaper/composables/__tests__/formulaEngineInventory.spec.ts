// Feature: formula-management-library, Property 19: 前端引擎三类型映射非破坏计算
/**
 * 属性/示例测试 P19：前端 per-cycle 公式引擎三类型映射非破坏计算。
 *
 * **Property 19: 前端引擎三类型映射非破坏计算**
 *
 * 对任意已接入统一治理的前端 per-cycle 公式引擎，为其计算原语标注三类型语义
 * （auto_calc / reasonability / logic_check）后，该引擎产出的单元数值与接入前逐一相等
 * （标注为元数据，不改变计算结果）。
 *
 * 被测：
 * - `formulaEngineInventory.ts`（Task 13.1：清单 + 三类型映射元数据）
 * - `useD3FormulaEngine.ts` / `useS34FormulaEngine.ts`（Task 13.2 试点接入的两引擎）
 *
 * 验证思路（"接入" = 登记清单 + 挂 tooltip 描述符 + 引用经 ACNR，均为元数据/展示层，
 * 不包裹或改写计算原语）：
 *  1. **非破坏（数值逐一相等）**：对随机输入，试点引擎计算原语的产出与独立算术基线逐一
 *     相等；接入所引入的公式单元描述符（D3_DETAIL_FORMULA_CELLS / getS34FormulaDescriptors）
 *     仅承载 表达式 + ACNR addr_id，不参与求值，故"接入前后"数值不变。
 *  2. **描述符是纯元数据**：S34 描述符暴露的 cellKey 集合与 computeFormulas 结果键一致；
 *     其存在不改变 computeFormulas 的任何数值。
 *  3. **三类型映射是元数据**：PRIMITIVE_TYPE_MAP 把 createSumFormula/createRatioFormula→
 *     auto_calc、createThresholdFormula→reasonability（Req 19.2）；为原语标注类型不改变其
 *     数值输出。
 *  4. **清单完整性 + 无回归**：试点两引擎标 integrated，其余标 pending（Req 19.6 无回归）。
 *
 * Framework: vitest + fast-check（numRuns=20）。
 *
 * **Validates: Requirements 19.2, 19.6**（设计 Req 24.2/24.6）
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  FORMULA_ENGINE_INVENTORY,
  PRIMITIVE_TYPE_MAP,
  getEnginesByStatus,
  getInventorySummary,
  type FormulaType,
} from '../formulaEngineInventory'

import {
  calcPriorAudited,
  calcEndBalance,
  calcEndUnadjusted,
  calcEndAudited,
  D3_DETAIL_FORMULA_CELLS,
} from '../useD3FormulaEngine'

import {
  parseNum as s34ParseNum,
  sumRange,
  safeDivide,
  extractColumnRange,
  computeFormulas,
  createSumFormula,
  createRatioFormula,
  createThresholdFormula,
  S34_16_1_FORMULAS,
  getS34FormulaDescriptors,
} from '../../s34-ipo-bundle/useS34FormulaEngine'

const KNOWN_TYPES: FormulaType[] = ['auto_calc', 'logic_check', 'reasonability']
const numArb = fc.double({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true })
const gridRowArb = fc.record({
  E: fc.option(numArb, { nil: null }),
  F: fc.option(numArb, { nil: null }),
})

// ── 独立算术基线（"接入前"的等价计算，用于逐一比对）──
const baselineEndBalance = (prior: number, credit: number, debit: number) => prior + credit - debit

describe('Feature: formula-management-library, Property 19: 前端引擎三类型映射非破坏计算', () => {
  it('D3 试点引擎：接入后计算原语产出与算术基线逐一相等（auto_calc 映射非破坏）', () => {
    fc.assert(
      fc.property(numArb, numArb, numArb, (a, b, c) => {
        // calcPriorAudited / calcEndBalance / calcEndUnadjusted / calcEndAudited
        // 均为 auto_calc 语义（求和/账面价值），接入描述符后数值不变。
        expect(calcPriorAudited(a, b, c)).toBeCloseTo(a + b + c, 5)
        expect(calcEndBalance(a, b, c)).toBeCloseTo(baselineEndBalance(a, b, c), 5)
        expect(calcEndUnadjusted(a, b)).toBeCloseTo(a + b, 5)
        expect(calcEndAudited(a, b, c)).toBeCloseTo(a + b + c, 5)
      }),
      { numRuns: 20 },
    )
  })

  it('D3 描述符是纯元数据：字段/表达式/ACNR addr_id 齐备，不参与求值', () => {
    // 四个自动计算列各有描述符，且 addr_id 为 ACNR 稳定格式（D3/D3-2/列），非渲染层拼接。
    for (const field of ['priorAudited', 'endBalance', 'endUnadjusted', 'endAudited'] as const) {
      const desc = D3_DETAIL_FORMULA_CELLS[field]
      expect(desc.field).toBe(field)
      expect(typeof desc.expression).toBe('string')
      expect(desc.expression.length).toBeGreaterThan(0)
      expect(desc.addrId).toMatch(/^D3\/D3-2\/[A-Z]$/)
    }
  })

  it('S34 试点引擎：computeFormulas 产出与纯函数基线逐一相等（描述符不改数值）', () => {
    fc.assert(
      fc.property(fc.array(gridRowArb, { minLength: 0, maxLength: 14 }), (grid) => {
        const before = computeFormulas(grid, S34_16_1_FORMULAS)

        // "接入" = 取描述符（getS34FormulaDescriptors 是纯元数据读取）。
        const descriptors = getS34FormulaDescriptors('S34-16-1')
        const after = computeFormulas(grid, S34_16_1_FORMULAS)

        // 描述符不改变任何计算结果：接入前后逐一相等。
        expect(after).toEqual(before)

        // 描述符暴露的 cellKey 集合恰为 computeFormulas 的结果键集合（元数据对齐）。
        expect(new Set(descriptors.map((d) => d.cellKey))).toEqual(new Set(Object.keys(before)))

        // addr_id 为 ACNR 稳定格式 S34/{sheet}/{col}{row+1}，非运行时坐标拼接。
        for (const d of descriptors) {
          expect(d.addrId).toMatch(/^S34\/S34-16-1\/[A-Z]\d+$/)
        }

        // 数值独立可复算：E19/F19 合计 = 明细行(0-based 7~17)求和（基线）。
        const eSum = sumRange(extractColumnRange(grid, 'E', 7, 17))
        const fSum = sumRange(extractColumnRange(grid, 'F', 7, 17))
        expect(before['18:E']).toBeCloseTo(eSum, 5)
        expect(before['18:F']).toBeCloseTo(fSum, 5)
        expect(before['24:C']).toEqual(safeDivide(fSum, eSum))
      }),
      { numRuns: 20 },
    )
  })

  it('三类型映射是元数据：为工厂原语标注类型不改变其数值输出（Req 19.2）', () => {
    // 映射规则：求和/比率 → auto_calc；阈值 → reasonability。
    expect(PRIMITIVE_TYPE_MAP.createSumFormula).toBe('auto_calc')
    expect(PRIMITIVE_TYPE_MAP.createRatioFormula).toBe('auto_calc')
    expect(PRIMITIVE_TYPE_MAP.createThresholdFormula).toBe('reasonability')

    fc.assert(
      fc.property(fc.array(gridRowArb, { minLength: 1, maxLength: 12 }), (grid) => {
        // createSumFormula（auto_calc）：其 compute 等于范围求和基线，与所映射的类型无关。
        const sumDef = createSumFormula(0, 'E', 0, grid.length - 1)
        expect(sumDef.compute(grid)).toBeCloseTo(
          sumRange(extractColumnRange(grid, 'E', 0, grid.length - 1)),
          5,
        )

        // createRatioFormula（auto_calc）：占比 = 行值/合计行值（安全除法），类型标注非破坏。
        // 取 row=0、totalRow=最后一行，与 safeDivide(值, 合计值) 基线逐一相等。
        const lastRow = grid.length - 1
        const ratioDef = createRatioFormula(0, 'G', 'E', lastRow)
        const rowVal = s34ParseNum(grid[0]?.E)
        const totalVal = s34ParseNum(grid[lastRow]?.E)
        expect(ratioDef.compute(grid)).toEqual(safeDivide(rowVal, totalVal))

        // createThresholdFormula（reasonability）：阈值判断输出仅 0/1，标注类型不改变结果。
        const thDef = createThresholdFormula(0, 'H', 'E', 0)
        const expected = s34ParseNum(grid[0]?.E) > 0 ? 1 : 0
        expect(thDef.compute(grid)).toBe(expected)
      }),
      { numRuns: 20 },
    )
  })

  it('清单完整性：试点两引擎 integrated、其余 pending（Req 19.6 无回归）', () => {
    const integrated = getEnginesByStatus('integrated')
    const integratedPaths = new Set(integrated.map((e) => e.filePath))

    // 试点两引擎已接入。
    expect(integratedPaths.has('src/components/workpaper/composables/useD3FormulaEngine.ts')).toBe(true)
    expect(integratedPaths.has('src/components/workpaper/s34-ipo-bundle/useS34FormulaEngine.ts')).toBe(true)

    // 每条清单条目：formulaTypes ⊆ 已知三类型，且 status 合法。
    for (const entry of FORMULA_ENGINE_INVENTORY) {
      expect(entry.formulaTypes.length).toBeGreaterThan(0)
      for (const t of entry.formulaTypes) expect(KNOWN_TYPES).toContain(t)
      expect(['integrated', 'pending']).toContain(entry.status)
    }

    // 摘要计数自洽：integrated + pending == total。
    const summary = getInventorySummary()
    expect(summary.integrated + summary.pending).toBe(summary.total)
    expect(summary.total).toBe(FORMULA_ENGINE_INVENTORY.length)
    // 大量引擎仍待接入（增量收敛，无一次性重写回归风险）。
    expect(summary.pending).toBeGreaterThan(0)
  })
})
