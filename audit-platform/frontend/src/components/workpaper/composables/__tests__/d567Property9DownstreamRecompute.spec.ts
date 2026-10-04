/**
 * Property 9（D5/D6/D7）：受管 store 键被**回写**后，下游 computed / watch 必须重算。
 *
 * spec: d567-sync-coverage-via-row-table-engine · Task 8 / 11 / 17 · Requirements 2.8, 2.9, 6.1
 *
 * ═══ 这条判据在防什么 ═══
 *
 * 双向回写的价值链是「OO 改一格 → forcesave → 后端 extract → store 键更新 → **前端下游重算**」。
 * 前四段由后端契约/instrumentation 判据覆盖，**最后一段一直没人测** —— 而它恰恰是最容易
 * 静默坏掉的一段：把 store 解析结果存进 `ref` 而非 `computed`（或 watch 漏了 `deep`/漏了键），
 * 回写就只落库不上屏，用户看到的还是旧数。四张表的欠账都登记在各自 Task 的 Property 9 项下。
 *
 * ═══ 四组链路（现读实证，2026-09-30）═══
 *
 *  ① `D5-4-rows` → `useD5CrossSheet`：fairValueRows → fairValueTotal(Σ row.fairValue)
 *     → ociChange(= 小计 − 公允价值合计) → adjudicationForDisclosure　**三层**
 *  ② `D6-8-single-rows` → `useD6CrossSheet`：eclReferenceValues.single(Σ r.expectedProvision)
 *     → .total → eclVsImpairmentDiff.diff / eclForDisclosure　**三层**
 *  ③ `D7-7-post-rows` → `useD7CrossSheet.voucherPostTransferTotal`(Σ r.creditAmount)
 *  ④ `D7-7-post-rows` → `useD7Detail` 的 **watch**：按 `customerName` 聚合 → 写 `postTransfer`
 *     到 `companyName` 匹配的 D7-2 行 → `persistRows()`（有落库副作用）
 *
 * 🔴 判据形态：每组都做**两轮**回写（A → B → C），断言每轮都跟上。只测一轮的话，
 *    「首次读取正确但之后不再跟随」（一次性快照）会漏网 —— 那正是 `ref` 误用的典型症状。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope, nextTick, defineComponent, h, type Ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

// ── element-plus：仅 ElMessage 被 composable 用到，全量 mock 避免加载重型库 ──
vi.mock('element-plus', () => ({
  ElMessage: Object.assign(vi.fn(), {
    success: vi.fn(), info: vi.fn(), error: vi.fn(), warning: vi.fn(),
  }),
}))

// ── apiProxy：`useD7Detail` 经 `useAgingConfig` 拉 /aging/config。
//    🔴 这不是可选的：`useD7Detail` 的 rows watch 有 `if (!segments.value.length) return` 门
//    （等账龄段加载完才迁移，避免用空段丢数据）⇒ 不喂 segments 则 rows 恒空、④ 组判据测不到东西。
const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: mockGet } }))

import { useD5CrossSheet } from '../useD5CrossSheet'
import { useD6CrossSheet } from '../useD6CrossSheet'
import { useD7CrossSheet } from '../useD7CrossSheet'
import { useD7Detail } from '../useD7Detail'
import { PRESET_SEGMENTS, clearAgingConfigCache } from '@/composables/useAgingConfig'

beforeEach(() => {
  clearAgingConfigCache()
  mockGet.mockReset()
  mockGet.mockResolvedValue({
    preset: 'THREE_YEAR' as const,
    effective_segments: PRESET_SEGMENTS.THREE_YEAR,
    subject_overrides: {},
  })
})

type Resp = { item_id: string; conclusion: string | null; remark: string | null }
type Store = Ref<Map<string, Resp>>

function makeStore(entries: Record<string, unknown> = {}): Store {
  const m = new Map<string, Resp>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { item_id: k, conclusion: null, remark: typeof v === 'string' ? v : JSON.stringify(v) })
  }
  return ref(m) as Store
}

/** 模拟「后端 extract 把新值写回 store 键」—— 必须换 Map 引用（与生产 `allResponses.value = new Map(...)` 同形）。 */
function writeback(store: Store, key: string, value: unknown): void {
  const m = new Map(store.value)
  m.set(key, {
    item_id: key,
    conclusion: null,
    remark: typeof value === 'string' ? value : JSON.stringify(value),
  })
  store.value = m
}

// ═══════════════════════════════════════════════════════════════════════════
// ① D5：D5-4-rows → fairValueTotal → ociChange → adjudicationForDisclosure
// **Validates: Requirements 2.8（Task 8 Property 9）**
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 9 ①：D5-4-rows 回写 ⇒ useD5CrossSheet 三层下游全部重算', () => {
  const fvRows = (...vals: number[]) =>
    vals.map((v, i) => ({ rowId: `fv-${i}`, fairValue: v }))
  /** D5-2 明细：给 categoryAggregation 一个非零小计，让 ociChange 有意义。 */
  const detailRows = [
    { rowId: 'd1', category: '应收票据', endAudited: 1000, priorAudited: 400 },
    { rowId: 'd2', category: '应收账款', endAudited: 500, priorAudited: 100 },
  ]

  it('两轮回写都跟上（防「首读正确、之后不再跟随」的一次性快照）', async () => {
    const store = makeStore({ 'D5-2-rows': detailRows, 'D5-4-rows': fvRows(600, 300) })
    const scope = effectScope()
    try {
      const cs = scope.run(() => useD5CrossSheet({ allResponses: store as any }))!
      // 基线：公允价值合计 900；小计 1500 ⇒ ociChange.current = 1500 − 900 = 600
      expect(cs.ociChange.value.current).toBe(600)
      expect(cs.adjudicationForDisclosure.value.ociChange.current).toBe(600)

      // 第一轮回写：公允价值合计 → 1100
      writeback(store, 'D5-4-rows', fvRows(800, 300))
      await nextTick()
      expect(cs.ociChange.value.current, 'ociChange 未跟随第一轮回写').toBe(1500 - 1100)
      expect(
        cs.adjudicationForDisclosure.value.ociChange.current,
        '第三层 adjudicationForDisclosure 未跟随',
      ).toBe(1500 - 1100)

      // 第二轮回写：行数也变（删一行）⇒ 合计 200
      writeback(store, 'D5-4-rows', fvRows(200))
      await nextTick()
      expect(cs.ociChange.value.current, 'ociChange 未跟随第二轮回写').toBe(1500 - 200)
      expect(cs.adjudicationForDisclosure.value.ociChange.current).toBe(1500 - 200)
    } finally {
      scope.stop()
    }
  })

  it('键被清空（回写成空数组）⇒ 合计归零而不是保留旧值', async () => {
    const store = makeStore({ 'D5-2-rows': detailRows, 'D5-4-rows': fvRows(600, 300) })
    const scope = effectScope()
    try {
      const cs = scope.run(() => useD5CrossSheet({ allResponses: store as any }))!
      expect(cs.ociChange.value.current).toBe(600)
      writeback(store, 'D5-4-rows', [])
      await nextTick()
      // 公允价值合计 0 ⇒ ociChange = 小计 1500 − 0
      expect(cs.ociChange.value.current, '清空后仍用旧值 ⇒ 下游缓存了快照').toBe(1500)
    } finally {
      scope.stop()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// ② D6：D6-8-single-rows → eclReferenceValues → eclVsImpairmentDiff / eclForDisclosure
// **Validates: Requirements 2.9（Task 11 Property 9）**
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 9 ②：D6-8-single-rows 回写 ⇒ useD6CrossSheet ECL 链重算', () => {
  const eclRows = (...vals: number[]) =>
    vals.map((v, i) => ({ rowId: `ecl-${i}`, expectedProvision: v }))

  it('两轮回写都跟上，且第三层 eclVsImpairmentDiff 同步变化', async () => {
    const store = makeStore({ 'D6-8-single-rows': eclRows(100, 50) })
    const scope = effectScope()
    try {
      const cs = scope.run(() => useD6CrossSheet({ allResponses: store as any }))!
      expect(cs.eclReferenceValues.value.single).toBe(150)
      expect(cs.eclReferenceValues.value.total).toBe(150)
      const diff0 = cs.eclVsImpairmentDiff.value.diff

      writeback(store, 'D6-8-single-rows', eclRows(300, 50))
      await nextTick()
      expect(cs.eclReferenceValues.value.single, 'ECL single 未跟随第一轮回写').toBe(350)
      expect(cs.eclReferenceValues.value.total).toBe(350)
      expect(
        cs.eclVsImpairmentDiff.value.diff,
        '第三层 eclVsImpairmentDiff 未跟随（diff 应随 eclTotal 变化）',
      ).toBe(diff0 + 200)

      writeback(store, 'D6-8-single-rows', eclRows(7))
      await nextTick()
      expect(cs.eclReferenceValues.value.single, 'ECL single 未跟随第二轮回写').toBe(7)
    } finally {
      scope.stop()
    }
  })

  it('eclForDisclosure（披露口径）同一回写下同步重算', async () => {
    const store = makeStore({ 'D6-8-single-rows': eclRows(100) })
    const scope = effectScope()
    try {
      const cs = scope.run(() => useD6CrossSheet({ allResponses: store as any }))!
      const before = JSON.stringify(cs.eclForDisclosure.value)
      writeback(store, 'D6-8-single-rows', eclRows(999))
      await nextTick()
      const after = JSON.stringify(cs.eclForDisclosure.value)
      expect(after, 'eclForDisclosure 在回写后毫无变化 ⇒ 未消费该键或缓存了快照').not.toBe(before)
    } finally {
      scope.stop()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// ③ D7-crossSheet：D7-7-post-rows → voucherPostTransferTotal
// **Validates: Requirements 2.8（Task 17 Property 9）**
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 9 ③：D7-7-post-rows 回写 ⇒ voucherPostTransferTotal 重算', () => {
  const postRows = (...pairs: Array<[string, number]>) =>
    pairs.map(([customerName, creditAmount], i) => ({ rowId: `p-${i}`, customerName, creditAmount }))

  it('两轮回写都跟上', async () => {
    const store = makeStore({ 'D7-7-post-rows': postRows(['甲公司', 100], ['乙公司', 200]) })
    const scope = effectScope()
    try {
      const cs = scope.run(() =>
        useD7CrossSheet({
          allResponses: store as any,
          segments: ref(PRESET_SEGMENTS.THREE_YEAR) as any,
        }),
      )!
      expect(cs.voucherPostTransferTotal.value).toBe(300)

      writeback(store, 'D7-7-post-rows', postRows(['甲公司', 500], ['乙公司', 200]))
      await nextTick()
      expect(cs.voucherPostTransferTotal.value, '未跟随第一轮回写').toBe(700)

      writeback(store, 'D7-7-post-rows', postRows(['丙公司', 1]))
      await nextTick()
      expect(cs.voucherPostTransferTotal.value, '未跟随第二轮回写').toBe(1)
    } finally {
      scope.stop()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// ④ D7-detail：D7-7-post-rows → watch → postTransfer 写回 D7-2 行 + 落库
// **Validates: Requirements 2.8（Task 17 Property 9 的 watch 侧）**
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 9 ④：D7-7-post-rows 回写 ⇒ useD7Detail 的 watch 触发联动', () => {
  /**
   * 🔴 必须**真组件挂载**（不能用 `effectScope`）：`useD7Detail` → `useAgingConfig` 的
   *    `fetchConfig()` 挂在 `onMounted` 里，`effectScope` 不触发生命周期钩子 ⇒ segments 恒空
   *    ⇒ rows watch 被 `if (!segments.value.length) return` 门挡住 ⇒ rows 恒空、判据测不到东西。
   *    （实测踩过：先用 effectScope 写，两条判据报 `expected undefined to be 300`。）
   */
  function setupDetail(initial: Record<string, unknown>) {
    const store = makeStore(initial)
    const debouncedSave = vi.fn((itemId: string, data: Partial<Resp>) => {
      const m = new Map(store.value)
      const cur = m.get(itemId) ?? { item_id: itemId, conclusion: null, remark: null }
      m.set(itemId, { ...cur, ...data } as Resp)
      store.value = m
    })
    let api!: ReturnType<typeof useD7Detail>
    const Comp = defineComponent({
      setup() {
        api = useD7Detail({
          allResponses: store as any,
          saveImmediate: async () => {},
          debouncedSave: debouncedSave as any,
          wpId: ref('wp-t'),
          projectId: ref('p-t'),
        })
        return () => h('div')
      },
    })
    const wrapper = mount(Comp)
    return { store, api, debouncedSave, dispose: () => wrapper.unmount() }
  }

  /** 等账龄配置的异步 fetch 落地（rows watch 的前置门）+ 响应式刷新。 */
  async function flush(): Promise<void> {
    await flushPromises()
    await nextTick()
    await flushPromises()
  }

  const d72Rows = [
    { rowId: 'r1', companyName: '甲公司', postTransfer: 0 },
    { rowId: 'r2', companyName: '乙公司', postTransfer: 0 },
  ]

  it('watch 把期后结转按客户名聚合写到匹配行的 postTransfer', async () => {
    const { store, api, dispose } = setupDetail({
      'D7-2-rows': d72Rows,
      'D7-7-post-rows': [{ customerName: '甲公司', creditAmount: 300 }],
    })
    try {
      await flush()
      const r1 = api.rows.value.find((r: any) => r.companyName === '甲公司')
      expect(r1?.postTransfer, 'immediate watch 未把期后结转写进行对象').toBe(300)

      // 回写：金额变 + 另一家也有了
      writeback(store, 'D7-7-post-rows', [
        { customerName: '甲公司', creditAmount: 900 },
        { customerName: '乙公司', creditAmount: 50 },
      ])
      await nextTick()
      expect(
        api.rows.value.find((r: any) => r.companyName === '甲公司')?.postTransfer,
        'watch 未跟随回写（甲公司）',
      ).toBe(900)
      expect(
        api.rows.value.find((r: any) => r.companyName === '乙公司')?.postTransfer,
        'watch 未跟随回写（乙公司）',
      ).toBe(50)
    } finally {
      dispose()
    }
  })

  it('联动结果**落库**（不只是内存对象变了）', async () => {
    const { store, debouncedSave, dispose } = setupDetail({
      'D7-2-rows': d72Rows,
      'D7-7-post-rows': [{ customerName: '甲公司', creditAmount: 300 }],
    })
    try {
      await flush()
      writeback(store, 'D7-7-post-rows', [{ customerName: '甲公司', creditAmount: 777 }])
      await nextTick()
      // persistRows() 走 debouncedSave('D7-2-rows', …)
      const persisted = debouncedSave.mock.calls.filter((c) => c[0] === 'D7-2-rows')
      expect(persisted.length, '联动后未持久化 D7-2-rows ⇒ 刷新即丢').toBeGreaterThan(0)
      const lastRemark = String(store.value.get('D7-2-rows')?.remark ?? '')
      expect(lastRemark, '落库内容里没有新的 postTransfer 值').toContain('777')
    } finally {
      dispose()
    }
  })

  it('🔴 无匹配客户名时不得误写（按 companyName 精确匹配，不做模糊）', async () => {
    const { store, api, dispose } = setupDetail({
      'D7-2-rows': d72Rows,
      'D7-7-post-rows': [{ customerName: '甲公司', creditAmount: 300 }],
    })
    try {
      await flush()
      writeback(store, 'D7-7-post-rows', [{ customerName: '不存在的公司', creditAmount: 1234 }])
      await nextTick()
      for (const r of api.rows.value as any[]) {
        expect(r.postTransfer, `${r.companyName} 被无匹配的期后结转误写`).toBe(0)
      }
    } finally {
      dispose()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 🔴 变异自检：证明「两轮回写」判据能抓住一次性快照
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 9 变异自检：一次性快照会被抓住', () => {
  it('模拟错误实现（把解析结果存进 ref 只初始化一次）⇒ 第二轮回写检出不跟随', async () => {
    // 这不是测生产代码，而是证明**判据形态**（两轮回写 + 逐轮断言）具备鉴别力：
    // 若某个 composable 把 store 解析结果缓存进 ref，本形态必红。
    const store = makeStore({ 'D5-4-rows': [{ rowId: 'a', fairValue: 100 }] })
    // 错误实现：只在创建时读一次
    const cached = ref(JSON.parse(String(store.value.get('D5-4-rows')?.remark ?? '[]')))
    const sumCached = () =>
      (cached.value as any[]).reduce((s, r) => s + Number(r.fairValue || 0), 0)
    expect(sumCached()).toBe(100)

    writeback(store, 'D5-4-rows', [{ rowId: 'a', fairValue: 999 }])
    await nextTick()
    // 错误实现不跟随 —— 本断言证明「两轮回写」形态确实能区分正确与错误实现。
    expect(sumCached(), '缓存实现竟跟随了 store（变异体构造错了）').toBe(100)

    // 对照：正确实现（computed 读 store）跟随。
    const scope = effectScope()
    try {
      const cs = scope.run(() => useD5CrossSheet({ allResponses: store as any }))!
      expect(cs.fairValueTotal.value.current).toBe(999)
    } finally {
      scope.stop()
    }
  })
})
