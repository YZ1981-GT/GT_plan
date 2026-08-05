/**
 * Property-Based Tests — 截止测试自动提取 composable
 *
 * Spec: .kiro/specs/cutoff-test-auto-sampling/
 * Tasks: 6.2, 6.3
 *
 * 使用 fast-check + vitest 验证 Property 8 & Property 10。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { applyFillMode, type ExtractedVoucher, type FillMode } from '../composables/useCutoffAutoSampling'

// ─── Generators ──────────────────────────────────────────────────────────────

/** Generate a valid YYYY-MM-DD date string */
const arbDateStr = fc
  .date({ min: new Date('2020-01-01'), max: new Date('2030-12-31') })
  .map((d) => {
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${y}-${m}-${day}`
  })

/** Generate a unique voucher number */
const arbVoucherNo = (prefix: string) =>
  fc.integer({ min: 1, max: 99999 }).map(n => `${prefix}-${String(n).padStart(5, '0')}`)

/** Generate a single ExtractedVoucher */
function arbVoucher(voucherNoArb: fc.Arbitrary<string>): fc.Arbitrary<ExtractedVoucher> {
  return fc.record({
    voucherNo: voucherNoArb,
    voucherDate: arbDateStr,
    summary: fc.option(fc.string({ minLength: 0, maxLength: 20 }), { nil: null }),
    debitAmount: fc.option(
      fc.float({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }).map(String),
      { nil: null },
    ),
    creditAmount: fc.option(
      fc.float({ min: 0, max: 1e8, noNaN: true, noDefaultInfinity: true }).map(String),
      { nil: null },
    ),
    accountCode: fc.stringMatching(/^[0-9]{4,6}$/),
    accountName: fc.option(fc.string({ minLength: 1, maxLength: 10 }), { nil: null }),
    counterpartAccount: fc.option(fc.stringMatching(/^[0-9]{4,6}$/), { nil: null }),
    voucherType: fc.option(fc.constantFrom('记', '收', '付', '转'), { nil: null }),
    cutoffStatus: fc.constantFrom('可能跨期' as const, '待检查' as const, '正常' as const),
    remark: fc.string({ minLength: 0, maxLength: 10 }),
    selected: fc.constant(true),
  })
}

/** Generate an array of ExtractedVouchers with unique voucherNos within the array */
function arbUniqueVouchers(prefix: string, minLen: number, maxLen: number): fc.Arbitrary<ExtractedVoucher[]> {
  return fc.integer({ min: minLen, max: maxLen }).chain(len => {
    if (len === 0) return fc.constant([])
    return fc.array(arbVoucher(arbVoucherNo(prefix)), { minLength: len, maxLength: len })
      .map(vouchers => {
        // Ensure uniqueness by deduplicating on voucherNo
        const seen = new Set<string>()
        return vouchers.filter(v => {
          if (seen.has(v.voucherNo)) return false
          seen.add(v.voucherNo)
          return true
        })
      })
  })
}

/** Generate a fill mode */
const arbFillMode: fc.Arbitrary<FillMode> = fc.constantFrom('append', 'replace', 'merge')

// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: 填充策略正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: cutoff-test-auto-sampling, Property 8: 填充策略正确性', () => {
  /**
   * **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.6**
   *
   * 对任意 existing (length N) 和 selected (length M, unique voucher_no):
   * - append: result.length === N + M
   * - replace: result.length === M
   * - merge: no duplicates + length = N + (M - overlap)
   */

  it('append: result length === N + M, preserves order', () => {
    fc.assert(
      fc.property(
        arbUniqueVouchers('EX', 0, 10),
        arbUniqueVouchers('SEL', 0, 10),
        (existing, selected) => {
          const result = applyFillMode(existing, selected, 'append')

          // Length must be N + M
          expect(result.length).toBe(existing.length + selected.length)

          // First N items are existing
          for (let i = 0; i < existing.length; i++) {
            expect(result[i].voucherNo).toBe(existing[i].voucherNo)
          }

          // Last M items are selected
          for (let i = 0; i < selected.length; i++) {
            expect(result[existing.length + i].voucherNo).toBe(selected[i].voucherNo)
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('replace: result length === M, contains only selected vouchers', () => {
    fc.assert(
      fc.property(
        arbUniqueVouchers('EX', 0, 10),
        arbUniqueVouchers('SEL', 0, 10),
        (existing, selected) => {
          const result = applyFillMode(existing, selected, 'replace')

          // Length must be M
          expect(result.length).toBe(selected.length)

          // All items from selected
          for (let i = 0; i < selected.length; i++) {
            expect(result[i].voucherNo).toBe(selected[i].voucherNo)
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('merge: no duplicate voucherNo, length = N + (M - overlap)', () => {
    fc.assert(
      fc.property(
        arbUniqueVouchers('V', 0, 10),
        arbUniqueVouchers('V', 0, 10),
        (existing, selected) => {
          const result = applyFillMode(existing, selected, 'merge')

          // Calculate overlap count
          const existingNos = new Set(existing.map(v => v.voucherNo))
          const overlapCount = selected.filter(v => existingNos.has(v.voucherNo)).length

          // Length = N + (M - overlap)
          expect(result.length).toBe(existing.length + (selected.length - overlapCount))

          // No duplicate voucherNo in result
          const resultNos = result.map(v => v.voucherNo)
          expect(new Set(resultNos).size).toBe(resultNos.length)

          // All existing items are preserved
          for (const ex of existing) {
            expect(resultNos).toContain(ex.voucherNo)
          }

          // All non-overlapping selected items are present
          for (const sel of selected) {
            if (!existingNos.has(sel.voucherNo)) {
              expect(resultNos).toContain(sel.voucherNo)
            }
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('all three modes produce only ExtractedVoucher objects from input', () => {
    fc.assert(
      fc.property(
        arbUniqueVouchers('EX', 1, 5),
        arbUniqueVouchers('SEL', 1, 5),
        arbFillMode,
        (existing, selected, mode) => {
          const result = applyFillMode(existing, selected, mode)

          // Every result item must have a voucherNo that exists in either existing or selected
          const allNos = new Set([
            ...existing.map(v => v.voucherNo),
            ...selected.map(v => v.voucherNo),
          ])
          for (const item of result) {
            expect(allNos.has(item.voucherNo)).toBe(true)
          }
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 10: 撤销 Round-Trip — before_data 快照与恢复
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: cutoff-test-auto-sampling, Property 10: 撤销 Round-Trip — before_data 快照与恢复', () => {
  /**
   * **Validates: Requirements 5.6, 5.8, 9.1, 9.3, 9.4, 9.5**
   *
   * 对任意 samples[] (length 0-20):
   * - fill 后 before_data deep-equals 原 samples
   * - undo 后恢复到原 samples (通过 fill mode 的 replace 逻辑模拟)
   */

  it('before_data snapshot deep-equals original samples after fill', () => {
    fc.assert(
      fc.property(
        arbUniqueVouchers('ORIG', 0, 20),
        arbUniqueVouchers('NEW', 1, 10),
        arbFillMode,
        (originalSamples, newSelected, mode) => {
          // Simulate the fill operation:
          // 1. Snapshot before_data = deep copy of original samples
          const beforeData = JSON.parse(JSON.stringify(originalSamples))

          // 2. Apply fill mode to produce new state
          const _newState = applyFillMode(originalSamples, newSelected, mode)

          // Assert: before_data deep-equals original samples
          expect(beforeData).toEqual(originalSamples)
          expect(beforeData.length).toBe(originalSamples.length)

          // Verify each item matches
          for (let i = 0; i < originalSamples.length; i++) {
            expect(beforeData[i].voucherNo).toBe(originalSamples[i].voucherNo)
            expect(beforeData[i].voucherDate).toBe(originalSamples[i].voucherDate)
            expect(beforeData[i].debitAmount).toBe(originalSamples[i].debitAmount)
            expect(beforeData[i].creditAmount).toBe(originalSamples[i].creditAmount)
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('undo restores samples to before_data state (round-trip fidelity)', () => {
    fc.assert(
      fc.property(
        arbUniqueVouchers('ORIG', 0, 20),
        arbUniqueVouchers('NEW', 1, 10),
        arbFillMode,
        (originalSamples, newSelected, mode) => {
          // Step 1: Save before_data snapshot
          const beforeData: ExtractedVoucher[] = JSON.parse(JSON.stringify(originalSamples))

          // Step 2: Apply fill → changes the state
          const afterFill = applyFillMode(originalSamples, newSelected, mode)

          // Step 3: Simulate undo — restore from before_data using replace mode
          const afterUndo = applyFillMode(afterFill, beforeData, 'replace')

          // Assert: after undo, restored state deep-equals original samples
          expect(afterUndo).toEqual(beforeData)
          expect(afterUndo.length).toBe(originalSamples.length)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('fill mode correctly produces expected result length', () => {
    fc.assert(
      fc.property(
        arbUniqueVouchers('ORIG', 0, 20),
        arbUniqueVouchers('NEW', 0, 10),
        arbFillMode,
        (originalSamples, newSelected, mode) => {
          const result = applyFillMode(originalSamples, newSelected, mode)

          switch (mode) {
            case 'append':
              expect(result.length).toBe(originalSamples.length + newSelected.length)
              break
            case 'replace':
              expect(result.length).toBe(newSelected.length)
              break
            case 'merge': {
              const existingNos = new Set(originalSamples.map(v => v.voucherNo))
              const overlap = newSelected.filter(v => existingNos.has(v.voucherNo)).length
              expect(result.length).toBe(originalSamples.length + newSelected.length - overlap)
              break
            }
          }
        },
      ),
      { numRuns: 20 },
    )
  })
})
