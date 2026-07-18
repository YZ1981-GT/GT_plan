/**
 * F1 Property 9 PBT: 明细表合计行恒等于明细行之和
 *
 * 验证明细表F1-2合计行的正确性：
 * - 合计行各金额列 === SUM(所有明细行对应列)
 * - 适用于所有数值列（priorUnadjusted, priorAdjustment, ..., endAudited, aging等）
 *
 * **Validates: Requirements 4.8, 13.6**
 */
import { describe, it } from 'vitest'
import * as fc from 'fast-check'
import { calcSubtotal } from '../composables/useF1FormulaEngine'
import { recalcRowFormulas, type DetailRow } from '../composables/useF1Detail'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 生成明细行（含完整字段，金额字段随机） */
const detailRowArb: fc.Arbitrary<DetailRow> = fc.record({
  rowId: fc.string({ minLength: 1, maxLength: 10 }).map(s => `row-${s}`),
  customerName: fc.constantFrom('供应商A', '供应商B', '供应商C', '供应商D', '供应商E'),
  companyCode: fc.constant(''),
  nature: fc.constantFrom('货款', '工程款', '设备款', '服务费', '其他'),
  relationType: fc.constant('非关联方'),
  priorUnadjusted: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
  priorAdjustment: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
  priorReclass: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
  priorAudited: fc.constant(0), // will be recalculated
  agingPrior: fc.record({
    within1: fc.float({ min: 0, max: 1e8, noNaN: true }),
    y1to2: fc.float({ min: 0, max: 1e8, noNaN: true }),
    y2to3: fc.float({ min: 0, max: 1e8, noNaN: true }),
    over3: fc.float({ min: 0, max: 1e8, noNaN: true }),
  }),
  debit: fc.float({ min: 0, max: 1e8, noNaN: true }),
  credit: fc.float({ min: 0, max: 1e8, noNaN: true }),
  endBalance: fc.constant(0), // will be recalculated
  entityReclass: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
  endUnadjusted: fc.constant(0), // will be recalculated
  agingCurrent: fc.record({
    within1: fc.float({ min: 0, max: 1e8, noNaN: true }),
    y1to2: fc.float({ min: 0, max: 1e8, noNaN: true }),
    y2to3: fc.float({ min: 0, max: 1e8, noNaN: true }),
    over3: fc.float({ min: 0, max: 1e8, noNaN: true }),
  }),
  endAje: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
  endRje: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
  endAudited: fc.constant(0), // will be recalculated
  agingAudited: fc.record({
    within1: fc.float({ min: 0, max: 1e8, noNaN: true }),
    y1to2: fc.float({ min: 0, max: 1e8, noNaN: true }),
    y2to3: fc.float({ min: 0, max: 1e8, noNaN: true }),
    over3: fc.float({ min: 0, max: 1e8, noNaN: true }),
  }),
  isConfirmed: fc.constant(''),
  postPeriodSettlement: fc.float({ min: 0, max: 1e8, noNaN: true }),
  remark: fc.constant(''),
})

const detailRowsArb = fc.array(detailRowArb, { minLength: 0, maxLength: 10 })

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('F1 Property 9: 明细表合计行恒等于明细行之和', () => {
  /**
   * **Property 9a: 合计行各金额列 === SUM(明细行对应列)**
   *
   * 对任意 DetailRow[] 数组（经公式重算后），合计行的每个金额列
   * 应等于所有明细行该列值之和。
   *
   * **Validates: Requirements 4.8, 13.6**
   */
  it('合计行 priorUnadjusted === SUM(明细行.priorUnadjusted)', () => {
    fc.assert(
      fc.property(detailRowsArb, (rawRows) => {
        const rows = rawRows.map(recalcRowFormulas)
        const subtotal = calcSubtotal(rows.map(r => r.priorUnadjusted))
        const expected = rows.reduce((sum, r) => sum + r.priorUnadjusted, 0)
        return Math.abs(subtotal - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  it('合计行 priorAudited === SUM(明细行.priorAudited)', () => {
    fc.assert(
      fc.property(detailRowsArb, (rawRows) => {
        const rows = rawRows.map(recalcRowFormulas)
        const subtotal = calcSubtotal(rows.map(r => r.priorAudited))
        const expected = rows.reduce((sum, r) => sum + r.priorAudited, 0)
        return Math.abs(subtotal - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  it('合计行 debit === SUM(明细行.debit)', () => {
    fc.assert(
      fc.property(detailRowsArb, (rawRows) => {
        const rows = rawRows.map(recalcRowFormulas)
        const subtotal = calcSubtotal(rows.map(r => r.debit))
        const expected = rows.reduce((sum, r) => sum + r.debit, 0)
        return Math.abs(subtotal - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  it('合计行 credit === SUM(明细行.credit)', () => {
    fc.assert(
      fc.property(detailRowsArb, (rawRows) => {
        const rows = rawRows.map(recalcRowFormulas)
        const subtotal = calcSubtotal(rows.map(r => r.credit))
        const expected = rows.reduce((sum, r) => sum + r.credit, 0)
        return Math.abs(subtotal - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  it('合计行 endBalance === SUM(明细行.endBalance)', () => {
    fc.assert(
      fc.property(detailRowsArb, (rawRows) => {
        const rows = rawRows.map(recalcRowFormulas)
        const subtotal = calcSubtotal(rows.map(r => r.endBalance))
        const expected = rows.reduce((sum, r) => sum + r.endBalance, 0)
        return Math.abs(subtotal - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  it('合计行 endAudited === SUM(明细行.endAudited)', () => {
    fc.assert(
      fc.property(detailRowsArb, (rawRows) => {
        const rows = rawRows.map(recalcRowFormulas)
        const subtotal = calcSubtotal(rows.map(r => r.endAudited))
        const expected = rows.reduce((sum, r) => sum + r.endAudited, 0)
        return Math.abs(subtotal - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 9b: 合计行账龄各段 === SUM(明细行对应账龄段)**
   *
   * **Validates: Requirements 4.8**
   */
  it('合计行 agingAudited.within1 === SUM(明细行.agingAudited.within1)', () => {
    fc.assert(
      fc.property(detailRowsArb, (rawRows) => {
        const rows = rawRows.map(recalcRowFormulas)
        const subtotal = calcSubtotal(rows.map(r => r.agingAudited.within1))
        const expected = rows.reduce((sum, r) => sum + r.agingAudited.within1, 0)
        return Math.abs(subtotal - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  it('合计行 agingAudited.over3 === SUM(明细行.agingAudited.over3)', () => {
    fc.assert(
      fc.property(detailRowsArb, (rawRows) => {
        const rows = rawRows.map(recalcRowFormulas)
        const subtotal = calcSubtotal(rows.map(r => r.agingAudited.over3))
        const expected = rows.reduce((sum, r) => sum + r.agingAudited.over3, 0)
        return Math.abs(subtotal - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 9c: 空数组时合计为 0**
   *
   * **Validates: Requirements 4.8**
   */
  it('空行列表的合计行各列为 0', () => {
    const rows: DetailRow[] = []
    const subtotal = calcSubtotal(rows.map(r => r.endAudited))
    const subtotalDebit = calcSubtotal(rows.map(r => r.debit))
    const subtotalCredit = calcSubtotal(rows.map(r => r.credit))

    fc.assert(
      fc.property(fc.constant(null), () => {
        return subtotal === 0 && subtotalDebit === 0 && subtotalCredit === 0
      }),
      { numRuns: 1 },
    )
  })
})
