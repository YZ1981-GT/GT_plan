/**
 * Property-Based Tests — D1-7 备查簿核对 composable
 *
 * Spec: .kiro/specs/d1-endorsement-discount/
 * Tasks: 4.2 (Property 6), 4.3 (Property 8), 4.4 (Property 9), 4.5 (Property 11)
 *
 * 使用 fast-check + vitest（numRuns: 100）验证 useD1MemoReconciliation 的四个正确性属性：
 * - Property 6：备查簿核对区差异行 === 备查簿合计 - 明细账(D1-2)
 * - Property 8：动态行添加保持结构不变量
 * - Property 9：动态行序列化 Round-Trip 深度相等
 * - Property 11：D1-7 SUMIFS 按状态统计（贴现/背书）正确性
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import {
  useD1MemoReconciliation,
  emptyMemoRow,
  type MemoRow,
  type UseD1MemoReconciliationOptions,
} from '../useD1MemoReconciliation'
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

// ─── Field lists (mirror composable internals) ───────────────────────────────

const NUMERIC_FIELDS: Array<keyof MemoRow> = [
  'amount',
  'discountInterest',
  'beginningBalance',
  'currentReceived',
  'currentEndorsed',
  'currentMatured',
  'currentDiscounted',
  'endingBalance',
  'unexpiredEndorsedDiscounted',
  'auditedFinancing',
  'auditedNotes',
  'overdueTransferAmount',
]

const STRING_FIELDS: Array<keyof MemoRow> = [
  'noteType',
  'noteNumber',
  'receivedDate',
  'endorser',
  'issueDate',
  'issuer',
  'acceptor',
  'maturityDate',
  'transferDate',
  'status',
  'endorsee',
  'discountBank',
  'isPledged',
  'isDiscountedEndorsed',
  'isDerecognized',
  'creditRating',
  'relatedParty',
  'isOverdue',
  'remarkText',
]

// ─── Generators ──────────────────────────────────────────────────────────────

/**
 * 有限数值（避免 Infinity/NaN，否则 JSON 序列化会退化为 null → parseNum → 0）。
 * `+ 0` 将 -0 归一为 +0：JSON round-trip 会把 -0 序列化为 "0"，而 -0 与 +0
 * 表示同一审计金额，不应在深度相等断言中被区分（属生成器构造性伪差异）。
 */
const finiteAmount = fc
  .double({ min: -1e7, max: 1e7, noNaN: true, noDefaultInfinity: true })
  .map((x) => x + 0)

const statusArb = fc.constantFrom('持有', '已贴现', '已背书', '到期')

/**
 * 完整 MemoRow 生成器：以 emptyMemoRow 为基底，随机覆盖全部字段。
 * 约束：rowId 非空字符串；rowType ∈ {fixed, dynamic}（composable 反序列化不保留 summary）；
 * category 与桶一致（反序列化按桶回填 category）。
 */
function memoRowArb(category: 'bank' | 'commercial'): fc.Arbitrary<MemoRow> {
  const stringFieldRecord: Record<string, fc.Arbitrary<string>> = {}
  for (const f of STRING_FIELDS) stringFieldRecord[f] = fc.string({ maxLength: 12 })
  const numericFieldRecord: Record<string, fc.Arbitrary<number>> = {}
  for (const f of NUMERIC_FIELDS) numericFieldRecord[f] = finiteAmount

  return fc
    .record({
      rowId: fc.string({ minLength: 1, maxLength: 10 }).map((s) => `row-${s}`),
      rowType: fc.constantFrom<'fixed' | 'dynamic'>('fixed', 'dynamic'),
      ...stringFieldRecord,
      ...numericFieldRecord,
      status: statusArb,
    })
    .map((overrides: any) => {
      const base = emptyMemoRow(category, overrides.rowType)
      return { ...base, ...overrides, category } as MemoRow
    })
}

/** D1-2 按类别原值明细行（用户可编辑字段），JSON 存于 D1-cat-rows.remark */
const d1CatRowArb = fc.record({
  priorUnadjusted: finiteAmount,
  priorAje: finiteAmount,
  priorRje: finiteAmount,
  currentIncrease: finiteAmount,
  currentDecrease: finiteAmount,
  currentAje: finiteAmount,
  currentRje: finiteAmount,
})

// ─── Instantiation helper ────────────────────────────────────────────────────

function mountComposable(seed: Record<string, unknown> = {}) {
  const allResponses = ref(new Map<string, ChecklistResponse>())
  for (const [key, value] of Object.entries(seed)) {
    allResponses.value.set(key, {
      item_id: key,
      conclusion: null,
      remark: typeof value === 'string' ? value : JSON.stringify(value),
    })
  }
  const saveImmediate = vi.fn().mockResolvedValue(undefined)
  const options: UseD1MemoReconciliationOptions = {
    allResponses,
    wpId: ref('test-wp'),
    projectId: ref('test-proj'),
    saveImmediate,
    isReadonly: ref(false),
  }
  const api = useD1MemoReconciliation(options)
  return { api, allResponses, saveImmediate }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Task 4.2 — Property 6: 备查簿核对区差异等于备查簿减明细账
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-endorsement-discount, Property 6: 备查簿核对区差异', () => {
  /**
   * **Validates: Requirements 5.1, 5.2**
   *
   * 对任意备查簿数据 + D1-2 明细账数据：
   * reconciliationRows[2]（差异行）每一列 === reconciliationRows[0]（备查簿合计）
   * 减去 reconciliationRows[1]（明细账D1-2）。
   */
  it('差异行每列 === 备查簿合计 - 明细账(D1-2)', () => {
    fc.assert(
      fc.property(
        fc.array(memoRowArb('bank'), { minLength: 0, maxLength: 8 }),
        fc.array(memoRowArb('commercial'), { minLength: 0, maxLength: 8 }),
        fc.array(d1CatRowArb, { minLength: 0, maxLength: 8 }),
        (bankRows, commercialRows, catRows) => {
          const { api } = mountComposable({
            'D1-memo-rows': { bankRows, commercialRows },
            'D1-cat-rows': catRows,
          })

          const [memoTotal, ledger, diff] = api.reconciliationRows.value
          const columns: Array<keyof typeof diff> = [
            'beginningBalance',
            'currentReceived',
            'currentEndorsed',
            'currentMatured',
            'currentDiscounted',
            'endingBalance',
          ]
          for (const col of columns) {
            expect(diff[col] as number).toBeCloseTo(
              (memoTotal[col] as number) - (ledger[col] as number),
              6,
            )
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Task 4.3 — Property 8: 动态行添加保持结构不变量
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-endorsement-discount, Property 8: 动态行添加保持结构不变量', () => {
  /**
   * **Validates: Requirements 4.8, 7.2, 8.2, 10.3**
   *
   * 对预填 0..10 行的分类调用 addRow：行数变为 N+1；新增行（末尾元素）
   * 全部数值字段为 0、rowType 为 'dynamic'（合计行是 computed，不在数组内，
   * 故末尾即为"位于合计行之前"的最后一条明细/动态行）。
   */
  const runAddRowProperty = (category: 'bank' | 'commercial') => {
    fc.assert(
      fc.property(fc.array(memoRowArb(category), { minLength: 0, maxLength: 10 }), (rows) => {
        const seedKey = category === 'bank'
          ? { bankRows: rows, commercialRows: [] }
          : { bankRows: [], commercialRows: rows }
        const { api } = mountComposable({ 'D1-memo-rows': seedKey })

        const list = category === 'bank' ? api.bankRows : api.commercialRows
        const before = list.value.length
        expect(before).toBe(rows.length)

        api.addRow(category)

        expect(list.value.length).toBe(before + 1)
        const newRow = list.value[list.value.length - 1]
        expect(newRow.rowType).toBe('dynamic')
        expect(newRow.category).toBe(category)
        for (const f of NUMERIC_FIELDS) {
          expect(newRow[f] as number).toBe(0)
        }
      }),
      { numRuns: 100 },
    )
  }

  it('addRow(bank) 后长度 N+1、新行数值全 0、rowType=dynamic', () => {
    runAddRowProperty('bank')
  })

  it('addRow(commercial) 后长度 N+1、新行数值全 0、rowType=dynamic', () => {
    runAddRowProperty('commercial')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Task 4.4 — Property 9: 动态行序列化 Round-Trip
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-endorsement-discount, Property 9: 动态行序列化Round-Trip', () => {
  /**
   * **Validates: Requirements 13.7, 13.8, 13.9**
   *
   * 通过 composable 层验证序列化 round-trip：将生成的 MemoRow[] 序列化注入
   * allResponses 的 D1-memo-rows，实例化后读回 bankRows/commercialRows，
   * 应与原始数据深度相等（所有字段保留）。
   */
  it('composable 层：注入行序列化后读回深度相等', () => {
    fc.assert(
      fc.property(
        fc.array(memoRowArb('bank'), { minLength: 0, maxLength: 8 }),
        fc.array(memoRowArb('commercial'), { minLength: 0, maxLength: 8 }),
        (bankRows, commercialRows) => {
          const { api } = mountComposable({
            'D1-memo-rows': { bankRows, commercialRows },
          })
          expect(api.bankRows.value).toEqual(bankRows)
          expect(api.commercialRows.value).toEqual(commercialRows)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('纯 JSON Round-Trip：JSON.stringify → JSON.parse 深度相等', () => {
    fc.assert(
      fc.property(fc.array(memoRowArb('bank'), { minLength: 0, maxLength: 10 }), (rows) => {
        const parsed = JSON.parse(JSON.stringify(rows))
        expect(parsed).toEqual(rows)
      }),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Task 4.5 — Property 11: D1-7 SUMIFS 统计正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-endorsement-discount, Property 11: SUMIFS统计正确性', () => {
  /**
   * **Validates: Requirements 5.6**
   *
   * endorsedStats.discountedTotal === Σ amount(status==='已贴现')
   * endorsedStats.endorsedTotal   === Σ amount(status==='已背书')
   * 统计范围为 bankRows ∪ commercialRows。
   */
  it('贴现/背书统计等于按状态过滤的金额之和', () => {
    fc.assert(
      fc.property(
        fc.array(memoRowArb('bank'), { minLength: 0, maxLength: 10 }),
        fc.array(memoRowArb('commercial'), { minLength: 0, maxLength: 10 }),
        (bankRows, commercialRows) => {
          const { api } = mountComposable({
            'D1-memo-rows': { bankRows, commercialRows },
          })

          const allRows = [...bankRows, ...commercialRows]
          const expectedDiscounted = allRows
            .filter((r) => r.status === '已贴现')
            .reduce((sum, r) => sum + r.amount, 0)
          const expectedEndorsed = allRows
            .filter((r) => r.status === '已背书')
            .reduce((sum, r) => sum + r.amount, 0)

          expect(api.endorsedStats.value.discountedTotal).toBeCloseTo(expectedDiscounted, 4)
          expect(api.endorsedStats.value.endorsedTotal).toBeCloseTo(expectedEndorsed, 4)
        },
      ),
      { numRuns: 100 },
    )
  })
})
