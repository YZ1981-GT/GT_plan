/**
 * Wave 6 / Task 7.1 — G7 前端属性测试（fast-check）。
 *
 * Property 2: Persist_First 不改已填值 — overwrite=false 后原非零/非空字段逐字不变。
 * Property 4: 按名归并幂等 — 同一取数重复应用两次 state 行数与值不变。
 *
 * **Validates: Requirements 10.2, 10.4**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { mergeAuxRowsIntoDetail, normalizeInvesteeName } from '../g7AuxExtraction'
import { createG7CostRow, type G7CostRow, type G7DetailState } from '../g7DetailModel'

// ─── Arbitraries ────────────────────────────────────────────────────────────

const arbInvesteeName = fc.string({ minLength: 1, maxLength: 6, unit: fc.constantFrom('甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸', '公', '司', '集', '团') })

const arbAmount = fc.double({ min: -1e6, max: 1e6, noNaN: true })

const arbPositiveAmount = fc.double({ min: 0.01, max: 1e6, noNaN: true })

const arbCostRowPartial = fc.record({
  investeeName: arbInvesteeName,
  openingAmount: arbAmount,
  increaseAmount: arbAmount,
  decreaseAmount: arbAmount,
})

function buildState(rows: Array<{ name: string; opening: number; increase: number; decrease: number }>): G7DetailState {
  const state: G7DetailState = { costRows: [], equityRows: [], impairmentRows: [] }
  for (let i = 0; i < rows.length; i++) {
    const r = createG7CostRow(i + 1, rows[i].name)
    r.openingAmount = rows[i].opening
    r.increaseAmount = rows[i].increase
    r.decreaseAmount = rows[i].decrease
    state.costRows.push(r)
  }
  return state
}

// ─── Property 2: Persist_First 不改已填值 ───────────────────────────────────
// **Validates: Requirements 10.2**

describe('Property 2: Persist_First 不改已填值', () => {
  it('对任意非零已填字段，overwrite=false 后其值逐字不变', () => {
    fc.assert(
      fc.property(
        // Generate existing state with non-zero values
        fc.array(
          fc.record({
            name: arbInvesteeName,
            opening: arbPositiveAmount,
            increase: arbPositiveAmount,
            decrease: arbPositiveAmount,
          }),
          { minLength: 1, maxLength: 5 },
        ),
        // Generate incoming rows (may overlap names)
        fc.array(arbCostRowPartial, { minLength: 1, maxLength: 5 }),
        (existingDefs, incoming) => {
          // Build state with non-zero values
          const state = buildState(existingDefs)

          // Snapshot original non-zero values
          const snapshot = state.costRows.map(r => ({
            name: normalizeInvesteeName(r.investeeName),
            opening: r.openingAmount,
            increase: r.increaseAmount,
            decrease: r.decreaseAmount,
          }))

          // Apply merge with overwrite=false (Persist_First)
          mergeAuxRowsIntoDetail(state, incoming as Array<Partial<G7CostRow>>, { overwrite: false })

          // Assert: all originally non-zero fields remain unchanged
          for (const orig of snapshot) {
            const current = state.costRows.find(
              r => normalizeInvesteeName(r.investeeName) === orig.name,
            )
            if (!current) continue // row still exists after merge

            // Non-zero original values MUST NOT change
            if (Math.abs(orig.opening) > 1e-9) {
              expect(current.openingAmount).toBe(orig.opening)
            }
            if (Math.abs(orig.increase) > 1e-9) {
              expect(current.increaseAmount).toBe(orig.increase)
            }
            if (Math.abs(orig.decrease) > 1e-9) {
              expect(current.decreaseAmount).toBe(orig.decrease)
            }
          }
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ─── Property 4: 按名归并幂等 ──────────────────────────────────────────────
// **Validates: Requirements 10.4**

describe('Property 4: 按名归并幂等', () => {
  it('同一取数结果连续应用两次，state 行数与各字段值不变', () => {
    fc.assert(
      fc.property(
        fc.array(arbCostRowPartial, { minLength: 1, maxLength: 8 }),
        (incoming) => {
          // Start with empty state
          const state: G7DetailState = { costRows: [], equityRows: [], impairmentRows: [] }

          // First application
          mergeAuxRowsIntoDetail(state, incoming as Array<Partial<G7CostRow>>, { overwrite: false })

          // Snapshot after first application
          const countAfterFirst = state.costRows.length
          const valuesAfterFirst = state.costRows.map(r => ({
            name: normalizeInvesteeName(r.investeeName),
            opening: r.openingAmount,
            increase: r.increaseAmount,
            decrease: r.decreaseAmount,
          }))

          // Second application (same input)
          const r2 = mergeAuxRowsIntoDetail(state, incoming as Array<Partial<G7CostRow>>, { overwrite: false })

          // Property: row count unchanged
          expect(state.costRows.length).toBe(countAfterFirst)

          // Property: no new rows added
          expect(r2.added).toBe(0)

          // Property: all field values unchanged
          for (const orig of valuesAfterFirst) {
            const current = state.costRows.find(
              r => normalizeInvesteeName(r.investeeName) === orig.name,
            )
            expect(current).toBeDefined()
            if (current) {
              expect(current.openingAmount).toBe(orig.opening)
              expect(current.increaseAmount).toBe(orig.increase)
              expect(current.decreaseAmount).toBe(orig.decrease)
            }
          }
        },
      ),
      { numRuns: 20 },
    )
  })
})
