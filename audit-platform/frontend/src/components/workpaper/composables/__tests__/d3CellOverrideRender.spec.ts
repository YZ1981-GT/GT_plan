/**
 * D3-1 逐格覆盖状态机的判据（Task 14）—— 纯函数反证式（Property 8）+ **跑同步器**运行时判据。
 *
 * spec: d3-sync-coverage-via-row-table-engine · Task 14 · Requirements 4.4 / 4.5 / 4.6 / 6.1
 *
 * ═══ 为什么要有"跑同步器"这一层（上游血泪教训）═══
 *
 * `d4CellOverrideRender.spec.ts` 原话：`resolveCellState(stored, snap, derived)` 纯函数判据
 * 「证明不了这三个量在真实运行里会不会走到那四态」——上游 13 条纯函数判据全绿而生产坏掉，
 * 根因是 S4 可达性取决于 `syncDerivedCellsIntoStore()` 怎么维护 `snap`（composable 的事）。
 * 故本文件既有纯函数反证（Property 8），又有**真正实例化 useD3Adjudication 跑一遍它的
 * sections/覆盖计算**的判据（喂真实 allResponses 含 D3-2 跨 sheet 聚合 + 手工覆盖）。
 *
 * 判据构造法（同 D4）：不写死聚合口径，先挂载拿 S1 态的派生值当基准，再据它构造覆盖/上游变化。
 */
import { describe, it, expect } from 'vitest'
import { ref, effectScope, nextTick, type Ref } from 'vue'
import * as fc from 'fast-check'
import {
  resolveCellState,
  displayValueForCellState,
} from '../shared/dynamicAdjudicationRows'
import { useD3Adjudication, NATURE_ROWS } from '../useD3Adjudication'
import type { ChecklistResponse } from '../useD3FormData'

type Responses = Ref<Map<string, ChecklistResponse>>

// ─── crossSheet mock（可注入各性质 label 的 current/prior 聚合值）────────────────

function makeCrossSheet(natureCurrent: Record<string, number> = {}) {
  const natureAggregation = ref<Record<string, { prior: number; current: number }>>(
    Object.fromEntries(
      Object.entries(natureCurrent).map(([label, current]) => [label, { current, prior: 0 }]),
    ),
  )
  return {
    natureAggregation,
    agingAggregation: ref({
      within1: 0, y1to2: 0, y2to3: 0, over3: 0,
      prior_within1: 0, prior_y1to2: 0, prior_y2to3: 0, prior_over3: 0,
    }),
    agingByKey: ref({
      current: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 },
      prior: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 },
    }),
    agingSegments: ref([
      { key: 'within1', label: '1年以内', dayFrom: 0, dayTo: 365 },
      { key: 'y1to2', label: '1-2年', dayFrom: 366, dayTo: 730 },
      { key: 'y2to3', label: '2-3年', dayFrom: 731, dayTo: 1095 },
      { key: 'over3', label: '3年以上', dayFrom: 1096, dayTo: null },
    ]),
    longTermRows: ref([]),
    relatedPartyRows: ref([]),
    adjustmentTotals: ref({ ajeTotal: 0, rjeTotal: 0 }),
    adjudicationForDisclosure: ref({ natureAggregation: {}, agingAggregation: {}, longTermRows: [] }),
    postPeriodSettlementSync: ref({ byCustomer: {}, total: 0 }),
    crossSheetStatus: ref('loaded' as const),
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
    useD3Adjudication({
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

/** 第一个性质行（`预收销售固定资产款` 等，从真源常量取）——派生格挂在它的 currentUnadjusted。 */
const FIRST_NATURE = NATURE_ROWS[0]
const itemId = (rowKey: string, field: string) => `D3-adj-nature-${rowKey}-${field}`
const snapId = (rowKey: string, field: string) => `${itemId(rowKey, field)}-snap`

function setRaw(responses: Responses, id: string, raw: string | number): void {
  responses.value.set(id, { item_id: id, conclusion: null, remark: String(raw) })
}
function readRawValue(responses: Responses, id: string): string {
  return String(responses.value.get(id)?.remark ?? '')
}

/** 从 sections 性质区取某派生行。 */
function natureRow(api: ReturnType<typeof useD3Adjudication>, rowKey: string) {
  return api.sections.value[0]?.rows.find((r) => r.rowKey === rowKey)
}


// ═══════════════════════════════════════════════════════════════════════════
// Property 8（纯函数反证式）：只改 derived 不改 stored/snap ⇒ 覆盖标记数必须为 0
// **Validates: Requirements 4.4**
// ═══════════════════════════════════════════════════════════════════════════

describe('D3-P8 反证式（纯函数）：只改 derived 不改 stored/snap ⇒ 零覆盖标记', () => {
  it('stored==snap（upstreamChanged 但未 overridden）⇒ 一批格覆盖标记数(S2+S4)恒为 0', () => {
    fc.assert(
      fc.property(
        // 一批格：每格 base（stored==snap 的值）+ 新 derived（只改上游）
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
            // 🔴 只改 derived：stored = snap = base（未人工覆盖）；derived = newDerived（上游变了）。
            const state = resolveCellState(base, base, newDerived)
            if (state === 'S2' || state === 'S4') overrideMarks += 1
          }
          // 未 overridden（stored==snap）⇒ 只可能 S1（上游没变）或 S3（上游变了自动跟随），
          //   绝不可能 S2/S4 ⇒ 覆盖标记数必须为 0。
          return overrideMarks === 0
        },
      ),
      { numRuns: 5 },
    )
  })

  it('对照：真改了 stored（stored≠snap）⇒ 覆盖标记出现（证明上一条不是恒真装饰）', () => {
    // stored 与 snap 不同 = 人工覆盖，必产生 S2（上游没变）或 S4（上游也变了）。
    expect(resolveCellState(100, 50, 50)).toBe('S2')
    expect(resolveCellState(100, 50, 999)).toBe('S4')
    // 显示值：S2/S4 显示 stored（覆盖值），不显示 derived。
    expect(displayValueForCellState('S2', 100, 50)).toBe(100)
    expect(displayValueForCellState('S4', 100, 999)).toBe(100)
  })
})


// ═══════════════════════════════════════════════════════════════════════════
// 🔴 跑同步器判据（关键）：真正实例化 useD3Adjudication 并跑它的 sections/覆盖计算。
// **Validates: Requirements 4.4 / 4.5 / 4.6**
// ═══════════════════════════════════════════════════════════════════════════

describe('D3-P8 跑同步器：真实 composable 里派生格四态可达', () => {
  it('只改上游派生（不改 stored/snap）⇒ 真实 sections 里零覆盖标记（S1/S3 无 override）', async () => {
    const crossSheet = makeCrossSheet({ [FIRST_NATURE.label]: 100 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      // 挂载后是 S1 纯派生：显示派生值、无 override。
      expect(natureRow(api, FIRST_NATURE.rowKey)!.currentUnadjusted).toBe(100)
      expect(natureRow(api, FIRST_NATURE.rowKey)!.cellOverrides).toBeUndefined()

      // 🔴 只改上游派生（不碰 stored/snap，同步器会把 snap 跟到新值 ⇒ S3 自动跟随）。
      crossSheet.natureAggregation.value = { [FIRST_NATURE.label]: { current: 250, prior: 0 } }
      await nextTick()
      const row = natureRow(api, FIRST_NATURE.rowKey)!
      expect(row.currentUnadjusted, 'S3 应跟随上游到新派生值').toBe(250)
      // 全表零覆盖标记（真实 composable 层的 Property 8）。
      let marks = 0
      for (const sec of api.sections.value) for (const r of sec.rows) {
        if (r.cellOverrides && Object.keys(r.cellOverrides).length > 0) marks += 1
      }
      expect(marks, '只改上游派生不该产生任何覆盖标记').toBe(0)
    } finally {
      dispose()
    }
  })

  it('S2：OO/手工覆盖派生格 ⇒ 标「已人工覆盖」+ 显示覆盖值', async () => {
    const crossSheet = makeCrossSheet({ [FIRST_NATURE.label]: 100 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const derived1 = natureRow(api, FIRST_NATURE.rowKey)!.currentUnadjusted
      expect(derived1).toBe(100)
      // 模拟人工/OO 覆盖：把 stored 改大（snap 仍是派生值 100）。
      setRaw(responses, itemId(FIRST_NATURE.rowKey, 'currentUnadjusted'), derived1 + 1000)
      await nextTick()
      const row = natureRow(api, FIRST_NATURE.rowKey)!
      expect(row.cellOverrides?.currentUnadjusted?.state, '应为 S2（覆盖、上游未变）').toBe('S2')
      expect(row.currentUnadjusted, '显示覆盖值不是派生值').toBe(derived1 + 1000)
    } finally {
      dispose()
    }
  })

  it('S4：覆盖后上游再变 ⇒ 三值(覆盖值/原派生值/现派生值)同时可读且互不相等，系统不自动二选一', async () => {
    const crossSheet = makeCrossSheet({ [FIRST_NATURE.label]: 100 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const derived1 = natureRow(api, FIRST_NATURE.rowKey)!.currentUnadjusted
      const overrideValue = derived1 + 1000
      // 步骤1：覆盖 ⇒ S2。
      setRaw(responses, itemId(FIRST_NATURE.rowKey, 'currentUnadjusted'), overrideValue)
      await nextTick()
      expect(natureRow(api, FIRST_NATURE.rowKey)!.cellOverrides?.currentUnadjusted?.state).toBe('S2')
      // 步骤2：上游再变 ⇒ S4。
      crossSheet.natureAggregation.value = { [FIRST_NATURE.label]: { current: 250, prior: 0 } }
      await nextTick()
      const cell = natureRow(api, FIRST_NATURE.rowKey)!.cellOverrides?.currentUnadjusted
      expect(cell, '覆盖格丢了 cellOverrides —— 覆盖被吞掉').toBeDefined()
      expect(cell!.state, `上游已变后应为 S4，实得 ${cell!.state}`).toBe('S4')
      // 🔴 三值同时可读且互不相等（"系统不自动二选一"的判据面）。
      expect(cell!.stored).toBe(overrideValue) // 覆盖值
      expect(cell!.snap).toBe(derived1) // 原派生值（冻结，不追上 derived）
      expect(cell!.derived).toBe(250) // 现派生值
      expect(new Set([cell!.stored, cell!.snap, cell!.derived]).size).toBe(3)
      // 显示值仍是覆盖值。
      expect(natureRow(api, FIRST_NATURE.rowKey)!.currentUnadjusted).toBe(overrideValue)
    } finally {
      dispose()
    }
  })

  it('snap 必须在 store 里真的冻结（不只是渲染层算出来的）', async () => {
    const crossSheet = makeCrossSheet({ [FIRST_NATURE.label]: 100 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const derived1 = natureRow(api, FIRST_NATURE.rowKey)!.currentUnadjusted
      setRaw(responses, itemId(FIRST_NATURE.rowKey, 'currentUnadjusted'), derived1 + 1000)
      await nextTick()
      crossSheet.natureAggregation.value = { [FIRST_NATURE.label]: { current: 250, prior: 0 } }
      await nextTick()
      // store 里的 snap 必须仍是 derived1（覆盖时的派生值），不是新派生 250。
      expect(Number(readRawValue(responses, snapId(FIRST_NATURE.rowKey, 'currentUnadjusted')))).toBe(derived1)
    } finally {
      dispose()
    }
  })
})


// ═══════════════════════════════════════════════════════════════════════════
// 恢复取数（需求 4.6 / 6.5）：只影响被点那一格，且当场写对
// ═══════════════════════════════════════════════════════════════════════════

describe('D3-P8 恢复取数：作用域一格 + 当场写对', () => {
  it('恢复取数把被点格退回 S1（显示派生值、无 override）', async () => {
    const crossSheet = makeCrossSheet({ [FIRST_NATURE.label]: 100 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const derived1 = natureRow(api, FIRST_NATURE.rowKey)!.currentUnadjusted
      setRaw(responses, itemId(FIRST_NATURE.rowKey, 'currentUnadjusted'), derived1 + 1000)
      await nextTick()
      expect(natureRow(api, FIRST_NATURE.rowKey)!.cellOverrides?.currentUnadjusted?.state).toBe('S2')

      api.restoreDerivedValue('nature', FIRST_NATURE.rowKey, 'currentUnadjusted')
      // 🔴 当场（不 await）store 里应已是派生值，不靠下一 tick 自愈。
      expect(
        Number(readRawValue(responses, itemId(FIRST_NATURE.rowKey, 'currentUnadjusted'))),
        '恢复取数当场写进 store 的不是派生值',
      ).toBe(derived1)
      expect(Number(readRawValue(responses, snapId(FIRST_NATURE.rowKey, 'currentUnadjusted')))).toBe(derived1)

      await nextTick()
      const row = natureRow(api, FIRST_NATURE.rowKey)!
      expect(row.cellOverrides?.currentUnadjusted, '恢复后应回 S1，无 override').toBeUndefined()
      expect(row.currentUnadjusted).toBe(derived1)
    } finally {
      dispose()
    }
  })

  it('恢复一行不影响另一派生行（同列其他行保持覆盖态）', async () => {
    const second = NATURE_ROWS[1]
    const crossSheet = makeCrossSheet({ [FIRST_NATURE.label]: 100, [second.label]: 300 })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const d1 = natureRow(api, FIRST_NATURE.rowKey)!.currentUnadjusted
      const d2 = natureRow(api, second.rowKey)!.currentUnadjusted
      setRaw(responses, itemId(FIRST_NATURE.rowKey, 'currentUnadjusted'), d1 + 1000)
      setRaw(responses, itemId(second.rowKey, 'currentUnadjusted'), d2 + 1000)
      await nextTick()
      expect(natureRow(api, FIRST_NATURE.rowKey)!.cellOverrides?.currentUnadjusted).toBeDefined()
      expect(natureRow(api, second.rowKey)!.cellOverrides?.currentUnadjusted).toBeDefined()

      api.restoreDerivedValue('nature', FIRST_NATURE.rowKey, 'currentUnadjusted')
      await nextTick()
      expect(natureRow(api, FIRST_NATURE.rowKey)!.cellOverrides?.currentUnadjusted).toBeUndefined()
      expect(
        natureRow(api, second.rowKey)!.cellOverrides?.currentUnadjusted,
        '另一行被连带恢复了',
      ).toBeDefined()
      expect(natureRow(api, second.rowKey)!.currentUnadjusted).toBe(d2 + 1000)
    } finally {
      dispose()
    }
  })
})
