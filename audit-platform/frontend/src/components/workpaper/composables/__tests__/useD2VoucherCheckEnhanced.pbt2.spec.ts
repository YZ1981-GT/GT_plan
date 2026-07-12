/**
 * Property-Based Tests — Storage prefix isolation (P3) & View mode switch (P4)
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 1.3
 *
 * **Validates: Requirements 1.4, 3.4**
 *
 * Properties:
 * - Property 3: Storage prefix isolation — 区1 item_id 以 D2-vc-current- 开头，
 *   区2 以 D2-vc-post- 开头，互不污染
 * - Property 4: View mode switch preserves data — 切换矩阵/卡片视图不影响底层行数据
 */
import { describe, it, expect, vi } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'
import {
  useD2VoucherCheckEnhanced,
  type VoucherCheckRow,
  type UseD2VoucherCheckEnhancedOptions,
} from '../useD2VoucherCheckEnhanced'

// Mock inject/onBeforeUnmount to avoid Vue runtime errors in unit tests
vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...(actual as any),
    inject: () => null,
    onBeforeUnmount: () => {},
  }
})

const RUNS = { numRuns: 100 }

// ─── Shared Generators ─────────────────────────────────────────────────────

/** Generate a minimal VoucherCheckRow-like record for testing */
const arbVoucherCheckRow: fc.Arbitrary<VoucherCheckRow> = fc.record({
  rowId: fc.string({ minLength: 1, maxLength: 16 }),
  seq: fc.nat({ max: 999 }),
  customerName: fc.string({ maxLength: 20 }),
  voucherDate: fc.constantFrom('2025-06-15', '2025-12-31', '2026-01-05', '2024-03-20', ''),
  voucherNo: fc.string({ minLength: 1, maxLength: 12 }),
  businessContent: fc.string({ maxLength: 30 }),
  counterpartAccount: fc.string({ maxLength: 10 }),
  counterpartDetail: fc.string({ maxLength: 10 }),
  debitAmount: fc.float({ min: 0, max: 9999999, noNaN: true }),
  creditAmount: fc.float({ min: 0, max: 9999999, noNaN: true }),
  supportingDoc: fc.string({ maxLength: 20 }),
  check1: fc.string({ maxLength: 10 }),
  check2: fc.string({ maxLength: 10 }),
  check3: fc.string({ maxLength: 10 }),
  check4: fc.string({ maxLength: 10 }),
  check5: fc.string({ maxLength: 10 }),
  indexRef: fc.string({ maxLength: 10 }),
  isAbnormal: fc.constantFrom('', '是', '否'),
  remark: fc.string({ maxLength: 20 }),
  attachments: fc.constant([]),
  ocrResult: fc.constant(undefined),
  source: fc.constantFrom('手动', '自动抽凭', ''),
})

/** Generate a non-empty array of rows */
const arbRowArray = fc.array(arbVoucherCheckRow, { minLength: 1, maxLength: 10 })

/** Generate view mode toggle sequences */
const arbViewModeSequence = fc.array(
  fc.constantFrom('matrix' as const, 'card' as const),
  { minLength: 1, maxLength: 20 },
)

// ─── Helpers ───────────────────────────────────────────────────────────────

function createOptions(): UseD2VoucherCheckEnhancedOptions {
  return {
    allResponses: ref(new Map()),
    isReadonly: ref(false),
    bsDate: ref('2025-12-31'),
  }
}

/** Deep clone rows for comparison (strip non-serializable fields) */
function serializeRows(rows: VoucherCheckRow[]): string {
  return JSON.stringify(rows.map(r => ({
    rowId: r.rowId,
    seq: r.seq,
    customerName: r.customerName,
    voucherDate: r.voucherDate,
    voucherNo: r.voucherNo,
    businessContent: r.businessContent,
    counterpartAccount: r.counterpartAccount,
    counterpartDetail: r.counterpartDetail,
    debitAmount: r.debitAmount,
    creditAmount: r.creditAmount,
    supportingDoc: r.supportingDoc,
    check1: r.check1,
    check2: r.check2,
    check3: r.check3,
    check4: r.check4,
    check5: r.check5,
    indexRef: r.indexRef,
    isAbnormal: r.isAbnormal,
    remark: r.remark,
  })))
}

// ─── Property 3: Storage prefix isolation ──────────────────────────────────
// Feature: d2-7-voucher-check-enhancement, Property 3: Storage prefix isolation

describe('Property 3: Storage prefix isolation', () => {
  it(
    'zone "current" rows serialize to item_id with prefix D2-vc-current-, ' +
    'zone "post" rows serialize to item_id with prefix D2-vc-post-',
    () => {
      fc.assert(
        fc.property(
          arbRowArray,
          arbRowArray,
          (currentRowData, postRowData) => {
            const options = createOptions()
            const {
              currentRows,
              postRows,
              saveToResponses,
            } = useD2VoucherCheckEnhanced(options)

            // Seed both zones with arbitrary data
            currentRows.value = currentRowData.map((r, i) => ({ ...r, seq: i + 1 }))
            postRows.value = postRowData.map((r, i) => ({ ...r, seq: i + 1 }))

            // Persist
            saveToResponses()

            // Verify: all keys in allResponses map
            const allKeys = [...options.allResponses.value.keys()]

            // Must have exactly 2 entries for rows
            const currentKeys = allKeys.filter(k => k.startsWith('D2-vc-current-'))
            const postKeys = allKeys.filter(k => k.startsWith('D2-vc-post-'))

            // At least one key per zone
            expect(currentKeys.length).toBeGreaterThanOrEqual(1)
            expect(postKeys.length).toBeGreaterThanOrEqual(1)

            // No cross-contamination: no current data in post keys
            for (const key of currentKeys) {
              expect(key.startsWith('D2-vc-current-')).toBe(true)
              expect(key.startsWith('D2-vc-post-')).toBe(false)
            }
            for (const key of postKeys) {
              expect(key.startsWith('D2-vc-post-')).toBe(true)
              expect(key.startsWith('D2-vc-current-')).toBe(false)
            }

            // Verify content isolation: current key contains current data, post key contains post data
            const currentEntry = options.allResponses.value.get('D2-vc-current-rows')
            const postEntry = options.allResponses.value.get('D2-vc-post-rows')

            expect(currentEntry).toBeDefined()
            expect(postEntry).toBeDefined()

            const parsedCurrent = JSON.parse(currentEntry.remark)
            const parsedPost = JSON.parse(postEntry.remark)

            // Count must match
            expect(parsedCurrent.length).toBe(currentRowData.length)
            expect(parsedPost.length).toBe(postRowData.length)

            // Spot-check: first row voucherNo should match
            if (currentRowData.length > 0) {
              expect(parsedCurrent[0].voucherNo).toBe(currentRowData[0].voucherNo)
            }
            if (postRowData.length > 0) {
              expect(parsedPost[0].voucherNo).toBe(postRowData[0].voucherNo)
            }
          },
        ),
        RUNS,
      )
    },
  )

  it(
    'no key without the correct zone prefix exists after save',
    () => {
      fc.assert(
        fc.property(
          arbRowArray,
          (rowData) => {
            const options = createOptions()
            const { currentRows, postRows, saveToResponses } = useD2VoucherCheckEnhanced(options)

            // Only populate current zone
            currentRows.value = rowData.map((r, i) => ({ ...r, seq: i + 1 }))
            postRows.value = [] // post zone empty

            saveToResponses()

            // All keys must start with D2-vc- prefix (either current or post)
            const allKeys = [...options.allResponses.value.keys()]
            for (const key of allKeys) {
              expect(
                key.startsWith('D2-vc-current-') || key.startsWith('D2-vc-post-'),
              ).toBe(true)
            }
          },
        ),
        RUNS,
      )
    },
  )
})

// ─── Property 4: View mode switch preserves data ───────────────────────────
// Feature: d2-7-voucher-check-enhancement, Property 4: View mode switch preserves data

describe('Property 4: View mode switch preserves data', () => {
  it(
    'toggling viewMode between matrix and card any number of times does not alter row data',
    () => {
      fc.assert(
        fc.property(
          arbRowArray,
          arbRowArray,
          arbViewModeSequence,
          (currentRowData, postRowData, toggleSequence) => {
            const options = createOptions()
            const {
              currentRows,
              postRows,
              viewMode,
              switchViewMode,
            } = useD2VoucherCheckEnhanced(options)

            // Seed both zones
            currentRows.value = currentRowData.map((r, i) => ({ ...r, seq: i + 1 }))
            postRows.value = postRowData.map((r, i) => ({ ...r, seq: i + 1 }))

            // Snapshot before toggles
            const currentBefore = serializeRows(currentRows.value)
            const postBefore = serializeRows(postRows.value)

            // Apply toggle sequence
            for (const mode of toggleSequence) {
              switchViewMode(mode)
            }

            // Snapshot after toggles
            const currentAfter = serializeRows(currentRows.value)
            const postAfter = serializeRows(postRows.value)

            // Row data must be identical
            expect(currentAfter).toBe(currentBefore)
            expect(postAfter).toBe(postBefore)

            // viewMode should be the last value in the sequence
            expect(viewMode.value).toBe(toggleSequence[toggleSequence.length - 1])
          },
        ),
        RUNS,
      )
    },
  )

  it(
    'switching viewMode does not change the length of either zone array',
    () => {
      fc.assert(
        fc.property(
          arbRowArray,
          fc.nat({ max: 10 }),
          (rowData, toggleCount) => {
            const options = createOptions()
            const {
              currentRows,
              postRows,
              switchViewMode,
            } = useD2VoucherCheckEnhanced(options)

            currentRows.value = rowData.map((r, i) => ({ ...r, seq: i + 1 }))

            const lenBefore = currentRows.value.length
            const postLenBefore = postRows.value.length

            // Toggle N times alternating
            for (let i = 0; i < toggleCount; i++) {
              switchViewMode(i % 2 === 0 ? 'card' : 'matrix')
            }

            expect(currentRows.value.length).toBe(lenBefore)
            expect(postRows.value.length).toBe(postLenBefore)
          },
        ),
        RUNS,
      )
    },
  )
})
