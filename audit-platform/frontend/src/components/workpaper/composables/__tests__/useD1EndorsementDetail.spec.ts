/**
 * Property-Based Tests — D1-8 贴现背书明细 composable
 *
 * Spec: .kiro/specs/d1-endorsement-discount/
 * Task: 5.2 (Property 10)
 *
 * 使用 fast-check + vitest（numRuns: 100）验证 useD1EndorsementDetail 的正确性属性：
 * - Property 10：从备查簿导入状态筛选正确性
 *   discount 表仅含 status==='已贴现' 行；endorse 表仅含 status==='已背书' 行；
 *   数量等于源中该状态行数；billAmount 从源 amount 保留（sum 校验）。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import {
  useD1EndorsementDetail,
  type UseD1EndorsementDetailOptions,
} from '../useD1EndorsementDetail'
import { emptyMemoRow, type MemoRow } from '../useD1MemoReconciliation'
import type { ChecklistResponse } from '../useD1FormData'

// Mock onBeforeUnmount to avoid lifecycle warnings when instantiating the
// composable outside of a mounted component (matches repo convention).
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return {
    ...actual,
    onBeforeUnmount: vi.fn(),
  }
})

// ─── Generators ──────────────────────────────────────────────────────────────

const statusArb = fc.constantFrom('持有', '已贴现', '已背书', '到期')

const finiteAmount = fc
  .double({ min: 0, max: 1e7, noNaN: true, noDefaultInfinity: true })
  .map((x) => x + 0)

/** MemoRow 生成器：以 emptyMemoRow('bank') 为基底，随机覆盖 status 与 amount */
const memoRowArb: fc.Arbitrary<MemoRow> = fc
  .record({
    status: statusArb,
    amount: finiteAmount,
  })
  .map(({ status, amount }) => {
    const base = emptyMemoRow('bank')
    return { ...base, status, amount } as MemoRow
  })

const tableArb = fc.constantFrom<'discount' | 'endorse'>('discount', 'endorse')

// ─── Instantiation helper ────────────────────────────────────────────────────

function mountComposable() {
  const allResponses = ref(new Map<string, ChecklistResponse>())
  const saveImmediate = vi.fn().mockResolvedValue(undefined)
  const options: UseD1EndorsementDetailOptions = {
    allResponses,
    wpId: ref('test-wp'),
    projectId: ref('test-proj'),
    saveImmediate,
    isReadonly: ref(false),
  }
  const api = useD1EndorsementDetail(options)
  return { api, allResponses, saveImmediate }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Task 5.2 — Property 10: 从备查簿导入状态筛选正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-endorsement-discount, Property 10: 从备查簿导入状态筛选正确性', () => {
  /**
   * **Validates: Requirements 17.1, 17.2**
   *
   * 对任意 MemoRow[] + 表选择：importFromMemo 后目标表所有行仅对应目标状态源行，
   * 行数等于源中该状态行数，且 billAmount 之和 === 源中该状态 amount 之和。
   */
  it('导入后结果仅含对应状态、数量匹配、金额保留', () => {
    fc.assert(
      fc.property(
        fc.array(memoRowArb, { minLength: 0, maxLength: 20 }),
        tableArb,
        (memoRows, table) => {
          const { api } = mountComposable()
          api.importFromMemo(table, memoRows)

          const targetStatus = table === 'discount' ? '已贴现' : '已背书'
          const sourceMatches = memoRows.filter((m) => m.status === targetStatus)
          const resultRows = table === 'discount' ? api.discountRows.value : api.endorseRows.value

          // 数量匹配
          expect(resultRows.length).toBe(sourceMatches.length)

          // 每行 rowType='dynamic'
          for (const r of resultRows) {
            expect(r.rowType).toBe('dynamic')
          }

          // billAmount 之和 === 源中该状态 amount 之和
          const expectedSum = sourceMatches.reduce((s, m) => s + m.amount, 0)
          const actualSum = resultRows.reduce((s, r) => s + r.billAmount, 0)
          expect(actualSum).toBeCloseTo(expectedSum, 4)

          // 另一张表不受影响（仍为空）
          const otherRows = table === 'discount' ? api.endorseRows.value : api.discountRows.value
          expect(otherRows.length).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})
