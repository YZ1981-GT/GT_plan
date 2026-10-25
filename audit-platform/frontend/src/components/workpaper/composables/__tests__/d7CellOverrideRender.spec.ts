/**
 * D7-1 逐格覆盖状态机的判据（Property 8）—— 纯函数反证式 + **跑同步器**运行时判据。
 *
 * spec: d567-sync-coverage-via-row-table-engine · Requirements 4.4 / 4.5 / 4.6
 *
 * ═══ 为什么必须有"跑同步器"这一层（上游血泪教训）═══
 *
 * `resolveCellState(stored, snap, derived)` 纯函数判据「证明不了这三个量在真实运行里会不会
 * 走到那四态」——上游 **13 条纯函数判据全绿而生产坏掉**，根因是 S4 可达性取决于
 * `syncDerivedCellsIntoStore()` 怎么维护 `snap`。故本文件除纯函数反证外，**真正实例化
 * useD7Adjudication** 跑它的 natureRows/agingRows。
 *
 * ═══ D7 的派生格（三家里最多）═══
 *
 * 双区块 × 两列 = 四组：
 *   nature（4 固定行）× {priorUnadjusted, currentUnadjusted} ← `crossSheet.natureAggregation`
 *   aging（按账龄配置段动态）× {priorUnadjusted, currentUnadjusted} ← `crossSheet.agingByKey`
 * item_id 形态 `D7-1-adj-{block}-{rowKey}-{field}`，快照键 `{itemId}-snap`。
 *
 * 🔴 改造前两区块各有一处反模式，本文件逐一反证：
 *   nature：`agg ? agg.prior : manual` —— 聚合对象**一存在就无条件盖掉手工值**；
 *   aging： `isFromCrossSheet = crossCurrent !== 0 || crossPrior !== 0` —— **一个标志管两列**，
 *           current 非零就把 prior 也切到 cross（哪怕 crossPrior 为 0）。
 */
import { describe, it, expect } from 'vitest'
import { ref, computed, effectScope, nextTick, type Ref } from 'vue'
import * as fc from 'fast-check'
import {
  resolveCellState,
  displayValueForCellState,
  resolvePerCellDerivedState,
} from '../shared/dynamicAdjudicationRows'
import { useD7Adjudication } from '../useD7Adjudication'
import { PRESET_SEGMENTS } from '@/composables/useAgingConfig'
import type { ChecklistResponse } from '../useD7FormData'

type Responses = Ref<Map<string, ChecklistResponse>>

const SEGS = PRESET_SEGMENTS.THREE_YEAR
/** 默认 THREE_YEAR 段 key → 审定表 rowKey（与 composable 内 LEGACY_AGING_ROWKEY 同源口径）。 */
const AGING_ROWKEY: Record<string, string> = {
  within1: 'within-1-year',
  y1to2: '1-to-2-years',
  y2to3: '2-to-3-years',
  over3: 'over-3-years',
}

// ─── crossSheet mock（可注入 nature 四性质 + aging 各段的 prior/current）──────────

function makeCrossSheet(init?: {
  nature?: Record<string, { prior: number; current: number }>
  agingCurrent?: Record<string, number>
  agingPrior?: Record<string, number>
}) {
  const nature = ref(
    init?.nature ?? {
      revenue: { prior: 10, current: 100 },
      development: { prior: 20, current: 200 },
      engineering: { prior: 30, current: 300 },
      other: { prior: 40, current: 400 },
    },
  )
  const agingCurrent = ref(init?.agingCurrent ?? { within1: 500, y1to2: 600, y2to3: 700, over3: 800 })
  const agingPrior = ref(init?.agingPrior ?? { within1: 50, y1to2: 60, y2to3: 70, over3: 80 })
  const zeroAdj = { aje: 0, rje: 0 }
  return {
    _nature: nature,
    _agingCurrent: agingCurrent,
    _agingPrior: agingPrior,
    natureAggregation: computed(() => nature.value),
    agingByKey: computed(() => ({ current: agingCurrent.value, prior: agingPrior.value })),
    agingSegments: computed(() => SEGS),
    agingAggregation: computed(() => ({})),
    adjustmentTotals: computed(() => ({
      totalAje: 0,
      totalRje: 0,
      byNature: { revenue: zeroAdj, development: zeroAdj, engineering: zeroAdj, other: zeroAdj },
      byAging: { within1: zeroAdj, y1to2: zeroAdj, y2to3: zeroAdj, over3: zeroAdj },
    })),
    crossValidation: computed(() => ({ isConsistent: true, diff: 0 })),
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
    useD7Adjudication({
      allResponses,
      crossSheet: crossSheet as any,
      saveImmediate: async () => {},
      debouncedSave,
      wpId: ref('wp-test'),
      projectId: ref('proj-test'),
      isReadonly: ref(false),
    }),
  )!
  return { api, dispose: () => scope.stop() }
}

const itemId = (block: string, rowKey: string, field: string) => `D7-1-adj-${block}-${rowKey}-${field}`
const snapId = (block: string, rowKey: string, field: string) => `${itemId(block, rowKey, field)}-snap`

function setRaw(responses: Responses, id: string, raw: string | number): void {
  responses.value.set(id, { item_id: id, conclusion: null, remark: String(raw) })
  responses.value = new Map(responses.value)
}
function readRawValue(responses: Responses, id: string): string {
  return String(responses.value.get(id)?.remark ?? '')
}
type Api = ReturnType<typeof useD7Adjudication>
function natureRow(api: Api, rowKey: string) {
  return api.natureRows.value.find((r) => r.rowKey === rowKey)
}
function agingRow(api: Api, rowKey: string) {
  return api.agingRows.value.find((r) => r.rowKey === rowKey)
}
function rowOf(api: Api, block: string, rowKey: string) {
  return block === 'nature' ? natureRow(api, rowKey) : agingRow(api, rowKey)
}
/** 全表（两区块）覆盖标记数。 */
function countOverrideMarks(api: Api): number {
  let marks = 0
  for (const r of [...api.natureRows.value, ...api.agingRows.value]) {
    if (r.cellOverrides) marks += Object.keys(r.cellOverrides).length
  }
  return marks
}

/** 四组派生格的代表（两区块 × 两列），用于 it.each 穷举。 */
const DERIVED_CELLS = [
  { block: 'nature', rowKey: 'revenue', field: 'priorUnadjusted', bump: (cs: any) => { cs._nature.value = { ...cs._nature.value, revenue: { ...cs._nature.value.revenue, prior: 17 } } } },
  { block: 'nature', rowKey: 'revenue', field: 'currentUnadjusted', bump: (cs: any) => { cs._nature.value = { ...cs._nature.value, revenue: { ...cs._nature.value.revenue, current: 177 } } } },
  { block: 'aging', rowKey: AGING_ROWKEY.within1, field: 'priorUnadjusted', bump: (cs: any) => { cs._agingPrior.value = { ...cs._agingPrior.value, within1: 57 } } },
  { block: 'aging', rowKey: AGING_ROWKEY.within1, field: 'currentUnadjusted', bump: (cs: any) => { cs._agingCurrent.value = { ...cs._agingCurrent.value, within1: 577 } } },
] as const

// ═══════════════════════════════════════════════════════════════════════════
// Property 8（纯函数反证式）：只改 derived 不改 stored/snap ⇒ 覆盖标记数必须为 0
// **Validates: Requirements 4.4**
// ═══════════════════════════════════════════════════════════════════════════

describe('D7-P8 反证式（纯函数）：只改 derived 不改 stored/snap ⇒ 零覆盖标记', () => {
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

  it('共享降级：snap=null 时 stored=0 判 S1 显示 derived / stored 非零判 S2 显示 stored', () => {
    // 与 D5/D6 共用同一实现（`resolvePerCellDerivedState`），此处钉死语义防三家各自漂移。
    const zero = resolvePerCellDerivedState(0, null, 100)
    expect(zero.state).toBe('S1')
    expect(zero.display).toBe(100)
    const nonZero = resolvePerCellDerivedState(888, null, 100)
    expect(nonZero.state).toBe('S2')
    expect(nonZero.display).toBe(888)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 🔴 跑同步器判据：真正实例化 useD7Adjudication 并跑 natureRows / agingRows
// **Validates: Requirements 4.4 / 4.5 / 4.6**
// ═══════════════════════════════════════════════════════════════════════════

describe('D7-P8 跑同步器：真实 composable 里两区块四态可达', () => {
  it('挂载即 S1 纯派生：两区块两列都显示派生值、零覆盖标记', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      expect(natureRow(api, 'revenue')!.priorUnadjusted).toBe(10)
      expect(natureRow(api, 'revenue')!.currentUnadjusted).toBe(100)
      expect(agingRow(api, AGING_ROWKEY.within1)!.priorUnadjusted).toBe(50)
      expect(agingRow(api, AGING_ROWKEY.within1)!.currentUnadjusted).toBe(500)
      expect(countOverrideMarks(api)).toBe(0)
    } finally {
      dispose()
    }
  })

  it('只改上游派生 ⇒ 两区块都跟随（S3），且零覆盖标记', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      crossSheet._nature.value = { ...crossSheet._nature.value, revenue: { prior: 11, current: 111 } }
      crossSheet._agingCurrent.value = { ...crossSheet._agingCurrent.value, within1: 555 }
      crossSheet._agingPrior.value = { ...crossSheet._agingPrior.value, within1: 55 }
      await nextTick()
      expect(natureRow(api, 'revenue')!.priorUnadjusted).toBe(11)
      expect(natureRow(api, 'revenue')!.currentUnadjusted).toBe(111)
      expect(agingRow(api, AGING_ROWKEY.within1)!.priorUnadjusted).toBe(55)
      expect(agingRow(api, AGING_ROWKEY.within1)!.currentUnadjusted).toBe(555)
      expect(countOverrideMarks(api), '只改上游派生不该产生任何覆盖标记').toBe(0)
    } finally {
      dispose()
    }
  })

  it.each(DERIVED_CELLS)(
    'S2：覆盖 $block/$rowKey/$field ⇒ 标已覆盖 + 显示覆盖值',
    async ({ block, rowKey, field }) => {
      const crossSheet = makeCrossSheet()
      const responses = ref(new Map<string, ChecklistResponse>()) as Responses
      const { api, dispose } = run(responses, crossSheet)
      try {
        await nextTick()
        const derived1 = (rowOf(api, block, rowKey) as any)[field] as number
        expect(derived1).toBeGreaterThan(0)
        setRaw(responses, itemId(block, rowKey, field), derived1 + 1000)
        await nextTick()
        const r = rowOf(api, block, rowKey)!
        expect(r.cellOverrides?.[field]?.state, '应为 S2（覆盖、上游未变）').toBe('S2')
        expect((r as any)[field], '显示覆盖值不是派生值').toBe(derived1 + 1000)
      } finally {
        dispose()
      }
    },
  )

  it.each(DERIVED_CELLS)(
    'S4：$block/$rowKey/$field 覆盖后上游再变 ⇒ 三值同时可读且互不相等',
    async ({ block, rowKey, field, bump }) => {
      const crossSheet = makeCrossSheet()
      const responses = ref(new Map<string, ChecklistResponse>()) as Responses
      const { api, dispose } = run(responses, crossSheet)
      try {
        await nextTick()
        const derived1 = (rowOf(api, block, rowKey) as any)[field] as number
        const overrideValue = derived1 + 1000
        setRaw(responses, itemId(block, rowKey, field), overrideValue)
        await nextTick()
        expect(rowOf(api, block, rowKey)!.cellOverrides?.[field]?.state).toBe('S2')

        bump(crossSheet as any)
        await nextTick()
        const cell = rowOf(api, block, rowKey)!.cellOverrides?.[field]
        expect(cell, '覆盖格丢了 cellOverrides —— 覆盖被吞掉').toBeDefined()
        expect(cell!.state, `上游已变后应为 S4，实得 ${cell!.state}`).toBe('S4')
        expect(cell!.stored).toBe(overrideValue)
        expect(cell!.snap, '原派生值没冻结').toBe(derived1)
        expect(new Set([cell!.stored, cell!.snap, cell!.derived]).size).toBe(3)
        expect((rowOf(api, block, rowKey) as any)[field]).toBe(overrideValue)
      } finally {
        dispose()
      }
    },
  )

  it('🔴🔴 覆盖标记不会自我擦除（上游 D4 事故的精确反证）', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const derived1 = natureRow(api, 'revenue')!.currentUnadjusted
      setRaw(responses, itemId('nature', 'revenue', 'currentUnadjusted'), derived1 + 1000)
      await nextTick()
      for (const v of [150, 160, 170, 100]) {
        crossSheet._nature.value = {
          ...crossSheet._nature.value,
          revenue: { ...crossSheet._nature.value.revenue, current: v },
        }
        await nextTick()
        api._syncDerivedCellsIntoStore()
        await nextTick()
        expect(
          natureRow(api, 'revenue')!.cellOverrides?.currentUnadjusted,
          `上游变到 ${v} 后覆盖标记被擦除`,
        ).toBeDefined()
        expect(natureRow(api, 'revenue')!.currentUnadjusted).toBe(derived1 + 1000)
      }
      // snap 在 store 里真的冻结。
      expect(
        Number(readRawValue(responses, snapId('nature', 'revenue', 'currentUnadjusted'))),
      ).toBe(derived1)
    } finally {
      dispose()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 🔴 D7 改造前两处反模式的精确反证
// **Validates: Requirements 4.5**
// ═══════════════════════════════════════════════════════════════════════════

describe('D7-P8 改造前反模式的反证', () => {
  it('🔴 nature 区：聚合对象存在时手工值不再被无条件盖掉（原 `agg ? agg.X : manual`）', async () => {
    // 改造前：`agg` 一存在就取 `agg.prior`/`agg.current`，手工值永远无效（连 `!== 0` 都没有）。
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      setRaw(responses, itemId('nature', 'development', 'currentUnadjusted'), 9999)
      await nextTick()
      const r = natureRow(api, 'development')!
      expect(r.currentUnadjusted, '聚合存在时手工覆盖被吞 ⇒ 反模式未修掉').toBe(9999)
      expect(r.cellOverrides?.currentUnadjusted?.state).toBe('S2')
    } finally {
      dispose()
    }
  })

  it('🔴 aging 区：两列独立判定（原一个 isFromCrossSheet 标志管两列）', async () => {
    // 改造前：`isFromCrossSheet = crossCurrent !== 0 || crossPrior !== 0` 对两列共用 ——
    // current 非零就把 prior 也切到 cross（crossPrior=0 时期初手工值被吞成 0）。
    const crossSheet = makeCrossSheet({
      agingCurrent: { within1: 500, y1to2: 0, y2to3: 0, over3: 0 },
      agingPrior: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 },
    })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    // 期初是人工录入（派生源为 0），期末由上游派生。
    setRaw(responses, itemId('aging', AGING_ROWKEY.within1, 'priorUnadjusted'), 777)
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const r = agingRow(api, AGING_ROWKEY.within1)!
      expect(r.priorUnadjusted, '期末有派生值就把期初手工值切成 0 ⇒ 反模式未修掉').toBe(777)
      expect(r.currentUnadjusted, '期末应跟随派生').toBe(500)
      // 两列状态独立：prior 是覆盖态，current 是纯派生。
      expect(r.cellOverrides?.priorUnadjusted?.state).toBe('S2')
      expect(r.cellOverrides?.currentUnadjusted).toBeUndefined()
    } finally {
      dispose()
    }
  })

  it('派生值恰为 0 时不再被误当成「无派生源」（原 `!== 0` 判据的盲区）', async () => {
    const crossSheet = makeCrossSheet({
      agingCurrent: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 },
      agingPrior: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 },
    })
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      // 上游真的是 0（该段无明细）⇒ S1 显示 0，且 snap 已落地（可后续跟随）。
      expect(agingRow(api, AGING_ROWKEY.y1to2)!.currentUnadjusted).toBe(0)
      expect(
        readRawValue(responses, snapId('aging', AGING_ROWKEY.y1to2, 'currentUnadjusted')),
        '派生值为 0 时 snap 没落地 ⇒ 后续无法区分覆盖与跟随',
      ).toBe('0')
      crossSheet._agingCurrent.value = { ...crossSheet._agingCurrent.value, y1to2: 321 }
      await nextTick()
      expect(agingRow(api, AGING_ROWKEY.y1to2)!.currentUnadjusted, '应跟随上游').toBe(321)
      expect(agingRow(api, AGING_ROWKEY.y1to2)!.cellOverrides).toBeUndefined()
    } finally {
      dispose()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 恢复取数：只影响被点那一格（跨区块也不串）
// **Validates: Requirements 4.6**
// ═══════════════════════════════════════════════════════════════════════════

describe('D7-P8 恢复取数：作用域一格 + 当场写对', () => {
  it('恢复取数把被点格退回 S1，且当场写进 store', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const derived1 = natureRow(api, 'revenue')!.currentUnadjusted
      setRaw(responses, itemId('nature', 'revenue', 'currentUnadjusted'), derived1 + 1000)
      await nextTick()
      expect(natureRow(api, 'revenue')!.cellOverrides?.currentUnadjusted?.state).toBe('S2')

      api.restoreDerivedValue('nature', 'revenue', 'currentUnadjusted')
      // 🔴 当场（不 await）store 里应已是派生值。
      expect(
        Number(readRawValue(responses, itemId('nature', 'revenue', 'currentUnadjusted'))),
        '恢复取数当场写进 store 的不是派生值',
      ).toBe(derived1)
      expect(Number(readRawValue(responses, snapId('nature', 'revenue', 'currentUnadjusted')))).toBe(derived1)

      await nextTick()
      const r = natureRow(api, 'revenue')!
      expect(r.cellOverrides?.currentUnadjusted, '恢复后应回 S1，无 override').toBeUndefined()
      expect(r.currentUnadjusted).toBe(derived1)
    } finally {
      dispose()
    }
  })

  it('恢复一格不影响同行另一列、也不影响另一区块（跨 block 不串）', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const base: Record<string, number> = {}
      for (const { block, rowKey, field } of DERIVED_CELLS) {
        const k = `${block}/${rowKey}/${field}`
        base[k] = (rowOf(api, block, rowKey) as any)[field]
        setRaw(responses, itemId(block, rowKey, field), base[k] + 1000)
      }
      await nextTick()
      expect(countOverrideMarks(api)).toBe(DERIVED_CELLS.length)

      // 只恢复 nature/revenue/currentUnadjusted。
      api.restoreDerivedValue('nature', 'revenue', 'currentUnadjusted')
      await nextTick()
      expect(natureRow(api, 'revenue')!.cellOverrides?.currentUnadjusted).toBeUndefined()
      // 同行另一列仍覆盖。
      expect(natureRow(api, 'revenue')!.cellOverrides?.priorUnadjusted, '同行另一列被连带恢复').toBeDefined()
      // 另一区块两列都仍覆盖。
      const ar = agingRow(api, AGING_ROWKEY.within1)!
      expect(ar.cellOverrides?.priorUnadjusted, 'aging 区被连带恢复').toBeDefined()
      expect(ar.cellOverrides?.currentUnadjusted, 'aging 区被连带恢复').toBeDefined()
      expect(countOverrideMarks(api)).toBe(DERIVED_CELLS.length - 1)
    } finally {
      dispose()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 覆盖值必须参与下游公式（小计 / 合同负债合计 / 账龄合计 / 差异）
// **Validates: Requirements 4.5**
// ═══════════════════════════════════════════════════════════════════════════

describe('D7-P8 覆盖值参与下游公式', () => {
  it('覆盖 nature 明细 ⇒ 小计与合同负债合计都用覆盖值重算', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      // 初始小计 = 100+200+300+400
      expect(natureRow(api, 'nature-subtotal')!.currentUnadjusted).toBe(1000)
      setRaw(responses, itemId('nature', 'revenue', 'currentUnadjusted'), 1100) // 100 → 1100
      await nextTick()
      expect(natureRow(api, 'nature-subtotal')!.currentUnadjusted, '小计没用覆盖值重算').toBe(2000)
      // 合同负债合计 = 小计 − 扣减（扣减为 0）
      expect(natureRow(api, 'contract-liability-total')!.currentUnadjusted).toBe(2000)
    } finally {
      dispose()
    }
  })

  it('覆盖 aging 明细 ⇒ 账龄合计用覆盖值重算', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      // 初始合计 = 500+600+700+800
      expect(agingRow(api, 'aging-total')!.currentUnadjusted).toBe(2600)
      setRaw(responses, itemId('aging', AGING_ROWKEY.within1, 'currentUnadjusted'), 1500) // 500 → 1500
      await nextTick()
      expect(agingRow(api, 'aging-total')!.currentUnadjusted, '账龄合计没用覆盖值重算').toBe(3600)
    } finally {
      dispose()
    }
  })
})
