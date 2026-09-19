/**
 * Property-Based Tests — D2-7 凭证检查表增强（Zone Isolation + Date Classification）
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 1.2
 *
 * 使用 fast-check + vitest，numRuns=100 验证：
 * - Property 1: Zone data isolation on switch — 编辑区A后切换到B再切回A，数据不变
 * - Property 2: Voucher date-based zone classification — classifyVoucherToZone 纯函数正确分类
 *
 * **Validates: Requirements 1.2, 1.5, 10.1**
 */
import { describe, it, expect, vi } from 'vitest'
import * as fc from 'fast-check'
import { ref } from 'vue'
import {
  classifyVoucherToZone,
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

/** Generate a valid YYYY-MM-DD date string within a reasonable range */
const arbDateStr: fc.Arbitrary<string> = fc
  .integer({ min: 2020, max: 2030 })
  .chain((year) =>
    fc.integer({ min: 1, max: 12 }).chain((month) =>
      fc.integer({ min: 1, max: 28 }).map((day) => {
        const m = String(month).padStart(2, '0')
        const d = String(day).padStart(2, '0')
        return `${year}-${m}-${d}`
      }),
    ),
  )

/** Generate an arbitrary VoucherCheckRow with random field values */
function arbVoucherCheckRow(seq: number): fc.Arbitrary<VoucherCheckRow> {
  return fc.record({
    rowId: fc.string({ minLength: 5, maxLength: 12 }).map((s) => `vcr-${s}`),
    seq: fc.constant(seq),
    customerName: fc.string({ minLength: 0, maxLength: 20 }),
    voucherDate: fc.oneof(arbDateStr, fc.constant('')),
    voucherNo: fc.string({ minLength: 0, maxLength: 15 }),
    businessContent: fc.string({ minLength: 0, maxLength: 30 }),
    counterpartAccount: fc.string({ minLength: 0, maxLength: 10 }),
    counterpartDetail: fc.string({ minLength: 0, maxLength: 10 }),
    debitAmount: fc.integer({ min: 0, max: 9999999 }),
    creditAmount: fc.integer({ min: 0, max: 9999999 }),
    supportingDoc: fc.string({ minLength: 0, maxLength: 10 }),
    check1: fc.string({ minLength: 0, maxLength: 10 }),
    check2: fc.string({ minLength: 0, maxLength: 10 }),
    check3: fc.string({ minLength: 0, maxLength: 10 }),
    check4: fc.string({ minLength: 0, maxLength: 10 }),
    check5: fc.string({ minLength: 0, maxLength: 10 }),
    indexRef: fc.string({ minLength: 0, maxLength: 10 }),
    isAbnormal: fc.constantFrom('', '是', '否'),
    remark: fc.string({ minLength: 0, maxLength: 20 }),
    attachments: fc.constant([]),
    ocrResult: fc.constant(undefined),
    source: fc.constantFrom('手动', '自动抽凭', ''),
  })
}

/** Generate an array of VoucherCheckRows with sequential seq numbers */
function arbVoucherCheckRows(minLen = 0, maxLen = 5): fc.Arbitrary<VoucherCheckRow[]> {
  return fc
    .integer({ min: minLen, max: maxLen })
    .chain((len) =>
      fc.tuple(...Array.from({ length: len }, (_, i) => arbVoucherCheckRow(i + 1))),
    )
    .map((rows) => rows as unknown as VoucherCheckRow[])
}

// ═══════════════════════════════════════════════════════════════════════════
// Property 1: Zone data isolation on switch
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: d2-7-voucher-check-enhancement, Property 1: Zone data isolation on switch', () => {
  /** **Validates: Requirements 1.2** */

  it('editing zone A, switching to B and back to A preserves zone A data exactly', () => {
    fc.assert(
      fc.property(
        // Generate random rows to pre-fill into currentRows (zone A)
        fc.array(arbVoucherCheckRow(1), { minLength: 1, maxLength: 5 }),
        // Generate random rows to pre-fill into postRows (zone B)
        fc.array(arbVoucherCheckRow(1), { minLength: 0, maxLength: 5 }),
        (zoneARows, zoneBRows) => {
          // Re-sequence
          const seqA = zoneARows.map((r, i) => ({ ...r, seq: i + 1 }))
          const seqB = zoneBRows.map((r, i) => ({ ...r, seq: i + 1 }))

          const options: UseD2VoucherCheckEnhancedOptions = {
            allResponses: ref(new Map()),
            isReadonly: ref(false),
            bsDate: ref('2025-12-31'),
          }

          const { currentRows, postRows, activeZone, switchZone } =
            useD2VoucherCheckEnhanced(options)

          // Seed zone A (current) data
          currentRows.value = seqA.map((r) => ({ ...r }))
          // Seed zone B (post) data
          postRows.value = seqB.map((r) => ({ ...r }))

          // Snapshot zone A before switch
          const snapshotA = JSON.stringify(currentRows.value)

          // Switch to zone B
          switchZone('post')
          expect(activeZone.value).toBe('post')

          // Switch back to zone A
          switchZone('current')
          expect(activeZone.value).toBe('current')

          // Zone A data must be identical
          expect(JSON.stringify(currentRows.value)).toBe(snapshotA)
        },
      ),
      RUNS,
    )
  })

  it('adding rows to zone B does not affect zone A data', () => {
    fc.assert(
      fc.property(
        fc.array(arbVoucherCheckRow(1), { minLength: 1, maxLength: 4 }),
        fc.integer({ min: 1, max: 3 }), // number of rows to add to zone B
        (zoneARows, addCount) => {
          const seqA = zoneARows.map((r, i) => ({ ...r, seq: i + 1 }))

          const options: UseD2VoucherCheckEnhancedOptions = {
            allResponses: ref(new Map()),
            isReadonly: ref(false),
            bsDate: ref('2025-12-31'),
          }

          const { currentRows, postRows, switchZone, addRow } =
            useD2VoucherCheckEnhanced(options)

          // Seed zone A data
          currentRows.value = seqA.map((r) => ({ ...r }))

          // Snapshot zone A
          const snapshotA = JSON.stringify(currentRows.value)

          // Switch to zone B and add rows
          switchZone('post')
          for (let i = 0; i < addCount; i++) {
            addRow()
          }

          // Zone B should have rows added
          expect(postRows.value).toHaveLength(addCount)

          // Zone A data must be unchanged
          expect(JSON.stringify(currentRows.value)).toBe(snapshotA)
        },
      ),
      RUNS,
    )
  })

  it('multiple zone switches preserve both zones data integrity', () => {
    fc.assert(
      fc.property(
        fc.array(arbVoucherCheckRow(1), { minLength: 1, maxLength: 3 }),
        fc.array(arbVoucherCheckRow(1), { minLength: 1, maxLength: 3 }),
        fc.array(fc.constantFrom('current' as const, 'post' as const), {
          minLength: 2,
          maxLength: 8,
        }),
        (zoneARows, zoneBRows, switchSequence) => {
          const seqA = zoneARows.map((r, i) => ({ ...r, seq: i + 1 }))
          const seqB = zoneBRows.map((r, i) => ({ ...r, seq: i + 1 }))

          const options: UseD2VoucherCheckEnhancedOptions = {
            allResponses: ref(new Map()),
            isReadonly: ref(false),
            bsDate: ref('2025-12-31'),
          }

          const { currentRows, postRows, switchZone } = useD2VoucherCheckEnhanced(options)

          // Seed both zones
          currentRows.value = seqA.map((r) => ({ ...r }))
          postRows.value = seqB.map((r) => ({ ...r }))

          const snapshotA = JSON.stringify(currentRows.value)
          const snapshotB = JSON.stringify(postRows.value)

          // Execute random switch sequence
          for (const zone of switchSequence) {
            switchZone(zone)
          }

          // Both zones must remain unchanged
          expect(JSON.stringify(currentRows.value)).toBe(snapshotA)
          expect(JSON.stringify(postRows.value)).toBe(snapshotB)
        },
      ),
      RUNS,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Property 2: Voucher date-based zone classification
// ═══════════════════════════════════════════════════════════════════════════

describe('Feature: d2-7-voucher-check-enhancement, Property 2: Voucher date-based zone classification', () => {
  /** **Validates: Requirements 1.5, 10.1** */

  it('voucherDate <= bsDate → "current"; voucherDate > bsDate → "post"', () => {
    fc.assert(
      fc.property(arbDateStr, arbDateStr, (voucherDate, bsDate) => {
        const result = classifyVoucherToZone(voucherDate, bsDate)
        if (voucherDate <= bsDate) {
          expect(result).toBe('current')
        } else {
          expect(result).toBe('post')
        }
      }),
      RUNS,
    )
  })

  it('empty voucherDate always returns "current"', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('', null as unknown as string),
        arbDateStr,
        (voucherDate, bsDate) => {
          const result = classifyVoucherToZone(voucherDate || '', bsDate)
          expect(result).toBe('current')
        },
      ),
      RUNS,
    )
  })

  it('empty bsDate always returns "current"', () => {
    fc.assert(
      fc.property(
        arbDateStr,
        fc.constantFrom('', null as unknown as string),
        (voucherDate, bsDate) => {
          const result = classifyVoucherToZone(voucherDate, bsDate || '')
          expect(result).toBe('current')
        },
      ),
      RUNS,
    )
  })

  it('boundary: voucherDate exactly equals bsDate → "current"', () => {
    fc.assert(
      fc.property(arbDateStr, (date) => {
        expect(classifyVoucherToZone(date, date)).toBe('current')
      }),
      RUNS,
    )
  })

  it('classification is deterministic for any input pair', () => {
    fc.assert(
      fc.property(
        fc.oneof(arbDateStr, fc.constant('')),
        fc.oneof(arbDateStr, fc.constant('')),
        (voucherDate, bsDate) => {
          const result1 = classifyVoucherToZone(voucherDate, bsDate)
          const result2 = classifyVoucherToZone(voucherDate, bsDate)
          expect(result1).toBe(result2)
          // Result is always one of the two valid values
          expect(['current', 'post']).toContain(result1)
        },
      ),
      RUNS,
    )
  })

  it('lexicographic string comparison aligns with date semantics for YYYY-MM-DD format', () => {
    fc.assert(
      fc.property(
        // Generate two dates where we know the ordering
        fc.integer({ min: 2020, max: 2030 }),
        fc.integer({ min: 1, max: 12 }),
        fc.integer({ min: 1, max: 28 }),
        fc.integer({ min: 1, max: 365 }), // days to add for "after" date
        (year, month, day, daysAfter) => {
          const m = String(month).padStart(2, '0')
          const d = String(day).padStart(2, '0')
          const bsDate = `${year}-${m}-${d}`

          // Create a date that is definitely after bsDate
          const base = new Date(`${year}-${m}-${d}T00:00:00`)
          base.setDate(base.getDate() + daysAfter)
          const afterYear = base.getFullYear()
          const afterMonth = String(base.getMonth() + 1).padStart(2, '0')
          const afterDay = String(base.getDate()).padStart(2, '0')
          const afterDate = `${afterYear}-${afterMonth}-${afterDay}`

          // afterDate should be classified as 'post'
          expect(classifyVoucherToZone(afterDate, bsDate)).toBe('post')
          // bsDate itself should be classified as 'current'
          expect(classifyVoucherToZone(bsDate, bsDate)).toBe('current')
        },
      ),
      RUNS,
    )
  })
})
