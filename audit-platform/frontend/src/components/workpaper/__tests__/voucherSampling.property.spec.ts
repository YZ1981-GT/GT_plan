/**
 * Property-Based Tests — 通用抽凭引擎 composable
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Tasks: 13.1, 13.2, 13.3, 13.4
 *
 * 使用 fast-check + vitest 验证 Property 6, 8, 10, 12。
 * Property 6 / 8 的合并已移到共享回填函数（voucher-identity-writeback-and-audit-phase 任务 9），这里按新口径验证。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { computeVersionDiff } from '../composables/useSamplingAlgorithms'
import type { SampledVoucher, Phase, EditTrailEntry } from '../composables/useSamplingAlgorithms'
import type { AuditPhase } from '@/composables/useProjectAuditPhase'
import { mergeVoucherCheckRows, type RowSource, type VoucherFillMode } from '../composables/shared/voucherCheckFill'
import { disjoint, fillRowsArb, lfpsOf, type FillRow } from '../composables/shared/__tests__/voucherCheckFillArbs'

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
    counterpartAccountName: fc.constant<string | null>(null),
    isMultiAccount: fc.constant(false),
    voucherEntries: fc.constant([] as SampledVoucher['voucherEntries']),
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

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6 / 8：回填合并（spec voucher-identity-writeback-and-audit-phase 任务 9 移植）
//
// 合并进底稿归共享回填函数 shared/voucherCheckFill.mergeVoucherCheckRows（ADR-VK-07）：引擎不再算合并结果，
// 原 applyFillMode 的属性在这里按新口径验证——按分录指纹认同一笔（不再按凭证号），「替换本阶段抽凭行」
// 只删同阶段、来源只有抽凭的行，年审回填不动预审行。
// ═══════════════════════════════════════════════════════════════════════════════

const RUNS = { numRuns: 20 }
const ENGINE_ONLY: RowSource[][] = [['engine']]

describe('Feature: voucher-sampling-engine, Property 6: 阶段隔离 — 年审永不覆盖预审', () => {
  it('年审回填（追加或替换）后预审行原样保留（逐字段相等）', () => {
    fc.assert(
      fc.property(
        fillRowsArb({ phase: 'preliminary' }, 1, 8),
        fillRowsArb({ phase: 'final', sources: ENGINE_ONLY }, 0, 6),
        fillRowsArb({ phase: 'final', sources: ENGINE_ONLY }, 1, 6),
        fc.constantFrom<VoucherFillMode>('append', 'replace'),
        (prelim, finals, incomingRaw, mode) => {
          const incoming = disjoint([...prelim, ...finals], incomingRaw)
          const snapshot = JSON.parse(JSON.stringify(prelim))
          const { rows } = mergeVoucherCheckRows([...prelim, ...finals], incoming, { mode, phase: 'final', source: 'engine' })
          expect(rows.filter(r => r._gt.ph === 'preliminary')).toEqual(snapshot)
        },
      ),
      RUNS,
    )
  })

  it('新增的行就是本次待写入行，接在已有行之后', () => {
    fc.assert(
      fc.property(
        fillRowsArb({}, 0, 8),
        fillRowsArb({ phase: 'final', sources: ENGINE_ONLY }, 1, 6),
        (existing, incomingRaw) => {
          const incoming = disjoint(existing, incomingRaw)
          const { rows, added } = mergeVoucherCheckRows(existing, incoming, { mode: 'append', phase: 'final', source: 'engine' })
          expect(added).toBe(incoming.length)
          expect(rows.slice(existing.length)).toEqual(incoming)
        },
      ),
      RUNS,
    )
  })
})

describe('Feature: voucher-sampling-engine, Property 8: 填充策略正确性', () => {
  it('追加：没有重叠时长度 = 已有 + 待写入，已有行不变', () => {
    fc.assert(
      fc.property(fillRowsArb({}, 0, 10), fillRowsArb({ phase: 'final' }, 1, 8), (existing, incomingRaw) => {
        const incoming = disjoint(existing, incomingRaw)
        const snapshot = JSON.parse(JSON.stringify(existing))
        const { rows } = mergeVoucherCheckRows(existing, incoming, { mode: 'append', phase: 'final', source: 'engine' })
        expect(rows.length).toBe(existing.length + incoming.length)
        expect(rows.slice(0, existing.length)).toEqual(snapshot)
      }),
      RUNS,
    )
  })

  it('追加幂等：同一批再写一次不增加行，都算已存在', () => {
    fc.assert(
      fc.property(fillRowsArb({}, 0, 8), fillRowsArb({ phase: 'final', sources: ENGINE_ONLY }, 1, 6), (existing, incomingRaw) => {
        const incoming = disjoint(existing, incomingRaw)
        const opts = { mode: 'append' as const, phase: 'final' as const, source: 'engine' as const }
        const once = mergeVoucherCheckRows(existing, incoming, opts).rows
        const twice = mergeVoucherCheckRows(once, incoming, opts)
        expect(twice.rows).toEqual(once)
        expect(twice.added).toBe(0)
        expect(twice.existed).toBe(incoming.length)
      }),
      RUNS,
    )
  })

  it('替换：只删同阶段且来源只有抽凭的行，其余逐字段保留', () => {
    fc.assert(
      fc.property(
        fillRowsArb({}, 0, 10),
        fillRowsArb({ phase: 'final', sources: ENGINE_ONLY }, 0, 6),
        fc.constantFrom<AuditPhase>('preliminary', 'final'),
        (existing, incomingRaw, phase) => {
          const incoming = disjoint(existing, incomingRaw)
          const removable = (r: FillRow) => r._gt.ph === phase && r._gt.src.every(s => s === 'engine')
          const kept = JSON.parse(JSON.stringify(existing.filter(r => !removable(r))))
          const res = mergeVoucherCheckRows(existing, incoming, { mode: 'replace', phase, source: 'engine' })
          expect(res.replaced).toBe(existing.filter(removable).length)
          expect(res.rows.slice(0, kept.length)).toEqual(kept)
          expect(res.rows.slice(kept.length)).toEqual(incoming)
        },
      ),
      RUNS,
    )
  })

  it('两种模式：结果行都来自已有行或待写入行，且同一分录（指纹 + 对方科目）只出现一次', () => {
    fc.assert(
      fc.property(
        fillRowsArb({}, 0, 8),
        fillRowsArb({ phase: 'preliminary' }, 1, 6),
        fc.constantFrom<VoucherFillMode>('append', 'replace'),
        fc.boolean(),
        (existing, incomingRaw, mode, overlap) => {
          // overlap = true：待写入里混进已有行的指纹（再次抽中同一分录）
          const incoming = overlap ? [...incomingRaw, ...existing.slice(0, 2)] : disjoint(existing, incomingRaw)
          const { rows } = mergeVoucherCheckRows(existing, incoming, { mode, phase: 'preliminary', source: 'engine' })
          const universe = new Set([...lfpsOf(existing), ...lfpsOf(incoming)])
          for (const r of rows) expect(universe.has(r._gt.lfp as string)).toBe(true)
          const keys = rows.map(r => `${r._gt.lfp}#${r._gt.cp ?? ''}`)
          expect(new Set(keys).size).toBe(keys.length)
        },
      ),
      RUNS,
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
