/**
 * D5-1 逐格覆盖状态机的判据（Property 8）—— 纯函数反证式 + **跑同步器**运行时判据。
 *
 * spec: d567-sync-coverage-via-row-table-engine · Requirements 4.4 / 4.5 / 4.6
 *
 * ═══ 为什么必须有"跑同步器"这一层（上游血泪教训，照抄 D3/D4 的理由）═══
 *
 * `resolveCellState(stored, snap, derived)` 纯函数判据「证明不了这三个量在真实运行里会不会
 * 走到那四态」——上游 **13 条纯函数判据全绿而生产坏掉**，根因是 S4 可达性取决于
 * `syncDerivedCellsIntoStore()` 怎么维护 `snap`（composable 的事，纯函数看不见）。
 * 故本文件既有纯函数反证，也有**真正实例化 useD5Adjudication 跑一遍**的判据。
 *
 * ═══ D5 的派生格 ═══
 *
 * D5-1 是固定行（非动态行），三个 cross_sheet 派生格全在 `currentUnadjusted` 列：
 *   `notes-receivable`（← D5-2 按类别聚合·应收票据）
 *   `accounts-receivable`（← D5-2 按类别聚合·应收账款）
 *   `oci-change`（← D5-4 公允价值变动）
 * 判据构造法同 D3/D4：**不写死聚合口径**，先挂载拿 S1 态的派生值当基准，再据它构造覆盖。
 */
import { describe, it, expect } from 'vitest'
import { ref, computed, effectScope, nextTick, type Ref } from 'vue'
import * as fc from 'fast-check'
import {
  resolveCellState,
  displayValueForCellState,
} from '../shared/dynamicAdjudicationRows'
import { useD5Adjudication } from '../useD5Adjudication'
import type { ChecklistResponse } from '../useD5FormData'

type Responses = Ref<Map<string, ChecklistResponse>>

// ─── crossSheet mock（可注入三个派生源）──────────────────────────────────────

function makeCrossSheet(init: { notes?: number; acc?: number; oci?: number } = {}) {
  const notes = ref(init.notes ?? 0)
  const acc = ref(init.acc ?? 0)
  const oci = ref(init.oci ?? 0)
  return {
    // 三个 ref 暴露出来供测试改上游
    _notes: notes,
    _acc: acc,
    _oci: oci,
    categoryAggregation: computed(() => ({
      notesReceivable: { prior: 0, current: notes.value },
      accountsReceivable: { prior: 0, current: acc.value },
    })),
    ociChange: computed(() => ({ prior: 0, current: oci.value })),
    adjustmentTotals: computed(() => ({ ajeTotal: 0, rjeTotal: 0 })),
  }
}

function run(allResponses: Responses, crossSheet: ReturnType<typeof makeCrossSheet>) {
  const scope = effectScope()
  const debouncedSave = (itemId: string, data: Partial<ChecklistResponse>) => {
    const existing =
      allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
    allResponses.value.set(itemId, { ...existing, ...data } as ChecklistResponse)
  }
  const api = scope.run(() =>
    useD5Adjudication({
      allResponses,
      wpId: ref('wp-test'),
      projectId: ref('proj-test'),
      saveImmediate: async () => {},
      debouncedSave,
      crossSheet: crossSheet as any,
      isReadonly: ref(false),
    }),
  )!
  return { api, dispose: () => scope.stop() }
}

const itemId = (rowKey: string, field: string) => `D5-1-adj-${rowKey}-${field}`
const snapId = (rowKey: string, field: string) => `${itemId(rowKey, field)}-snap`

function setRaw(responses: Responses, id: string, raw: string | number): void {
  responses.value.set(id, { item_id: id, conclusion: null, remark: String(raw) })
}
function readRawValue(responses: Responses, id: string): string {
  return String(responses.value.get(id)?.remark ?? '')
}
function row(api: ReturnType<typeof useD5Adjudication>, rowKey: string) {
  return api.rows.value.find((r) => r.rowKey === rowKey)
}
/** 全表覆盖标记计数（真实 composable 层的 Property 8 观测量）。 */
function countOverrideMarks(api: ReturnType<typeof useD5Adjudication>): number {
  let marks = 0
  for (const r of api.rows.value) {
    if (r.cellOverrides && Object.keys(r.cellOverrides).length > 0) marks += 1
  }
  return marks
}

/** D5 的三个派生格（rowKey + 注入上游值的 ref 名）。 */
const DERIVED_CELLS = [
  { rowKey: 'notes-receivable', src: '_notes' as const },
  { rowKey: 'accounts-receivable', src: '_acc' as const },
  { rowKey: 'oci-change', src: '_oci' as const },
]

// ═══════════════════════════════════════════════════════════════════════════
// Property 8（纯函数反证式）：只改 derived 不改 stored/snap ⇒ 覆盖标记数必须为 0
// **Validates: Requirements 4.4**
// ═══════════════════════════════════════════════════════════════════════════

describe('D5-P8 反证式（纯函数）：只改 derived 不改 stored/snap ⇒ 零覆盖标记', () => {
  it('stored==snap（upstreamChanged 但未 overridden）⇒ 一批格覆盖标记数(S2+S4)恒为 0', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            base: fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
            newDerived: fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
          }),
          { minLength: 1, maxLength: 20 },
        ),
        (cells) => {
          let overrideMarks = 0
          for (const { base, newDerived } of cells) {
            // 🔴 只改 derived：stored = snap = base（未人工覆盖）；derived = newDerived。
            const state = resolveCellState(base, base, newDerived)
            if (state === 'S2' || state === 'S4') overrideMarks += 1
          }
          return overrideMarks === 0
        },
      ),
      { numRuns: 5 },
    )
  })

  it('对照：真改了 stored（stored≠snap）⇒ 覆盖标记出现（证明上一条不是恒真装饰）', () => {
    expect(resolveCellState(100, 50, 50)).toBe('S2')
    expect(resolveCellState(100, 50, 999)).toBe('S4')
    expect(displayValueForCellState('S2', 100, 50)).toBe(100)
    expect(displayValueForCellState('S4', 100, 999)).toBe(100)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 🔴 跑同步器判据（关键）：真正实例化 useD5Adjudication 并跑它的 rows/覆盖计算
// **Validates: Requirements 4.4 / 4.5 / 4.6**
// ═══════════════════════════════════════════════════════════════════════════

describe('D5-P8 跑同步器：真实 composable 里派生格四态可达', () => {
  it('只改上游派生（不改 stored/snap）⇒ 真实 rows 里零覆盖标记（S1/S3 无 override）', async () => {
    const crossSheet = makeCrossSheet({ notes: 100, acc: 300, oci: 50 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      // 挂载后三格都是 S1 纯派生：显示派生值、无 override。
      expect(row(api, 'notes-receivable')!.currentUnadjusted).toBe(100)
      expect(row(api, 'accounts-receivable')!.currentUnadjusted).toBe(300)
      expect(row(api, 'oci-change')!.currentUnadjusted).toBe(50)
      expect(countOverrideMarks(api)).toBe(0)

      // 🔴 只改上游（不碰 stored/snap，同步器把 snap 跟到新值 ⇒ S3 自动跟随）。
      crossSheet._notes.value = 250
      crossSheet._acc.value = 700
      crossSheet._oci.value = 90
      await nextTick()
      expect(row(api, 'notes-receivable')!.currentUnadjusted, 'S3 应跟随上游').toBe(250)
      expect(row(api, 'accounts-receivable')!.currentUnadjusted).toBe(700)
      expect(row(api, 'oci-change')!.currentUnadjusted).toBe(90)
      expect(countOverrideMarks(api), '只改上游派生不该产生任何覆盖标记').toBe(0)
    } finally {
      dispose()
    }
  })

  it.each(DERIVED_CELLS)('S2：手工/OO 覆盖 $rowKey ⇒ 标已覆盖 + 显示覆盖值', async ({ rowKey }) => {
    const crossSheet = makeCrossSheet({ notes: 100, acc: 300, oci: 50 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const derived1 = row(api, rowKey)!.currentUnadjusted
      expect(derived1).toBeGreaterThan(0)
      setRaw(responses, itemId(rowKey, 'currentUnadjusted'), derived1 + 1000)
      await nextTick()
      const r = row(api, rowKey)!
      expect(r.cellOverrides?.currentUnadjusted?.state, '应为 S2（覆盖、上游未变）').toBe('S2')
      expect(r.currentUnadjusted, '显示覆盖值不是派生值').toBe(derived1 + 1000)
    } finally {
      dispose()
    }
  })

  it.each(DERIVED_CELLS)(
    'S4：$rowKey 覆盖后上游再变 ⇒ 三值同时可读且互不相等，系统不自动二选一',
    async ({ rowKey, src }) => {
      const crossSheet = makeCrossSheet({ notes: 100, acc: 300, oci: 50 })
      const responses = ref(new Map<string, ChecklistResponse>()) as Responses
      const { api, dispose } = run(responses, crossSheet)
      try {
        await nextTick()
        const derived1 = row(api, rowKey)!.currentUnadjusted
        const overrideValue = derived1 + 1000
        // 步骤1：覆盖 ⇒ S2。
        setRaw(responses, itemId(rowKey, 'currentUnadjusted'), overrideValue)
        await nextTick()
        expect(row(api, rowKey)!.cellOverrides?.currentUnadjusted?.state).toBe('S2')
        // 步骤2：上游再变 ⇒ S4。
        const newDerived = derived1 + 7
        crossSheet[src].value = newDerived
        await nextTick()
        const cell = row(api, rowKey)!.cellOverrides?.currentUnadjusted
        expect(cell, '覆盖格丢了 cellOverrides —— 覆盖被吞掉').toBeDefined()
        expect(cell!.state, `上游已变后应为 S4，实得 ${cell!.state}`).toBe('S4')
        // 🔴 三值同时可读且互不相等（"系统不自动二选一"的判据面）。
        expect(cell!.stored).toBe(overrideValue) // 覆盖值
        expect(cell!.snap).toBe(derived1) // 原派生值（冻结，不追上 derived）
        expect(cell!.derived).toBe(newDerived) // 现派生值
        expect(new Set([cell!.stored, cell!.snap, cell!.derived]).size).toBe(3)
        expect(row(api, rowKey)!.currentUnadjusted).toBe(overrideValue)
      } finally {
        dispose()
      }
    },
  )

  it('snap 必须在 store 里真的冻结（不只是渲染层算出来的）', async () => {
    const crossSheet = makeCrossSheet({ notes: 100, acc: 300, oci: 50 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const derived1 = row(api, 'notes-receivable')!.currentUnadjusted
      setRaw(responses, itemId('notes-receivable', 'currentUnadjusted'), derived1 + 1000)
      await nextTick()
      crossSheet._notes.value = 250
      await nextTick()
      // store 里的 snap 必须仍是 derived1（覆盖时的派生值），不是新派生 250。
      expect(
        Number(readRawValue(responses, snapId('notes-receivable', 'currentUnadjusted'))),
        'snap 追上了新派生值 ⇒ 覆盖标记会自我擦除',
      ).toBe(derived1)
    } finally {
      dispose()
    }
  })

  it('🔴🔴 覆盖标记不会自我擦除（上游 D4 事故的精确反证）', async () => {
    // 事故形态：同步器把**显示值**当派生值写回 snap。S2 下显示值 == stored ⇒
    // 写完 snap == stored ⇒ 下一轮判「未覆盖」⇒ 覆盖标记消失、用户改的数被上游静默盖掉。
    const crossSheet = makeCrossSheet({ notes: 100, acc: 300, oci: 50 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const derived1 = row(api, 'notes-receivable')!.currentUnadjusted
      setRaw(responses, itemId('notes-receivable', 'currentUnadjusted'), derived1 + 1000)
      await nextTick()
      // 连续多轮上游变动 + 多次同步器跑动，覆盖标记必须一直在。
      for (const v of [250, 260, 270, 100]) {
        crossSheet._notes.value = v
        await nextTick()
        api._syncDerivedCellsIntoStore()
        await nextTick()
        expect(
          row(api, 'notes-receivable')!.cellOverrides?.currentUnadjusted,
          `上游变到 ${v} 后覆盖标记被擦除`,
        ).toBeDefined()
        expect(row(api, 'notes-receivable')!.currentUnadjusted).toBe(derived1 + 1000)
      }
    } finally {
      dispose()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 🔴 `snap === null` 降级（迁移前存过值的格）—— D1 实测回归的 D5 同形反证
// **Validates: Requirements 4.4 / 4.5**
// ═══════════════════════════════════════════════════════════════════════════

describe('D5-P8 snap 为 null 的降级（迁移前的格 / 同步器没跑过）', () => {
  it('🔴 stored 为 "0"（旧版自动存过 0）+ 无 snap ⇒ 必须显示上游派生值，不得显示 0', async () => {
    // 不降级会算成 S4（overridden=(0≠null)=true）⇒ 显示 stored=0 ⇒ 上游 100 被吞；
    // 且同步器判 S4 后不再写 snap ⇒ snap 永远 null ⇒ 永久显示 0，**不可自愈**。
    const crossSheet = makeCrossSheet({ notes: 100 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    setRaw(responses, itemId('notes-receivable', 'currentUnadjusted'), '0')
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      expect(
        row(api, 'notes-receivable')!.currentUnadjusted,
        'stored=0 且无 snap 被判成覆盖态 ⇒ 上游派生值被显示成 0',
      ).toBe(100)
      expect(row(api, 'notes-receivable')!.cellOverrides).toBeUndefined()
      // 自愈：同步器应已把 snap 写上，后续上游变动可正常跟随（S3）。
      expect(Number(readRawValue(responses, snapId('notes-receivable', 'currentUnadjusted')))).toBe(100)
      crossSheet._notes.value = 420
      await nextTick()
      expect(row(api, 'notes-receivable')!.currentUnadjusted, '降级后仍应能跟随上游').toBe(420)
    } finally {
      dispose()
    }
  })

  it('对照：stored 非零 + 无 snap ⇒ 判 S2 保住手工值（证明上一条不是把降级做成恒 S1）', async () => {
    const crossSheet = makeCrossSheet({ notes: 100 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    setRaw(responses, itemId('notes-receivable', 'currentUnadjusted'), '888')
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const r = row(api, 'notes-receivable')!
      expect(r.cellOverrides?.currentUnadjusted?.state, '迁移前的手工值应判 S2').toBe('S2')
      expect(r.currentUnadjusted, '手工值被上游盖掉了').toBe(888)
    } finally {
      dispose()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 恢复取数：只影响被点那一格，且当场写对
// **Validates: Requirements 4.6**
// ═══════════════════════════════════════════════════════════════════════════

describe('D5-P8 恢复取数：作用域一格 + 当场写对', () => {
  it('恢复取数把被点格退回 S1（显示派生值、无 override）', async () => {
    const crossSheet = makeCrossSheet({ notes: 100, acc: 300, oci: 50 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const derived1 = row(api, 'notes-receivable')!.currentUnadjusted
      setRaw(responses, itemId('notes-receivable', 'currentUnadjusted'), derived1 + 1000)
      await nextTick()
      expect(row(api, 'notes-receivable')!.cellOverrides?.currentUnadjusted?.state).toBe('S2')

      api.restoreDerivedValue('notes-receivable', 'currentUnadjusted')
      // 🔴 当场（不 await）store 里应已是派生值，不靠下一 tick 自愈。
      expect(
        Number(readRawValue(responses, itemId('notes-receivable', 'currentUnadjusted'))),
        '恢复取数当场写进 store 的不是派生值',
      ).toBe(derived1)
      expect(Number(readRawValue(responses, snapId('notes-receivable', 'currentUnadjusted')))).toBe(derived1)

      await nextTick()
      const r = row(api, 'notes-receivable')!
      expect(r.cellOverrides?.currentUnadjusted, '恢复后应回 S1，无 override').toBeUndefined()
      expect(r.currentUnadjusted).toBe(derived1)
    } finally {
      dispose()
    }
  })

  it('恢复一格不影响另两个派生格（同列其他格保持覆盖态）', async () => {
    const crossSheet = makeCrossSheet({ notes: 100, acc: 300, oci: 50 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const base: Record<string, number> = {}
      for (const { rowKey } of DERIVED_CELLS) {
        base[rowKey] = row(api, rowKey)!.currentUnadjusted
        setRaw(responses, itemId(rowKey, 'currentUnadjusted'), base[rowKey] + 1000)
      }
      await nextTick()
      for (const { rowKey } of DERIVED_CELLS) {
        expect(row(api, rowKey)!.cellOverrides?.currentUnadjusted).toBeDefined()
      }

      api.restoreDerivedValue('notes-receivable', 'currentUnadjusted')
      await nextTick()
      expect(row(api, 'notes-receivable')!.cellOverrides?.currentUnadjusted).toBeUndefined()
      for (const rowKey of ['accounts-receivable', 'oci-change']) {
        expect(
          row(api, rowKey)!.cellOverrides?.currentUnadjusted,
          `${rowKey} 被连带恢复了`,
        ).toBeDefined()
        expect(row(api, rowKey)!.currentUnadjusted).toBe(base[rowKey] + 1000)
      }
    } finally {
      dispose()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// D5 特有：覆盖值必须参与下游公式（小计 / 公允价值合计 = 小计 − OCI）
// **Validates: Requirements 4.5**
// ═══════════════════════════════════════════════════════════════════════════

describe('D5-P8 覆盖值参与下游公式（D5 的 OCI 扣减结构）', () => {
  it('覆盖应收票据 ⇒ 小计与公允价值合计都用覆盖值重算（不是仍用派生值）', async () => {
    const crossSheet = makeCrossSheet({ notes: 100, acc: 300, oci: 50 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      expect(row(api, 'subtotal')!.currentUnadjusted).toBe(400) // 100 + 300
      // 覆盖应收票据 100 → 1000。
      setRaw(responses, itemId('notes-receivable', 'currentUnadjusted'), 1000)
      await nextTick()
      expect(row(api, 'subtotal')!.currentUnadjusted, '小计没用覆盖值重算').toBe(1300)
      // 公允价值合计 = 小计 − OCI变动 = 1300 − 50。
      expect(row(api, 'fv-total')!.currentUnadjusted, 'FV合计没用覆盖值重算').toBe(1250)
    } finally {
      dispose()
    }
  })
})
