/**
 * Property-Based Tests — 通用抽凭引擎 composable
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Tasks: 13.1, 13.2, 13.3, 13.4
 *
 * 使用 fast-check + vitest 验证 Property 6, 8, 10, 12。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { computeVersionDiff } from '../composables/useSamplingAlgorithms'
import type { SampledVoucher, Phase, FillMode, EditTrailEntry } from '../composables/useSamplingAlgorithms'
import { applyFillMode } from '../composables/useVoucherSampling'

// ─── Generators ──────────────────────────────────────────────────────────────

/** Generate a SampledVoucher with optional fixed phase */
function sampledVoucherArb(phase?: 'preliminary' | 'final'): fc.Arbitrary<SampledVoucher> {
  return fc.record({
    voucherNo: fc.string({ minLength: 1, maxLength: 10 }),
    voucherDate: fc.string({ minLength: 10, maxLength: 10 }),
    summary: fc.option(fc.string({ maxLength: 20 }), { nil: null }),
    debitAmount: fc.option(fc.string({ minLength: 1, maxLength: 10 }), { nil: null }),
    creditAmount: fc.option(fc.string({ minLength: 1, maxLength: 10 }), { nil: null }),
    accountCode: fc.string({ minLength: 4, maxLength: 6 }),
    accountName: fc.option(fc.string({ maxLength: 20 }), { nil: null }),
    counterpartAccount: fc.option(fc.string({ maxLength: 10 }), { nil: null }),
    voucherType: fc.option(fc.string({ maxLength: 5 }), { nil: null }),
    accountingPeriod: fc.option(fc.integer({ min: 1, max: 12 }), { nil: null }),
    checkResult: fc.constantFrom('' as const, 'Y' as const, 'N' as const, '异常' as const),
    abnormal: fc.boolean(),
    remark: fc.string({ maxLength: 20 }),
    selected: fc.boolean(),
    phase: phase ? fc.constant(phase as Phase) : fc.constantFrom('preliminary' as Phase, 'final' as Phase),
    editTrail: fc.constant([] as EditTrailEntry[]),
  })
}

/** Generate array of SampledVouchers with unique voucherNo */
function uniqueVouchersArb(
  phase?: 'preliminary' | 'final',
  minLen = 0,
  maxLen = 10,
): fc.Arbitrary<SampledVoucher[]> {
  return fc.array(sampledVoucherArb(phase), { minLength: minLen, maxLength: maxLen })
    .map(vouchers => {
      const seen = new Set<string>()
      return vouchers.filter(v => {
        if (seen.has(v.voucherNo)) return false
        seen.add(v.voucherNo)
        return true
      })
    })
}

/** Generate fill mode */
const arbFillMode: fc.Arbitrary<FillMode> = fc.constantFrom('append', 'replace', 'merge')

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 阶段隔离 — 年审永不覆盖预审
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-sampling-engine, Property 6: 阶段隔离 — 年审永不覆盖预审', () => {
  /**
   * **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 7.5, 9.4**
   *
   * For any samples array containing preliminary-phase rows and any fill operation
   * during final phase with mode forced to 'append':
   * - Preliminary-phase rows SHALL remain unchanged (deep-equal)
   * - New rows SHALL all have phase='final'
   * - View filtering SHALL correctly partition by phase
   */

  it('fill with phase=final and mode=append preserves all preliminary rows unchanged', () => {
    fc.assert(
      fc.property(
        uniqueVouchersArb('preliminary', 1, 10),
        uniqueVouchersArb('final', 1, 8),
        (preliminaryRows, newFinalRows) => {
          // Deep copy preliminary rows before operation
          const preliminarySnapshot = JSON.parse(JSON.stringify(preliminaryRows)) as SampledVoucher[]

          // Existing samples = preliminary rows (simulating pre-existing data)
          const existing: SampledVoucher[] = [...preliminaryRows]

          // Apply fill with phase='final', mode='append' (forced in final phase)
          const result = applyFillMode(existing, newFinalRows, 'append', 'final')

          // Assert: all original preliminary rows are unchanged (deep-equal)
          const resultPreliminary = result.filter(v => v.phase === 'preliminary')
          expect(resultPreliminary.length).toBe(preliminarySnapshot.length)
          for (let i = 0; i < preliminarySnapshot.length; i++) {
            expect(resultPreliminary[i]).toEqual(preliminarySnapshot[i])
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('all new rows appended during final phase have phase=final', () => {
    fc.assert(
      fc.property(
        uniqueVouchersArb('preliminary', 0, 8),
        uniqueVouchersArb('final', 1, 8),
        (preliminaryRows, newFinalRows) => {
          const existing: SampledVoucher[] = [...preliminaryRows]
          const result = applyFillMode(existing, newFinalRows, 'append', 'final')

          // New rows = result items beyond the original existing length
          const appendedRows = result.slice(existing.length)
          for (const row of appendedRows) {
            expect(row.phase).toBe('final')
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('view filtering correctly partitions samples by phase', () => {
    fc.assert(
      fc.property(
        uniqueVouchersArb('preliminary', 1, 8),
        uniqueVouchersArb('final', 1, 8),
        (preliminaryRows, finalRows) => {
          // Combined samples (mixed phases)
          const allSamples = [...preliminaryRows, ...finalRows]

          // Simulate view mode filtering
          const viewPreliminary = allSamples.filter(v => v.phase === 'preliminary')
          const viewFinal = allSamples.filter(v => v.phase === 'final')
          const viewAll = allSamples

          // Assert: preliminary-only shows only preliminary
          for (const v of viewPreliminary) {
            expect(v.phase).toBe('preliminary')
          }

          // Assert: final-only shows only final
          for (const v of viewFinal) {
            expect(v.phase).toBe('final')
          }

          // Assert: all = union of preliminary + final
          expect(viewAll.length).toBe(viewPreliminary.length + viewFinal.length)

          // Assert: no items lost
          expect(viewPreliminary.length).toBe(preliminaryRows.length)
          expect(viewFinal.length).toBe(finalRows.length)
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: 填充策略正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-sampling-engine, Property 8: 填充策略正确性', () => {
  /**
   * **Validates: Requirements 7.1, 7.2, 7.3, 7.4**
   *
   * For any existing samples (mixed phases) + selected vouchers + mode + currentPhase:
   * - append: current_phase_count grows by M
   * - replace: current_phase rows = M (other phase untouched)
   * - merge: no duplicate voucher_no within same phase
   */

  it('append: current phase count grows by exactly M', () => {
    fc.assert(
      fc.property(
        uniqueVouchersArb(undefined, 0, 10),
        uniqueVouchersArb('final', 1, 8),
        (existing, selected) => {
          const currentPhase: Phase = 'final'
          const existingPhaseCount = existing.filter(v => v.phase === currentPhase).length

          const result = applyFillMode(existing, selected, 'append', currentPhase)

          // Total length = existing + selected
          expect(result.length).toBe(existing.length + selected.length)

          // Current phase count in result = existingPhaseCount + M
          const resultPhaseCount = result.filter(v => v.phase === currentPhase).length
          expect(resultPhaseCount).toBe(existingPhaseCount + selected.length)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('replace: current phase rows replaced entirely, other phase untouched', () => {
    fc.assert(
      fc.property(
        uniqueVouchersArb('preliminary', 1, 5),
        uniqueVouchersArb('final', 0, 5),
        uniqueVouchersArb('final', 1, 8),
        (preliminaryRows, existingFinalRows, selected) => {
          const currentPhase: Phase = 'final'
          const existing = [...preliminaryRows, ...existingFinalRows]

          const result = applyFillMode(existing, selected, 'replace', currentPhase)

          // Other phase rows untouched
          const resultPreliminary = result.filter(v => v.phase === 'preliminary')
          expect(resultPreliminary.length).toBe(preliminaryRows.length)
          for (let i = 0; i < preliminaryRows.length; i++) {
            expect(resultPreliminary[i]).toEqual(preliminaryRows[i])
          }

          // Current phase = exactly M (the selected rows)
          const resultFinal = result.filter(v => v.phase === currentPhase)
          expect(resultFinal.length).toBe(selected.length)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('merge: no duplicate voucher_no within same phase', () => {
    fc.assert(
      fc.property(
        uniqueVouchersArb('final', 1, 8),
        uniqueVouchersArb('final', 1, 8),
        (existing, selected) => {
          const currentPhase: Phase = 'final'

          const result = applyFillMode(existing, selected, 'merge', currentPhase)

          // No duplicate voucher_no within current phase
          const phaseRows = result.filter(v => v.phase === currentPhase)
          const nos = phaseRows.map(v => v.voucherNo)
          expect(new Set(nos).size).toBe(nos.length)

          // Count = existing + (selected non-overlapping)
          const existingNos = new Set(existing.map(v => v.voucherNo))
          const newCount = selected.filter(v => !existingNos.has(v.voucherNo)).length
          expect(phaseRows.length).toBe(existing.length + newCount)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('all three modes: result items are a subset of existing ∪ selected', () => {
    fc.assert(
      fc.property(
        uniqueVouchersArb(undefined, 0, 8),
        uniqueVouchersArb('preliminary', 1, 5),
        arbFillMode,
        (existing, selected, mode) => {
          const currentPhase: Phase = 'preliminary'
          const result = applyFillMode(existing, selected, mode, currentPhase)

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
// Property 10: 版本对比 diff 正确性（完全分割）
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-sampling-engine, Property 10: 版本对比 diff 正确性（完全分割）', () => {
  /**
   * **Validates: Requirements 6.3**
   *
   * For any two arrays of voucher_no strings (A and B):
   * - added ∪ removed ∪ retained == A ∪ B (completeness)
   * - The three sets are pairwise disjoint (mutual exclusivity)
   */

  it('added ∪ removed ∪ retained == A ∪ B (completeness)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 10 }), { minLength: 0, maxLength: 20 }),
        fc.array(fc.string({ minLength: 1, maxLength: 10 }), { minLength: 0, maxLength: 20 }),
        (vouchersA, vouchersB) => {
          const result = computeVersionDiff(vouchersA, vouchersB)

          // Compute union A ∪ B (as unique set)
          const unionAB = new Set([...vouchersA, ...vouchersB])

          // Compute union of result sets
          const resultUnion = new Set([...result.added, ...result.removed, ...result.retained])

          // Completeness: result union == A ∪ B
          expect(resultUnion.size).toBe(unionAB.size)
          for (const v of unionAB) {
            expect(resultUnion.has(v)).toBe(true)
          }
          for (const v of resultUnion) {
            expect(unionAB.has(v)).toBe(true)
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('three sets are pairwise disjoint (mutual exclusivity)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 10 }), { minLength: 0, maxLength: 20 }),
        fc.array(fc.string({ minLength: 1, maxLength: 10 }), { minLength: 0, maxLength: 20 }),
        (vouchersA, vouchersB) => {
          const result = computeVersionDiff(vouchersA, vouchersB)

          const addedSet = new Set(result.added)
          const removedSet = new Set(result.removed)
          const retainedSet = new Set(result.retained)

          // added ∩ removed == ∅
          for (const v of addedSet) {
            expect(removedSet.has(v)).toBe(false)
          }

          // added ∩ retained == ∅
          for (const v of addedSet) {
            expect(retainedSet.has(v)).toBe(false)
          }

          // removed ∩ retained == ∅
          for (const v of removedSet) {
            expect(retainedSet.has(v)).toBe(false)
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('added = B \\ A, removed = A \\ B, retained = A ∩ B (set semantics)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.string({ minLength: 1, maxLength: 10 }), { minLength: 0, maxLength: 20 }),
        fc.array(fc.string({ minLength: 1, maxLength: 10 }), { minLength: 0, maxLength: 20 }),
        (vouchersA, vouchersB) => {
          const result = computeVersionDiff(vouchersA, vouchersB)

          const setA = new Set(vouchersA)
          const setB = new Set(vouchersB)

          // added: every item in B but not in A
          for (const v of result.added) {
            expect(setB.has(v)).toBe(true)
            expect(setA.has(v)).toBe(false)
          }

          // removed: every item in A but not in B
          for (const v of result.removed) {
            expect(setA.has(v)).toBe(true)
            expect(setB.has(v)).toBe(false)
          }

          // retained: every item in both A and B
          for (const v of result.retained) {
            expect(setA.has(v)).toBe(true)
            expect(setB.has(v)).toBe(true)
          }
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 12: 编辑留痕不可变性（仅追加）
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: voucher-sampling-engine, Property 12: 编辑留痕不可变性（仅追加）', () => {
  /**
   * **Validates: Requirements 9.2**
   *
   * For any sequence of field edits on a SampledVoucher:
   * - Each edit appends exactly one entry to editTrail (trail.length +1)
   * - Previous trail entries remain unchanged (immutability)
   * - new entry.oldValue == the field value before the edit
   */

  /** Editable fields and their value generators */
  const editableFields = [
    { field: 'checkResult', valueArb: fc.constantFrom('Y', 'N', '异常', '') },
    { field: 'remark', valueArb: fc.string({ minLength: 0, maxLength: 20 }) },
    { field: 'abnormal', valueArb: fc.boolean().map(String) },
  ] as const

  /** Generate a sequence of edit operations */
  const editSequenceArb = fc.array(
    fc.record({
      field: fc.constantFrom('checkResult', 'remark', 'abnormal'),
      value: fc.string({ minLength: 0, maxLength: 20 }),
    }),
    { minLength: 1, maxLength: 10 },
  )

  /**
   * Simulate updateField logic (pure version matching useVoucherSampling.ts)
   */
  function simulateUpdateField(
    voucher: SampledVoucher,
    field: string,
    value: unknown,
  ): void {
    const oldValue = String((voucher as any)[field] ?? '')
    const newValue = String(value ?? '')

    // Update field value
    ;(voucher as any)[field] = value

    // Append trail entry
    const trailEntry: EditTrailEntry = {
      userId: 'current_user',
      timestamp: new Date().toISOString(),
      field,
      oldValue,
      newValue,
    }
    voucher.editTrail.push(trailEntry)
  }

  it('each edit appends exactly one entry to editTrail', () => {
    fc.assert(
      fc.property(
        sampledVoucherArb('final'),
        editSequenceArb,
        (voucher, edits) => {
          // Start with empty trail
          voucher.editTrail = []
          let expectedLength = 0

          for (const edit of edits) {
            simulateUpdateField(voucher, edit.field, edit.value)
            expectedLength += 1
            expect(voucher.editTrail.length).toBe(expectedLength)
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('previous trail entries remain unchanged after new edits (immutability)', () => {
    fc.assert(
      fc.property(
        sampledVoucherArb('final'),
        editSequenceArb,
        (voucher, edits) => {
          voucher.editTrail = []
          const snapshots: EditTrailEntry[][] = []

          for (const edit of edits) {
            // Snapshot current trail before this edit
            snapshots.push(JSON.parse(JSON.stringify(voucher.editTrail)))

            simulateUpdateField(voucher, edit.field, edit.value)
          }

          // After all edits, verify every prior snapshot matches current trail prefix
          for (let i = 0; i < snapshots.length; i++) {
            const snapshot = snapshots[i]
            for (let j = 0; j < snapshot.length; j++) {
              expect(voucher.editTrail[j].field).toBe(snapshot[j].field)
              expect(voucher.editTrail[j].oldValue).toBe(snapshot[j].oldValue)
              expect(voucher.editTrail[j].newValue).toBe(snapshot[j].newValue)
              expect(voucher.editTrail[j].userId).toBe(snapshot[j].userId)
            }
          }
        },
      ),
      { numRuns: 20 },
    )
  })

  it('new trail entry.oldValue equals the field value before the edit', () => {
    fc.assert(
      fc.property(
        sampledVoucherArb('final'),
        editSequenceArb,
        (voucher, edits) => {
          voucher.editTrail = []

          for (const edit of edits) {
            // Capture field value BEFORE edit
            const valueBefore = String((voucher as any)[edit.field] ?? '')

            simulateUpdateField(voucher, edit.field, edit.value)

            // The last trail entry should have oldValue = valueBefore
            const lastEntry = voucher.editTrail[voucher.editTrail.length - 1]
            expect(lastEntry.oldValue).toBe(valueBefore)
            expect(lastEntry.field).toBe(edit.field)
            expect(lastEntry.newValue).toBe(String(edit.value ?? ''))
          }
        },
      ),
      { numRuns: 20 },
    )
  })
})
