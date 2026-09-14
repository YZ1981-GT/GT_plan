/**
 * Property-Based Tests — F2 跨Sheet联动
 *
 * Spec: .kiro/specs/f2-inventory-main/
 * Tasks: 4.2, 4.3
 *
 * Property 10: 明细→汇总聚合正确性
 * Property 11: 审定表净值=原值-跌价（13类别）
 *
 * **Validates: Requirements 2.5, 2.10, 3.1, 3.10, 4.2**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import { calcSubtotal, calcNetValue } from '../composables/useF2InvMaiFormulaEngine'
import type { F2DetailRow } from '../composables/useF2DetailSheet'
import { F2_DETAIL_SHEET_CONFIGS } from '../f2/detail/f2DetailSheetConfigs'

// ─── Helpers ────────────────────────────────────────────────────────────────

/** 11种明细表 sheetCode 列表 */
const DETAIL_SHEET_CODES = Object.keys(F2_DETAIL_SHEET_CONFIGS)

/** 生成单条 F2DetailRow（金额随机） */
const arbDetailRow = fc.record({
  id: fc.string({ minLength: 1, maxLength: 8 }),
  itemName: fc.string({ minLength: 1, maxLength: 10 }),
  openingQty: fc.float({ min: 0, max: 1e6, noNaN: true }),
  openingAmt: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  increaseQty: fc.float({ min: 0, max: 1e6, noNaN: true }),
  increaseAmt: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  decreaseQty: fc.float({ min: 0, max: 1e6, noNaN: true }),
  decreaseAmt: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  closingQty: fc.float({ min: 0, max: 1e6, noNaN: true }),
  closingAmt: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  unitPrice: fc.constant(0 as number | ''),
  agingLt1: fc.float({ min: 0, max: 1e8, noNaN: true }),
  aging1to2: fc.float({ min: 0, max: 1e8, noNaN: true }),
  aging2to3: fc.float({ min: 0, max: 1e8, noNaN: true }),
  agingGt3: fc.float({ min: 0, max: 1e8, noNaN: true }),
  agingTotal: fc.constant(0),
}) as fc.Arbitrary<F2DetailRow>

/** 生成多行明细表（1~20行） */
const arbDetailRows = fc.array(arbDetailRow, { minLength: 1, maxLength: 20 })

/** 生成11种类别的明细表数据集 */
const arbAllDetailSheets = fc.tuple(
  ...DETAIL_SHEET_CODES.map(() => arbDetailRows),
) as fc.Arbitrary<F2DetailRow[][]>

// ─── Property 10 PBT: 明细→汇总聚合正确性 ──────────────────────────────────

describe('Feature: f2-inventory-main, Property 10: 明细→汇总聚合正确性', () => {
  /**
   * **Validates: Requirements 3.1, 4.2**
   *
   * ∀ detailRows[11 categories]:
   * 汇总表各类别行金额 === 对应明细表所有行的合计（openingAmt/increaseAmt/decreaseAmt/closingAmt）
   *
   * 测试纯聚合逻辑：detailToSummary 就是对每张明细表的行做 calcSubtotal
   */
  it('各类别明细表行合计 === 汇总表对应类别行数据', () => {
    fc.assert(
      fc.property(arbAllDetailSheets, (allSheets) => {
        // 模拟 detailToSummaryAggregation 逻辑：
        // 对每张明细表(11种类别)，汇总各列合计
        for (let i = 0; i < DETAIL_SHEET_CODES.length; i++) {
          const rows = allSheets[i]

          // 聚合逻辑（与 useF2CrossSheet.loadDetailTotals 一致）
          const aggregatedOpening = calcSubtotal(rows.map((r) => r.openingAmt))
          const aggregatedIncrease = calcSubtotal(rows.map((r) => r.increaseAmt))
          const aggregatedDecrease = calcSubtotal(rows.map((r) => r.decreaseAmt))
          const aggregatedClosing = calcSubtotal(rows.map((r) => r.closingAmt))

          // 直接用 reduce 验证：汇总表各列 === 明细行各列之和
          const expectedOpening = rows.reduce((s, r) => s + r.openingAmt, 0)
          const expectedIncrease = rows.reduce((s, r) => s + r.increaseAmt, 0)
          const expectedDecrease = rows.reduce((s, r) => s + r.decreaseAmt, 0)
          const expectedClosing = rows.reduce((s, r) => s + r.closingAmt, 0)

          expect(aggregatedOpening).toBeCloseTo(expectedOpening, 5)
          expect(aggregatedIncrease).toBeCloseTo(expectedIncrease, 5)
          expect(aggregatedDecrease).toBeCloseTo(expectedDecrease, 5)
          expect(aggregatedClosing).toBeCloseTo(expectedClosing, 5)
        }
      }),
      { numRuns: 100 },
    )
  })

  it('汇总表合计行 === 所有11类别聚合之总和', () => {
    fc.assert(
      fc.property(arbAllDetailSheets, (allSheets) => {
        // 每类别 closingAmt 合计
        const categorySums = allSheets.map((rows) =>
          calcSubtotal(rows.map((r) => r.closingAmt)),
        )

        // 汇总表合计行 = 所有类别之和
        const grandTotal = calcSubtotal(categorySums)
        const expectedGrandTotal = categorySums.reduce((s, v) => s + v, 0)

        expect(grandTotal).toBeCloseTo(expectedGrandTotal, 5)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 11 PBT: 审定表净值=原值-跌价 ─────────────────────────────────

/** 13类别（含商品进销差价+跌价准备） */
const CATEGORY_COUNT = 13

/** 生成13类别的原值审定数 + 跌价审定数 */
const arbAuditedPairs = fc.array(
  fc.record({
    grossEndAudited: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
    impairmentEndAudited: fc.float({ min: 0, max: 1e9, noNaN: true }),
  }),
  { minLength: CATEGORY_COUNT, maxLength: CATEGORY_COUNT },
)

describe('Feature: f2-inventory-main, Property 11: 审定表净值=原值-跌价（13类别）', () => {
  /**
   * **Validates: Requirements 2.5, 2.10, 3.10**
   *
   * ∀ 13类别:
   * netValueRow[i].endAudited === originalValueRow[i].endAudited - impairmentRow[i].endAudited
   *
   * 即净值区各类别审定数 = 原值区审定数 - 跌价区审定数
   * 使用 calcNetValue(gross, impairment) 验证
   */
  it('∀ 13类别: 净值审定 === 原值审定 - 跌价审定', () => {
    fc.assert(
      fc.property(arbAuditedPairs, (pairs) => {
        for (let i = 0; i < CATEGORY_COUNT; i++) {
          const { grossEndAudited, impairmentEndAudited } = pairs[i]

          // netValueComputed 逻辑: calcNetValue(grossRow.endAudited, impairmentRow.endAudited)
          const netEndAudited = calcNetValue(grossEndAudited, impairmentEndAudited)
          const expected = grossEndAudited - impairmentEndAudited

          expect(netEndAudited).toBeCloseTo(expected, 5)
        }
      }),
      { numRuns: 100 },
    )
  })

  it('净值合计 === 原值合计 - 跌价合计', () => {
    fc.assert(
      fc.property(arbAuditedPairs, (pairs) => {
        const grossTotal = calcSubtotal(pairs.map((p) => p.grossEndAudited))
        const impairmentTotal = calcSubtotal(pairs.map((p) => p.impairmentEndAudited))
        const netTotal = calcNetValue(grossTotal, impairmentTotal)

        // 也可以逐行算净值再合计，结果应一致（加法交换律）
        const netByRow = pairs.map((p) => calcNetValue(p.grossEndAudited, p.impairmentEndAudited))
        const netRowTotal = calcSubtotal(netByRow)

        expect(netTotal).toBeCloseTo(grossTotal - impairmentTotal, 5)
        expect(netRowTotal).toBeCloseTo(netTotal, 5)
      }),
      { numRuns: 100 },
    )
  })
})
