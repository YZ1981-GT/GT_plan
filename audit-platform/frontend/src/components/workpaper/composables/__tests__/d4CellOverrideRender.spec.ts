/**
 * P13 / P14 / P15：选项 b 覆盖状态机的**运行时**判据（不是纯函数层，是 composable 真行为）。
 *
 * spec: d4-html-to-oo-store-contract-alignment · Task 12 / 15
 * Requirements 6.3, 6.4, 6.5 · Property 13 / Property 14 / Property 15
 *
 * ═══ 为什么这三条必须落在 composable 层 ═══
 *
 * `dynamicAdjRowsCellState.spec.ts` 测的是纯函数 `resolveCellState(stored, snap, derived)` ——
 * 它证明「给定三个量，四态判定正确」，但**证明不了**这三个量在真实运行里会不会走到那四态。
 * spec 的 Testing Strategy 原话：「手写必漏 S4，而 S4 是唯一会静默丢数据的那一态」。
 * S4 的可达性完全取决于 `syncDerivedRowsIntoStore()` 怎么维护 `snap` —— 那是 composable 的事。
 *
 * 判据构造法：**不假设派生聚合口径**（months 求和规则将来若变，判据不该跟着红）。
 * 先挂载拿 S1 态的派生值当基准，再据它构造覆盖 / 上游变化。
 */
import { describe, it, expect } from 'vitest'
import { ref, effectScope, nextTick, type Ref } from 'vue'
import { useD4Adjudication } from '../useD4Adjudication'
import { D4_ADJ_ROWS_SPEC } from '../d4AdjudicationRows'
import { rowFieldItemId, labelKey } from '../shared/dynamicAdjudicationRows'
import type { ChecklistResponse } from '../useD4FormData'

type Responses = Ref<Map<string, ChecklistResponse>>

/** 被 spy 的 responses：统计 `Map.set` 次数（P13 的写库计数口径）。 */
function buildResponses(entries: Array<[string, unknown]>): {
  responses: Responses
  setCount: () => number
  resetCount: () => void
} {
  const map = new Map<string, ChecklistResponse>()
  for (const [item, payload] of entries) {
    map.set(item, { item_id: item, conclusion: null, remark: JSON.stringify(payload) })
  }
  let count = 0
  // 🔴 spy 装在**原始 Map** 上，且用 `Map.prototype.set` 取真实现：
  //    Vue 的 reactive Map 代理在 set 时会转调原始 target 的 set，所以装在原始 Map 上
  //    既能统计到生产代码经代理发起的每一次写，又不会自我递归。
  //    （装在 `responses.value`（代理）上会让 realSet 指回代理本身 ⇒ 栈溢出，已实测。）
  const realSet = Map.prototype.set.bind(map)
  map.set = ((k: string, v: ChecklistResponse) => {
    count += 1
    return realSet(k, v)
  }) as typeof map.set
  const responses = ref(map) as Responses
  return { responses, setCount: () => count, resetCount: () => { count = 0 } }
}

function run(allResponses: Responses) {
  const scope = effectScope()
  const api = scope.run(() =>
    useD4Adjudication({
      wpId: ref('wp-test'),
      projectId: ref('proj-test'),
      allResponses,
      isReadonly: ref(false),
    }),
  )!
  return { api, dispose: () => scope.stop() }
}

/** D4-2 明细行（主营按产品聚合的上游）。 */
const monthRow = (product: string, monthVal: number) => ({
  rowId: `r-${product}`,
  product,
  months: Array(12).fill(monthVal),
  auditAdjustment: 0,
  priorUnadjusted: 0,
  priorAdjustment: 0,
})

const PRODUCT = '产品A'
const PRODUCT2 = '产品B'
/** 派生行 store rowId = `xsheet-{section}-{labelKey(label)}`（裁决 D4：按 rowId 精确配对）。 */
const derivedRowId = (product: string) => `xsheet-main-${labelKey(product)}`
const storedId = (product: string, field: string) =>
  rowFieldItemId(D4_ADJ_ROWS_SPEC, derivedRowId(product), field)
const snapId = (product: string, field: string) => `${storedId(product, field)}-snap`

function setRaw(responses: Responses, itemId: string, raw: string | number): void {
  responses.value.set(itemId, { item_id: itemId, conclusion: null, remark: String(raw) })
}

function readRawValue(responses: Responses, itemId: string): string {
  return String(responses.value.get(itemId)?.remark ?? '')
}

/** 从 sections 主营区取某派生行。 */
function mainRow(api: ReturnType<typeof useD4Adjudication>, product: string) {
  const sec = api.sections.value.find((s) => s.sectionKey === 'main-revenue')!
  return sec.rows.find((r) => r.rowKey === derivedRowId(product))
}


// ═══════════════════════════════════════════════════════════════════════════
// P13：S3 自动跟随幂等 —— 值未变不产生第二次写库
// **Validates: Requirements 6.3**
// ═══════════════════════════════════════════════════════════════════════════

describe('P13：派生行同步幂等（值未变不写库）', () => {
  it('挂载后再次触发派生源（值不变）⇒ 零次 Map.set', async () => {
    const { responses, setCount, resetCount } = buildResponses([
      ['D4-2-rows', [monthRow(PRODUCT, 100)]],
    ])
    const { api, dispose } = run(responses)
    try {
      await nextTick()
      const firstPass = setCount()
      expect(firstPass).toBeGreaterThan(0) // 首次挂载必须真落库（否则本判据测的是空气）

      // 上游对象换了**新引用但值全等**（deep watch 会触发回调）。
      resetCount()
      responses.value.set('D4-2-rows', {
        item_id: 'D4-2-rows',
        conclusion: null,
        remark: JSON.stringify([monthRow(PRODUCT, 100)]),
      })
      await nextTick()
      // 上一行自身那次 set 要扣掉：它是测试写入，不是同步器写库。
      const syncWrites = setCount() - 1
      expect(syncWrites).toBe(0)
      // 派生值仍在（不是因为什么都没写才为 0）。
      expect(mainRow(api, PRODUCT)!.currentUnadjusted).toBeGreaterThan(0)
    } finally {
      dispose()
    }
  })

  it('上游值真变 ⇒ 必须写库（幂等不等于不写）', async () => {
    const { responses, setCount, resetCount } = buildResponses([
      ['D4-2-rows', [monthRow(PRODUCT, 100)]],
    ])
    const { api, dispose } = run(responses)
    try {
      await nextTick()
      const before = mainRow(api, PRODUCT)!.currentUnadjusted
      resetCount()
      responses.value.set('D4-2-rows', {
        item_id: 'D4-2-rows',
        conclusion: null,
        remark: JSON.stringify([monthRow(PRODUCT, 250)]),
      })
      await nextTick()
      expect(setCount() - 1).toBeGreaterThan(0)
      expect(mainRow(api, PRODUCT)!.currentUnadjusted).not.toBe(before)
    } finally {
      dispose()
    }
  })
})


// ═══════════════════════════════════════════════════════════════════════════
// P14：S4 双值同时可见，且系统不自动二选一
// **Validates: Requirements 6.4**
// ═══════════════════════════════════════════════════════════════════════════

describe('P14：S4（覆盖 且 上游已变）三值同时可见', () => {
  it('OO 覆盖后上游再变 ⇒ 该格进 S4，覆盖值/原派生值/现派生值三者都可读且互不相等', async () => {
    const { responses } = buildResponses([['D4-2-rows', [monthRow(PRODUCT, 100)]]])
    const { api, dispose } = run(responses)
    try {
      await nextTick()
      // ── 起点：S1 纯派生。derived 值从实际聚合读出（不写死聚合口径）。
      const derived1 = mainRow(api, PRODUCT)!.currentUnadjusted
      expect(derived1).toBeGreaterThan(0)
      expect(mainRow(api, PRODUCT)!.cellOverrides).toBeUndefined()

      // ── 步骤 1：模拟 OO 侧把这一格改大（回方向 merge 落行对象 ⇒ 读侧行对象/stored 优先）。
      const overrideValue = derived1 + 1000
      setRaw(responses, storedId(PRODUCT, 'currentUnadjusted'), overrideValue)
      await nextTick()
      const s2 = mainRow(api, PRODUCT)!
      expect(s2.cellOverrides?.currentUnadjusted?.state).toBe('S2')
      expect(s2.currentUnadjusted).toBe(overrideValue) // 显示覆盖值，不是派生值

      // ── 步骤 2：上游 D4-2 再变（同需求 5.3 真栈往返的第二步）。
      responses.value.set('D4-2-rows', {
        item_id: 'D4-2-rows',
        conclusion: null,
        remark: JSON.stringify([monthRow(PRODUCT, 250)]),
      })
      await nextTick()

      const s4 = mainRow(api, PRODUCT)!
      const cell = s4.cellOverrides?.currentUnadjusted
      expect(cell, '覆盖格丢了 cellOverrides —— 覆盖被吞掉').toBeDefined()
      expect(cell!.state, `上游已变后应为 S4，实得 ${cell!.state}`).toBe('S4')

      // 🔴 三值必须**同时**可读且互不相等 —— 这是「系统不自动二选一」的判据面。
      const derived2 = cell!.derived
      expect(cell!.stored).toBe(overrideValue) // 覆盖值
      expect(cell!.snap).toBe(derived1) // 被覆盖时的**原**派生值（必须冻结，不许追上 derived）
      expect(derived2).not.toBe(derived1) // 现派生值（上游已变）
      expect(new Set([cell!.stored, cell!.snap, derived2]).size).toBe(3)

      // 显示值仍是覆盖值（不自动改成现派生值）。
      expect(s4.currentUnadjusted).toBe(overrideValue)
    } finally {
      dispose()
    }
  })

  it('snap 必须在 store 里真的冻结（不只是渲染层算出来的）', async () => {
    const { responses } = buildResponses([['D4-2-rows', [monthRow(PRODUCT, 100)]]])
    const { api, dispose } = run(responses)
    try {
      await nextTick()
      const derived1 = mainRow(api, PRODUCT)!.currentUnadjusted
      setRaw(responses, storedId(PRODUCT, 'currentUnadjusted'), derived1 + 1000)
      await nextTick()
      responses.value.set('D4-2-rows', {
        item_id: 'D4-2-rows',
        conclusion: null,
        remark: JSON.stringify([monthRow(PRODUCT, 250)]),
      })
      await nextTick()
      // store 里的 snap item 必须还是 derived1（覆盖时的派生值），不是新派生值。
      expect(Number(readRawValue(responses, snapId(PRODUCT, 'currentUnadjusted')))).toBe(derived1)
    } finally {
      dispose()
    }
  })

  it('反证：未被覆盖的格上游变化后仍自动跟随、不产生覆盖标记（P12 的运行时面）', async () => {
    const { responses } = buildResponses([['D4-2-rows', [monthRow(PRODUCT, 100)]]])
    const { api, dispose } = run(responses)
    try {
      await nextTick()
      responses.value.set('D4-2-rows', {
        item_id: 'D4-2-rows',
        conclusion: null,
        remark: JSON.stringify([monthRow(PRODUCT, 777)]),
      })
      await nextTick()
      const row = mainRow(api, PRODUCT)!
      expect(row.cellOverrides, '纯派生格被误标成人工覆盖').toBeUndefined()
    } finally {
      dispose()
    }
  })
})


// ═══════════════════════════════════════════════════════════════════════════
// P15：恢复取数只影响被点的那一格
// **Validates: Requirements 6.5**
// ═══════════════════════════════════════════════════════════════════════════

describe('P15：恢复取数的作用域是「一格」', () => {
  it('同行两格都被覆盖 ⇒ 只恢复被点那格，另一格保持覆盖态', async () => {
    const { responses } = buildResponses([['D4-2-rows', [monthRow(PRODUCT, 100)]]])
    const { api, dispose } = run(responses)
    try {
      await nextTick()
      const row0 = mainRow(api, PRODUCT)!
      const curDerived = row0.currentUnadjusted
      const priorDerived = row0.priorUnadjusted
      // 两格各自被 OO 覆盖（prior 派生值可能为 0，+1000 后必然 ≠ 派生值）。
      setRaw(responses, storedId(PRODUCT, 'currentUnadjusted'), curDerived + 1000)
      setRaw(responses, storedId(PRODUCT, 'priorUnadjusted'), priorDerived + 2000)
      await nextTick()
      const both = mainRow(api, PRODUCT)!
      expect(both.cellOverrides?.currentUnadjusted).toBeDefined()
      expect(both.cellOverrides?.priorUnadjusted).toBeDefined()

      // ── 只点 currentUnadjusted 的「恢复取数」 ──
      api.restoreDerivedValue(derivedRowId(PRODUCT), 'currentUnadjusted')
      await nextTick()

      const after = mainRow(api, PRODUCT)!
      expect(after.cellOverrides?.currentUnadjusted, '被点那格未回 S1').toBeUndefined()
      expect(after.currentUnadjusted, '被点那格未退回派生值').toBe(curDerived)
      expect(after.cellOverrides?.priorUnadjusted, '同行另一格被连带恢复了').toBeDefined()
      expect(after.priorUnadjusted).toBe(priorDerived + 2000)
    } finally {
      dispose()
    }
  })

  it('同列其他行不受影响', async () => {
    const { responses } = buildResponses([
      ['D4-2-rows', [monthRow(PRODUCT, 100), monthRow(PRODUCT2, 300)]],
    ])
    const { api, dispose } = run(responses)
    try {
      await nextTick()
      const d1 = mainRow(api, PRODUCT)!.currentUnadjusted
      const d2 = mainRow(api, PRODUCT2)!.currentUnadjusted
      setRaw(responses, storedId(PRODUCT, 'currentUnadjusted'), d1 + 1000)
      setRaw(responses, storedId(PRODUCT2, 'currentUnadjusted'), d2 + 1000)
      await nextTick()
      expect(mainRow(api, PRODUCT)!.cellOverrides?.currentUnadjusted).toBeDefined()
      expect(mainRow(api, PRODUCT2)!.cellOverrides?.currentUnadjusted).toBeDefined()

      api.restoreDerivedValue(derivedRowId(PRODUCT), 'currentUnadjusted')
      await nextTick()

      expect(mainRow(api, PRODUCT)!.cellOverrides?.currentUnadjusted).toBeUndefined()
      expect(
        mainRow(api, PRODUCT2)!.cellOverrides?.currentUnadjusted,
        '另一行被连带恢复了',
      ).toBeDefined()
      expect(mainRow(api, PRODUCT2)!.currentUnadjusted).toBe(d2 + 1000)
    } finally {
      dispose()
    }
  })

  it('恢复取数**当场**把 store 写成派生值，不靠下一 tick 的同步自愈', async () => {
    // 🔴 这条专钉 `_pureDerived` 在 restoreDerivedValue 里的可达分支：若那里误取显示值
    //    （覆盖态下 == stored），store 里当场留着覆盖值 —— 此刻若 flushSave / 切 OO，错值
    //    直接落库。后续同步虽会自愈，但"靠下一 tick 兜住"不是正确性，只是运气。
    //    故断言在 restoreDerivedValue 之后**立即**读 store（不 await nextTick）。
    const { responses } = buildResponses([['D4-2-rows', [monthRow(PRODUCT, 100)]]])
    const { api, dispose } = run(responses)
    try {
      await nextTick()
      const d1 = mainRow(api, PRODUCT)!.currentUnadjusted
      const overrideValue = d1 + 1000
      setRaw(responses, storedId(PRODUCT, 'currentUnadjusted'), overrideValue)
      await nextTick()
      expect(mainRow(api, PRODUCT)!.cellOverrides?.currentUnadjusted?.state).toBe('S2')

      api.restoreDerivedValue(derivedRowId(PRODUCT), 'currentUnadjusted')
      // 注意：此处**不** await nextTick —— 同步器还没跑。
      expect(
        Number(readRawValue(responses, storedId(PRODUCT, 'currentUnadjusted'))),
        '恢复取数当场写进 store 的不是派生值（取了显示值 = 覆盖值）',
      ).toBe(d1)
      expect(Number(readRawValue(responses, snapId(PRODUCT, 'currentUnadjusted')))).toBe(d1)
    } finally {
      dispose()
    }
  })

  it('恢复取数把 stored 与 snap 一并写回当前派生值（下次同步保持 S1，不反弹）', async () => {
    const { responses } = buildResponses([['D4-2-rows', [monthRow(PRODUCT, 100)]]])
    const { api, dispose } = run(responses)
    try {
      await nextTick()
      const d1 = mainRow(api, PRODUCT)!.currentUnadjusted
      setRaw(responses, storedId(PRODUCT, 'currentUnadjusted'), d1 + 1000)
      await nextTick()
      api.restoreDerivedValue(derivedRowId(PRODUCT), 'currentUnadjusted')
      await nextTick()
      expect(Number(readRawValue(responses, storedId(PRODUCT, 'currentUnadjusted')))).toBe(d1)
      expect(Number(readRawValue(responses, snapId(PRODUCT, 'currentUnadjusted')))).toBe(d1)
      // 再触发一次同步（值未变）⇒ 仍是 S1，不回弹成覆盖。
      responses.value.set('D4-2-rows', {
        item_id: 'D4-2-rows',
        conclusion: null,
        remark: JSON.stringify([monthRow(PRODUCT, 100)]),
      })
      await nextTick()
      expect(mainRow(api, PRODUCT)!.cellOverrides).toBeUndefined()
      expect(mainRow(api, PRODUCT)!.currentUnadjusted).toBe(d1)
    } finally {
      dispose()
    }
  })
})
