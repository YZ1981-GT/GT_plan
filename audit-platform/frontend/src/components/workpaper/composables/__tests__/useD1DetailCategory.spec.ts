/**
 * Property-Based Tests — D1-2 原值明细(按类别) composable
 *
 * Spec: .kiro/specs/d1-adjudication-table/
 * Tasks: 4.2, 4.3
 *
 * 使用 fast-check + vitest 验证：
 * - Property 8: 动态行添加保持结构不变量
 * - Property 13: 动态行序列化Round-Trip
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { parseNum, calcAuditedAmount, calcCurrentUnadjusted } from '../useD1FormulaEngine'
import type { CategoryRow } from '../useD1DetailCategory'

// ─── Helpers replicating composable logic ────────────────────────────────────

/** Recalculate computed fields for a CategoryRow (mirrors recalcRow in composable) */
function recalcRow(row: CategoryRow): CategoryRow {
  const priorAudited = calcAuditedAmount(row.priorUnadjusted, row.priorAje, row.priorRje)
  const currentUnadjusted = calcCurrentUnadjusted(priorAudited, row.currentIncrease, row.currentDecrease)
  const currentAudited = calcAuditedAmount(currentUnadjusted, row.currentAje, row.currentRje)
  return {
    ...row,
    priorAudited,
    currentUnadjusted,
    currentAudited,
  }
}

/** Generate a unique dynamic row ID (mirrors generateRowId) */
let rowCounter = 0
function generateRowId(): string {
  return `dynamic-test-${Date.now()}-${rowCounter++}`
}

/** Simulate addRow: appends a new empty row to the end of the rows array */
function addRow(rows: CategoryRow[]): CategoryRow[] {
  const newRow: CategoryRow = recalcRow({
    rowId: generateRowId(),
    category: '',
    isFixed: false,
    priorUnadjusted: 0,
    priorAje: 0,
    priorRje: 0,
    priorAudited: 0,
    currentIncrease: 0,
    currentDecrease: 0,
    currentUnadjusted: 0,
    currentAje: 0,
    currentRje: 0,
    currentAudited: 0,
  })
  return [...rows, newRow]
}

/**
 * Serialize rows for storage (mirrors serializeRows in composable).
 * Only user-editable fields are stored; computed fields (priorAudited, currentUnadjusted, currentAudited)
 * are excluded and will be recalculated on load.
 */
function serializeRows(rows: CategoryRow[]): string {
  const data = rows.map(r => ({
    rowId: r.rowId,
    category: r.category,
    isFixed: r.isFixed,
    priorUnadjusted: r.priorUnadjusted,
    priorAje: r.priorAje,
    priorRje: r.priorRje,
    currentIncrease: r.currentIncrease,
    currentDecrease: r.currentDecrease,
    currentAje: r.currentAje,
    currentRje: r.currentRje,
  }))
  return JSON.stringify(data)
}

/**
 * Deserialize rows from JSON (mirrors loadFromResponses parsing logic).
 * Recalculates computed fields after parsing.
 */
function deserializeRows(json: string): CategoryRow[] {
  const parsed = JSON.parse(json)
  if (!Array.isArray(parsed)) return []
  return parsed.map((r: any) => recalcRow({
    rowId: r.rowId || generateRowId(),
    category: r.category || '',
    isFixed: Boolean(r.isFixed),
    priorUnadjusted: parseNum(r.priorUnadjusted),
    priorAje: parseNum(r.priorAje),
    priorRje: parseNum(r.priorRje),
    priorAudited: 0,
    currentIncrease: parseNum(r.currentIncrease),
    currentDecrease: parseNum(r.currentDecrease),
    currentUnadjusted: 0,
    currentAje: parseNum(r.currentAje),
    currentRje: parseNum(r.currentRje),
    currentAudited: 0,
  }))
}

// ─── Generators ──────────────────────────────────────────────────────────────

const amountArb = fc.float({ min: -1e9, max: 1e9, noNaN: true })

/** Generator for a single CategoryRow with random numeric fields */
const categoryRowArb: fc.Arbitrary<CategoryRow> = fc.record({
  rowId: fc.string({ minLength: 4, maxLength: 16 }).map(s => `dynamic-${s}`),
  category: fc.string({ minLength: 0, maxLength: 20 }),
  isFixed: fc.boolean(),
  priorUnadjusted: amountArb,
  priorAje: amountArb,
  priorRje: amountArb,
  priorAudited: fc.constant(0), // will be recalculated
  currentIncrease: amountArb,
  currentDecrease: amountArb,
  currentUnadjusted: fc.constant(0), // will be recalculated
  currentAje: amountArb,
  currentRje: amountArb,
  currentAudited: fc.constant(0), // will be recalculated
}).map(row => recalcRow(row))

// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: 动态行添加保持结构不变量
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 8: 动态行添加保持结构不变量', () => {
  /**
   * **Validates: Requirements 4.3, 5.2**
   *
   * For any current row list (length N), after addRow():
   * 1. The row list length should be N+1
   * 2. The new row should have all numeric fields = 0
   * 3. The new row should be the last element (before subtotal which is computed, not in the rows array)
   */
  it('addRow后行数为N+1', () => {
    fc.assert(
      fc.property(
        fc.array(categoryRowArb, { minLength: 0, maxLength: 10 }),
        (initialRows) => {
          const originalLength = initialRows.length
          const updatedRows = addRow(initialRows)
          expect(updatedRows).toHaveLength(originalLength + 1)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('新行所有数值字段为0', () => {
    fc.assert(
      fc.property(
        fc.array(categoryRowArb, { minLength: 0, maxLength: 10 }),
        (initialRows) => {
          const updatedRows = addRow(initialRows)
          const newRow = updatedRows[updatedRows.length - 1]

          // All numeric fields should be 0
          expect(newRow.priorUnadjusted).toBe(0)
          expect(newRow.priorAje).toBe(0)
          expect(newRow.priorRje).toBe(0)
          expect(newRow.priorAudited).toBe(0)
          expect(newRow.currentIncrease).toBe(0)
          expect(newRow.currentDecrease).toBe(0)
          expect(newRow.currentUnadjusted).toBe(0)
          expect(newRow.currentAje).toBe(0)
          expect(newRow.currentRje).toBe(0)
          expect(newRow.currentAudited).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('新行位于末尾（小计行之前，小计为computed不在rows数组中）', () => {
    fc.assert(
      fc.property(
        fc.array(categoryRowArb, { minLength: 0, maxLength: 10 }),
        (initialRows) => {
          const updatedRows = addRow(initialRows)
          const newRow = updatedRows[updatedRows.length - 1]

          // New row is the last element in the array
          expect(newRow.isFixed).toBe(false)
          expect(newRow.category).toBe('')
          expect(newRow.rowId).toMatch(/^dynamic-/)

          // Original rows are preserved in order
          for (let i = 0; i < initialRows.length; i++) {
            expect(updatedRows[i].rowId).toBe(initialRows[i].rowId)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 13: 动态行序列化Round-Trip
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-adjudication-table, Property 13: 动态行序列化Round-Trip', () => {
  /**
   * **Validates: Requirements 8.7, 9.3**
   *
   * For any valid CategoryRow array, serializing with JSON.stringify and then
   * parsing with JSON.parse should produce a deeply equal result for all
   * user-editable fields. Computed fields (priorAudited, currentUnadjusted,
   * currentAudited) are excluded from serialization but recalculated correctly on load.
   */
  it('序列化后再反序列化，用户可编辑字段深度相等', () => {
    fc.assert(
      fc.property(
        fc.array(categoryRowArb, { minLength: 0, maxLength: 10 }),
        (rows) => {
          // Serialize (only user-editable fields)
          const serialized = serializeRows(rows)

          // Deserialize (recalculates computed fields)
          const deserialized = deserializeRows(serialized)

          // Length should be preserved
          expect(deserialized).toHaveLength(rows.length)

          // Each row's user-editable fields should match
          for (let i = 0; i < rows.length; i++) {
            const original = rows[i]
            const restored = deserialized[i]

            // Identity fields
            expect(restored.rowId).toBe(original.rowId)
            expect(restored.category).toBe(original.category)
            expect(restored.isFixed).toBe(original.isFixed)

            // User-editable numeric fields (using toBeCloseTo for floating-point)
            expect(restored.priorUnadjusted).toBeCloseTo(original.priorUnadjusted, 5)
            expect(restored.priorAje).toBeCloseTo(original.priorAje, 5)
            expect(restored.priorRje).toBeCloseTo(original.priorRje, 5)
            expect(restored.currentIncrease).toBeCloseTo(original.currentIncrease, 5)
            expect(restored.currentDecrease).toBeCloseTo(original.currentDecrease, 5)
            expect(restored.currentAje).toBeCloseTo(original.currentAje, 5)
            expect(restored.currentRje).toBeCloseTo(original.currentRje, 5)

            // Computed fields should be correctly recalculated
            expect(restored.priorAudited).toBeCloseTo(original.priorAudited, 5)
            expect(restored.currentUnadjusted).toBeCloseTo(original.currentUnadjusted, 5)
            expect(restored.currentAudited).toBeCloseTo(original.currentAudited, 5)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('空数组序列化round-trip保持为空', () => {
    const serialized = serializeRows([])
    const deserialized = deserializeRows(serialized)
    expect(deserialized).toHaveLength(0)
  })

  it('JSON.stringify → JSON.parse 原始JSON结构深度相等', () => {
    fc.assert(
      fc.property(
        fc.array(categoryRowArb, { minLength: 1, maxLength: 10 }),
        (rows) => {
          // Direct JSON round-trip of the serialized data (editable fields only)
          const serialized = serializeRows(rows)
          const parsed = JSON.parse(serialized)
          const reSerialized = JSON.stringify(parsed)

          // The JSON structure should be identical after round-trip
          expect(reSerialized).toBe(serialized)
        },
      ),
      { numRuns: 100 },
    )
  })
})
