/**
 * F5-P9：BP-7 三处载入即重铸稳定行身份。
 *
 * spec: f5-sync-coverage-and-first-canary · Task 4（红判据）/ Task 6（修复）
 *       · Requirements 3.1 / 3.2 / 3.3 · Property 9
 *
 * slice BP-7 的 `must_fix_before` 把这三处定为**双向硬前置**：「把
 * `xlsx/gt-f5-cost-of-sales` 标 bidirectional 之前（也在 step 6 为这两条发布 contract 之前）」。
 *
 * 判据四组：
 *   ① 缺 id 的旧载荷 ⇒ 铸稳定身份，不出现下标形态
 *   ② 已含下标型 id 的存量载荷 ⇒ 重铸（需求 3.3 的迁移判据）
 *   ③ 铸造后**立即回写** store（否则下次载入又换新 id）
 *   ④ 插删行后同一逻辑行 id 不变
 *   ⑤ 形态变异防护：三处源码不得退回 `?? \`prefix-${i}\`` 写法
 */
import { describe, it, expect } from 'vitest'
import { ref, nextTick } from 'vue'
import {
  migrateF5MonthlyRows,
  useF5MonthlyDetail,
} from '../useF5MonthlyDetail'
import { migrateF5OtherCostRows, useF5OtherCost } from '../useF5OtherCost'
import { migrateF5ComparisonRows, useF5Comparison } from '../useF5Comparison'
import {
  isLegacyOrdinalRowId,
  mintStableRowId,
  resolveStableRowId,
  F5_ROW_ID_PREFIX,
  type RowIdentityMintStats,
} from '../f5RowIdentity'
import type { ChecklistResponse } from '../useF1FormData'

/** 改造前三处产出的下标派生身份形态（判据的反面样本）。 */
const LEGACY_ORDINAL = /^(m-\d+-\d+|oc-migrated-\d+|cmp-migrated-\d+)$/

function mkResponses(seed?: Record<string, string>) {
  const map = ref(new Map<string, ChecklistResponse>())
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      map.value.set(k, { item_id: k, conclusion: null, remark: v })
    }
  }
  return map
}

// ═══════════════════════════════════════════════════════════════════════════
// 组 ①②：缺 id / 含下标型 id 的载荷都被重铸
// ═══════════════════════════════════════════════════════════════════════════

describe('F5-P9 ①② 三处 migrate 铸稳定行身份', () => {
  const cases = [
    {
      label: 'F5-2 月度明细',
      migrate: migrateF5MonthlyRows,
      legacyIds: ['m-1700000000000-0', 'm-1700000000000-1'],
      payload: [{ product: '甲', months: [1, 2, 3] }, { product: '乙', months: [4] }],
    },
    {
      label: 'F5-3 其他业务成本',
      migrate: migrateF5OtherCostRows,
      legacyIds: ['oc-migrated-0', 'oc-migrated-1'],
      payload: [{ item: '销售材料', currentUnaudited: 100 }, { item: '出租', currentUnaudited: 20 }],
    },
    {
      label: 'F5-5 比较分析',
      migrate: migrateF5ComparisonRows,
      legacyIds: ['cmp-migrated-0', 'cmp-migrated-1'],
      payload: [{ product: '甲', currentQty: 1, currentUnitCost: 5 }, { product: '乙' }],
    },
  ]

  for (const c of cases) {
    it(`${c.label}：缺 id 的旧载荷铸稳定身份且不含下标形态`, () => {
      const stats: RowIdentityMintStats = { minted: 0 }
      const rows = c.migrate(JSON.stringify(c.payload), stats) as Array<{ id: string }>
      expect(rows).toHaveLength(c.payload.length)
      expect(stats.minted).toBe(c.payload.length)
      for (const row of rows) {
        expect(row.id).toBeTruthy()
        expect(LEGACY_ORDINAL.test(row.id)).toBe(false)
      }
      // 身份互不相同（下标形态虽唯一但不稳定；UUID 既唯一又稳定）
      expect(new Set(rows.map((r) => r.id)).size).toBe(rows.length)
    })

    it(`${c.label}：存量下标型 id 被重铸（需求 3.3 迁移判据）`, () => {
      const seeded = c.payload.map((p, i) => ({ ...p, id: c.legacyIds[i] }))
      const stats: RowIdentityMintStats = { minted: 0 }
      const rows = c.migrate(JSON.stringify(seeded), stats) as Array<{ id: string }>
      expect(stats.minted).toBe(seeded.length)
      for (const row of rows) {
        expect(LEGACY_ORDINAL.test(row.id)).toBe(false)
      }
    })

    it(`${c.label}：已是稳定 UUID 的行不被重铸`, () => {
      const stable = c.payload.map((p, i) => ({ ...p, id: `stable-uuid-${i}` }))
      const stats: RowIdentityMintStats = { minted: 0 }
      const rows = c.migrate(JSON.stringify(stable), stats) as Array<{ id: string }>
      expect(stats.minted).toBe(0)
      expect(rows.map((r) => r.id)).toEqual(stable.map((s) => s.id))
    })
  }
})

// ═══════════════════════════════════════════════════════════════════════════
// 组 ③：铸造后立即回写
// ═══════════════════════════════════════════════════════════════════════════

describe('F5-P9 ③ 铸造后立即回写 store', () => {
  it('F5-2：载入缺 id 的载荷后 store 里已带稳定 id', async () => {
    const responses = mkResponses({
      'F5-2-monthly-rows': JSON.stringify([{ product: '甲', months: [1] }]),
    })
    useF5MonthlyDetail({ allResponses: responses })
    await nextTick()
    const persisted = JSON.parse(responses.value.get('F5-2-monthly-rows')!.remark!)
    expect(persisted).toHaveLength(1)
    expect(persisted[0].id).toBeTruthy()
    expect(LEGACY_ORDINAL.test(persisted[0].id)).toBe(false)
  })

  it('F5-3：载入下标型 id 的载荷后 store 里已换成稳定 id', async () => {
    const responses = mkResponses({
      'F5-3-other-cost-rows': JSON.stringify([
        { id: 'oc-migrated-0', item: '销售材料', currentUnaudited: 10 },
      ]),
    })
    useF5OtherCost({ allResponses: responses })
    await nextTick()
    const persisted = JSON.parse(responses.value.get('F5-3-other-cost-rows')!.remark!)
    expect(persisted[0].id).not.toBe('oc-migrated-0')
    expect(LEGACY_ORDINAL.test(persisted[0].id)).toBe(false)
  })

  it('F5-5：载入缺 id 的 legacy 键载荷后主键被写入稳定 id', async () => {
    const responses = mkResponses({
      'F5-5-rows': JSON.stringify([{ product: '甲', currentQty: 2, currentUnitCost: 3 }]),
    })
    useF5Comparison({ allResponses: responses })
    await nextTick()
    // 🔴 需求 2.3：回写只写主键，legacy 键不被二次写入
    const primary = responses.value.get('F5-5-comparison-rows')
    expect(primary?.remark).toBeTruthy()
    const persisted = JSON.parse(primary!.remark!)
    expect(LEGACY_ORDINAL.test(persisted[0].id)).toBe(false)
    expect(responses.value.get('F5-5-rows')!.remark).toBe(
      JSON.stringify([{ product: '甲', currentQty: 2, currentUnitCost: 3 }]),
    )
  })

  it('readonly 时不回写（只读态不得产生写操作）', async () => {
    const raw = JSON.stringify([{ product: '甲', months: [1] }])
    const responses = mkResponses({ 'F5-2-monthly-rows': raw })
    useF5MonthlyDetail({ allResponses: responses, isReadonly: ref(true) })
    await nextTick()
    expect(responses.value.get('F5-2-monthly-rows')!.remark).toBe(raw)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 组 ④：插删行后同一逻辑行身份不变
// ═══════════════════════════════════════════════════════════════════════════

describe('F5-P9 ④ 插删行后同一逻辑行 id 不变', () => {
  it('F5-2：在首行前插入新行，原行 id 不变（下标派生会整体错位）', async () => {
    const responses = mkResponses({
      'F5-2-monthly-rows': JSON.stringify([
        { product: '甲', months: [1] },
        { product: '乙', months: [2] },
      ]),
    })
    const api = useF5MonthlyDetail({ allResponses: responses })
    await nextTick()
    const before = api.rows.value.map((r) => ({ id: r.id, product: r.product }))
    expect(before).toHaveLength(2)

    api.addRow()
    await nextTick()
    const after = api.rows.value
    expect(after.length).toBe(3)
    for (const original of before) {
      const match = after.find((r) => r.id === original.id)
      expect(match, `原行 ${original.product} 的 id 在插行后丢失`).toBeTruthy()
      expect(match!.product).toBe(original.product)
    }

    api.removeRow(after[after.length - 1].id)
    await nextTick()
    for (const original of before) {
      expect(api.rows.value.find((r) => r.id === original.id)).toBeTruthy()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 组 ⑤：形态变异防护 —— 三处源码不得退回下标写法
// ═══════════════════════════════════════════════════════════════════════════

describe('F5-P9 ⑤ helper 语义与形态防护', () => {
  it('isLegacyOrdinalRowId 认得三种旧形态、不误伤稳定 id', () => {
    expect(isLegacyOrdinalRowId('m-1700000000000-3')).toBe(true)
    expect(isLegacyOrdinalRowId('oc-migrated-12')).toBe(true)
    expect(isLegacyOrdinalRowId('cmp-migrated-0')).toBe(true)
    expect(isLegacyOrdinalRowId('f5m-abc-def')).toBe(false)
    expect(isLegacyOrdinalRowId('')).toBe(false)
    expect(isLegacyOrdinalRowId(undefined)).toBe(false)
  })

  it('mintStableRowId 带前缀且互不相同', () => {
    const a = mintStableRowId(F5_ROW_ID_PREFIX.monthlyDetail)
    const b = mintStableRowId(F5_ROW_ID_PREFIX.monthlyDetail)
    expect(a.startsWith('f5m-')).toBe(true)
    expect(a).not.toBe(b)
    expect(isLegacyOrdinalRowId(a)).toBe(false)
  })

  it('resolveStableRowId 只在缺失/旧形态时计数', () => {
    const stats: RowIdentityMintStats = { minted: 0 }
    expect(resolveStableRowId({ id: 'keep-me' }, 'f5m', stats)).toBe('keep-me')
    expect(stats.minted).toBe(0)
    resolveStableRowId({}, 'f5m', stats)
    expect(stats.minted).toBe(1)
    resolveStableRowId({ id: 'oc-migrated-9' }, 'f5oc', stats)
    expect(stats.minted).toBe(2)
    // rowId 兜底仍生效（既有载荷可能只有 rowId）
    expect(resolveStableRowId({ rowId: 'from-row-id' }, 'f5m', stats)).toBe('from-row-id')
    expect(stats.minted).toBe(2)
  })
})
