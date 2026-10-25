/**
 * D6-1 逐格覆盖状态机的判据（Property 8）—— 纯函数反证式 + **跑同步器**运行时判据。
 *
 * spec: d567-sync-coverage-via-row-table-engine · Requirements 4.4 / 4.5 / 4.6
 *
 * ═══ 为什么必须有"跑同步器"这一层（上游血泪教训）═══
 *
 * `resolveCellState(stored, snap, derived)` 纯函数判据「证明不了这三个量在真实运行里会不会
 * 走到那四态」——上游 **13 条纯函数判据全绿而生产坏掉**，根因是 S4 可达性取决于
 * `syncDerivedCellsIntoStore()` 怎么维护 `snap`。故本文件除纯函数反证外，**真正实例化
 * useD6Adjudication** 跑它的 blocks。
 *
 * ═══ D6 的派生格 ═══
 *
 * block1（合同资产原值）/ block2（坏账准备）的**动态行** × {priorUnadjusted, currentUnadjusted}，
 * 派生源分别是 `crossSheet.originalValueAggregation` / `impairmentAggregation`。
 * item_id `D6-1-adj-{blockKey}-{rowKey}-{field}`，快照键 `{itemId}-snap`。
 *
 * 🔴 block3（净值）**不参与**状态机：它是 `block1 − block2` 的纯公式区（`isEditable: false`），
 *    消费的已是 block1/block2 的显示值 ⇒ 覆盖自动透传（本文件有判据钉死这条透传）。
 *
 * 🔴 改造前的反模式是三家里最隐蔽的一版：
 *    `hasManualCurrent = map.has(`${prefix}-currentUnadjusted`)`
 *      ① `map.has` 对**空串** remark 也为 true ⇒ 一个空格就永久掐断上游取数；
 *      ② 只看 current 一个键却同时决定 prior 取不取派生值；
 *      ③ 与同步器**根本不兼容** —— 同步器把派生值落进 stored 后 `has` 即为 true
 *         ⇒ 上游取数被自己永久关掉。本文件三条都有精确反证。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, computed, effectScope, nextTick, type Ref } from 'vue'
import * as fc from 'fast-check'
import {
  resolveCellState,
  displayValueForCellState,
  resolvePerCellDerivedState,
} from '../shared/dynamicAdjudicationRows'
import { useD6Adjudication } from '../useD6Adjudication'
import type { ChecklistResponse } from '../useD6FormData'

type Responses = Ref<Map<string, ChecklistResponse>>
type Agg = Record<string, { prior: number; current: number }>

// ─── crossSheet mock（只需 3 个字段，已 grep 穷举 useD6Adjudication 的用点）──────

function makeCrossSheet(init?: { orig?: Agg; imp?: Agg }) {
  const orig = ref<Agg>(init?.orig ?? { catA: { prior: 10, current: 100 }, catB: { prior: 20, current: 200 } })
  const imp = ref<Agg>(init?.imp ?? { catA: { prior: 1, current: 8 }, catB: { prior: 2, current: 16 } })
  return {
    _orig: orig,
    _imp: imp,
    originalValueAggregation: computed(() => orig.value),
    impairmentAggregation: computed(() => imp.value),
    netValueValidation: computed(() => ({ isValid: true, diff: 0 })),
  }
}

function run(allResponses: Responses, crossSheet: ReturnType<typeof makeCrossSheet>) {
  const scope = effectScope()
  const debouncedSave = vi.fn()
  const saveImmediate = vi.fn().mockResolvedValue(undefined)
  const api = scope.run(() =>
    useD6Adjudication({
      allResponses,
      crossSheet: crossSheet as any,
      saveImmediate,
      debouncedSave,
      wpId: ref('wp-test'),
      projectId: ref('proj-test'),
    } as any),
  )!
  return { api, debouncedSave, saveImmediate, dispose: () => scope.stop() }
}

const itemId = (b: string, r: string, f: string) => `D6-1-adj-${b}-${r}-${f}`
const snapId = (b: string, r: string, f: string) => `${itemId(b, r, f)}-snap`

function setRaw(responses: Responses, id: string, raw: string | number): void {
  responses.value.set(id, { item_id: id, conclusion: null, remark: String(raw) })
  responses.value = new Map(responses.value)
}
function readRawValue(responses: Responses, id: string): string {
  return String(responses.value.get(id)?.remark ?? '')
}
type Api = ReturnType<typeof useD6Adjudication>
const BLOCK_INDEX: Record<string, number> = { block1: 0, block2: 1, block3: 2 }
function rowOf(api: Api, blockKey: string, rowKey: string) {
  return api.blocks.value[BLOCK_INDEX[blockKey]]?.rows.find((r) => r.rowKey === rowKey)
}
/** block1+block2 全部覆盖标记数（block3 不参与状态机，不计）。 */
function countOverrideMarks(api: Api): number {
  let marks = 0
  for (const bk of ['block1', 'block2']) {
    for (const r of api.blocks.value[BLOCK_INDEX[bk]]?.rows ?? []) {
      if (r.cellOverrides) marks += Object.keys(r.cellOverrides).length
    }
  }
  return marks
}

/** 四组派生格（两区块 × 两列），含改上游的 bump。 */
const DERIVED_CELLS = [
  {
    blockKey: 'block1', rowKey: 'catA', field: 'priorUnadjusted',
    bump: (cs: any) => { cs._orig.value = { ...cs._orig.value, catA: { ...cs._orig.value.catA, prior: 17 } } },
  },
  {
    blockKey: 'block1', rowKey: 'catA', field: 'currentUnadjusted',
    bump: (cs: any) => { cs._orig.value = { ...cs._orig.value, catA: { ...cs._orig.value.catA, current: 177 } } },
  },
  {
    blockKey: 'block2', rowKey: 'catA', field: 'priorUnadjusted',
    bump: (cs: any) => { cs._imp.value = { ...cs._imp.value, catA: { ...cs._imp.value.catA, prior: 7 } } },
  },
  {
    blockKey: 'block2', rowKey: 'catA', field: 'currentUnadjusted',
    bump: (cs: any) => { cs._imp.value = { ...cs._imp.value, catA: { ...cs._imp.value.catA, current: 77 } } },
  },
] as const

// ═══════════════════════════════════════════════════════════════════════════
// Property 8（纯函数反证式）
// **Validates: Requirements 4.4**
// ═══════════════════════════════════════════════════════════════════════════

describe('D6-P8 反证式（纯函数）：只改 derived 不改 stored/snap ⇒ 零覆盖标记', () => {
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

  it('共享降级语义（三家同一实现，钉死防漂移）', () => {
    expect(resolvePerCellDerivedState(0, null, 100).state).toBe('S1')
    expect(resolvePerCellDerivedState(0, null, 100).display).toBe(100)
    expect(resolvePerCellDerivedState(888, null, 100).state).toBe('S2')
    expect(resolvePerCellDerivedState(888, null, 100).display).toBe(888)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 🔴 跑同步器判据
// **Validates: Requirements 4.4 / 4.5 / 4.6**
// ═══════════════════════════════════════════════════════════════════════════

describe('D6-P8 跑同步器：真实 composable 里两区块四态可达', () => {
  it('挂载即 S1 纯派生：两区块两列都显示派生值、零覆盖标记', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      expect(rowOf(api, 'block1', 'catA')!.priorUnadjusted).toBe(10)
      expect(rowOf(api, 'block1', 'catA')!.currentUnadjusted).toBe(100)
      expect(rowOf(api, 'block2', 'catA')!.priorUnadjusted).toBe(1)
      expect(rowOf(api, 'block2', 'catA')!.currentUnadjusted).toBe(8)
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
      crossSheet._orig.value = { ...crossSheet._orig.value, catA: { prior: 11, current: 111 } }
      crossSheet._imp.value = { ...crossSheet._imp.value, catA: { prior: 3, current: 9 } }
      await nextTick()
      expect(rowOf(api, 'block1', 'catA')!.priorUnadjusted).toBe(11)
      expect(rowOf(api, 'block1', 'catA')!.currentUnadjusted).toBe(111)
      expect(rowOf(api, 'block2', 'catA')!.priorUnadjusted).toBe(3)
      expect(rowOf(api, 'block2', 'catA')!.currentUnadjusted).toBe(9)
      expect(countOverrideMarks(api), '只改上游派生不该产生任何覆盖标记').toBe(0)
    } finally {
      dispose()
    }
  })

  it.each(DERIVED_CELLS)(
    'S2：覆盖 $blockKey/$rowKey/$field ⇒ 标已覆盖 + 显示覆盖值',
    async ({ blockKey, rowKey, field }) => {
      const crossSheet = makeCrossSheet()
      const responses = ref(new Map<string, ChecklistResponse>()) as Responses
      const { api, dispose } = run(responses, crossSheet)
      try {
        await nextTick()
        const derived1 = (rowOf(api, blockKey, rowKey) as any)[field] as number
        expect(derived1).toBeGreaterThan(0)
        setRaw(responses, itemId(blockKey, rowKey, field), derived1 + 1000)
        await nextTick()
        const r = rowOf(api, blockKey, rowKey)!
        expect(r.cellOverrides?.[field]?.state, '应为 S2（覆盖、上游未变）').toBe('S2')
        expect((r as any)[field], '显示覆盖值不是派生值').toBe(derived1 + 1000)
      } finally {
        dispose()
      }
    },
  )

  it.each(DERIVED_CELLS)(
    'S4：$blockKey/$rowKey/$field 覆盖后上游再变 ⇒ 三值同时可读且互不相等',
    async ({ blockKey, rowKey, field, bump }) => {
      const crossSheet = makeCrossSheet()
      const responses = ref(new Map<string, ChecklistResponse>()) as Responses
      const { api, dispose } = run(responses, crossSheet)
      try {
        await nextTick()
        const derived1 = (rowOf(api, blockKey, rowKey) as any)[field] as number
        const overrideValue = derived1 + 1000
        setRaw(responses, itemId(blockKey, rowKey, field), overrideValue)
        await nextTick()
        expect(rowOf(api, blockKey, rowKey)!.cellOverrides?.[field]?.state).toBe('S2')

        bump(crossSheet as any)
        await nextTick()
        const cell = rowOf(api, blockKey, rowKey)!.cellOverrides?.[field]
        expect(cell, '覆盖格丢了 cellOverrides —— 覆盖被吞掉').toBeDefined()
        expect(cell!.state, `上游已变后应为 S4，实得 ${cell!.state}`).toBe('S4')
        expect(cell!.stored).toBe(overrideValue)
        expect(cell!.snap, '原派生值没冻结').toBe(derived1)
        expect(new Set([cell!.stored, cell!.snap, cell!.derived]).size).toBe(3)
        expect((rowOf(api, blockKey, rowKey) as any)[field]).toBe(overrideValue)
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
      const derived1 = rowOf(api, 'block1', 'catA')!.currentUnadjusted
      setRaw(responses, itemId('block1', 'catA', 'currentUnadjusted'), derived1 + 1000)
      await nextTick()
      for (const v of [150, 160, 170, 100]) {
        crossSheet._orig.value = {
          ...crossSheet._orig.value,
          catA: { ...crossSheet._orig.value.catA, current: v },
        }
        await nextTick()
        api._syncDerivedCellsIntoStore()
        await nextTick()
        expect(
          rowOf(api, 'block1', 'catA')!.cellOverrides?.currentUnadjusted,
          `上游变到 ${v} 后覆盖标记被擦除`,
        ).toBeDefined()
        expect(rowOf(api, 'block1', 'catA')!.currentUnadjusted).toBe(derived1 + 1000)
      }
      expect(Number(readRawValue(responses, snapId('block1', 'catA', 'currentUnadjusted')))).toBe(derived1)
    } finally {
      dispose()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 🔴 改造前 `map.has()` 反模式的三条精确反证
// **Validates: Requirements 4.5**
// ═══════════════════════════════════════════════════════════════════════════

describe('D6-P8 改造前 map.has() 反模式的反证', () => {
  // ═══ 鉴别力说明（实测变异结论，勿删）═══
  //
  // 把读侧退回 `map.has()` 反模式（变异 F）后，本 describe 里**只有第 ② 条会红**，
  // 加上「S2/S4 覆盖检出」「自我擦除」「恢复取数」共 8 条红。
  // ① 与 ③ 在变异下**仍然绿** —— 因为同步器（未被变异）会先把空串/旧值规范成派生值，
  // 把读侧的 `map.has` 问题掩盖掉。故 ① ③ 的定性是**结果级回归守卫**（锁住"用户看到的值
  // 必须是派生值"这一外部行为），**不是**该反模式的鉴别判据；真正的鉴别力在 ② 与覆盖检出组。
  // 🔴 不把它们标成「反证」，避免让非承重判据看起来在承重。

  it('①（结果级守卫）空串 remark 的格最终显示上游派生值', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    // 一个**空格**（用户点进去又退出来，或导入留下的空串）。
    setRaw(responses, itemId('block1', 'catA', 'currentUnadjusted'), '')
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      expect(
        rowOf(api, 'block1', 'catA')!.currentUnadjusted,
        '空串格没显示上游派生值',
      ).toBe(100)
      expect(rowOf(api, 'block1', 'catA')!.cellOverrides).toBeUndefined()
    } finally {
      dispose()
    }
  })

  it('①b（鉴别判据）空串必须被当成「无值」而非 0 —— 否则空 snap 会把格误判成已覆盖', () => {
    // 这条才有鉴别力：空串若按 `parseNum` 归成 0（改造前 `getNumFromResponse` 的口径），
    // 则 `snap=0, stored=888` ⇒ 判 S2 尚可，但 `snap=0, stored=0, derived=100` 会判成
    // **S3**（snap≠derived）而非降级 S1，且「从未写过快照」与「快照是 0」不可区分 ⇒
    // 同步器无法判断该不该冻结。`readCellOrNull` 把空串读成 null 才让降级分支可达。
    expect(resolvePerCellDerivedState(null, null, 100).state).toBe('S1')
    expect(resolvePerCellDerivedState(null, null, 100).display).toBe(100)
    // 对照：snap 真的是 0（同步器写过 0）⇒ 上游变了就是 S3，会跟随。
    expect(resolvePerCellDerivedState(0, 0, 100).state).toBe('S3')
    expect(resolvePerCellDerivedState(0, 0, 100).display).toBe(100)
    // 对照：snap 是 0 且 stored 被改 ⇒ S4（覆盖 + 上游已变），显示覆盖值。
    expect(resolvePerCellDerivedState(55, 0, 100).state).toBe('S4')
    expect(resolvePerCellDerivedState(55, 0, 100).display).toBe(55)
  })

  it('🔴② current 列的键存在不再决定 prior 列取不取派生值', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    // 只覆盖期末，期初应继续跟随派生。
    setRaw(responses, itemId('block1', 'catA', 'currentUnadjusted'), 9999)
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const r = rowOf(api, 'block1', 'catA')!
      expect(r.currentUnadjusted, '期末覆盖值应生效').toBe(9999)
      expect(r.priorUnadjusted, '期末有录入就把期初也切走 ⇒ 反模式未修掉').toBe(10)
      // 两列状态独立。
      expect(r.cellOverrides?.currentUnadjusted?.state).toBe('S2')
      expect(r.cellOverrides?.priorUnadjusted).toBeUndefined()
    } finally {
      dispose()
    }
  })

  it('③（结果级守卫）同步器落库后上游仍能继续驱动', async () => {
    // 改造前读侧与同步器**语义冲突**：同步器把派生值写进 stored 后 `map.has` 恒为 true。
    // 实测在变异 F 下本条仍绿（同步器会把 stored 一路推到新派生值，读侧取 stored 也得对值），
    // 故定性为结果级守卫；冲突的可观测后果落在「覆盖检出」组（那里变异必红）。
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      // 同步器已落库（stored 与 snap 都有值）。
      expect(readRawValue(responses, itemId('block1', 'catA', 'currentUnadjusted'))).toBe('100')
      expect(readRawValue(responses, snapId('block1', 'catA', 'currentUnadjusted'))).toBe('100')
      // 上游再变 ⇒ 仍须跟随（S3）。
      crossSheet._orig.value = { ...crossSheet._orig.value, catA: { prior: 10, current: 654 } }
      await nextTick()
      expect(
        rowOf(api, 'block1', 'catA')!.currentUnadjusted,
        '同步器落库后上游不再驱动该格',
      ).toBe(654)
      expect(rowOf(api, 'block1', 'catA')!.cellOverrides).toBeUndefined()
    } finally {
      dispose()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// block3（净值）：纯公式区，覆盖自动透传，无需第二套状态机
// **Validates: Requirements 4.5**
// ═══════════════════════════════════════════════════════════════════════════

describe('D6-P8 block3 净值区透传覆盖值', () => {
  it('覆盖 block1 明细 ⇒ block3 净值行/小计用覆盖值重算，且 block3 自身无 cellOverrides', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      // 初始净值 catA = 100 − 8
      expect(rowOf(api, 'block3', 'catA')!.currentUnadjusted).toBe(92)
      setRaw(responses, itemId('block1', 'catA', 'currentUnadjusted'), 1100)
      await nextTick()
      expect(
        rowOf(api, 'block3', 'catA')!.currentUnadjusted,
        'block3 没透传 block1 的覆盖值',
      ).toBe(1100 - 8)
      // block3 是纯公式区，不该自带覆盖标记。
      expect(rowOf(api, 'block3', 'catA')!.cellOverrides).toBeUndefined()
      // 小计同步透传：block1 小计(1100+200) − block2 小计(8+16)
      expect(api.blocks.value[2]!.subtotalRow.currentUnadjusted).toBe(1300 - 24)
    } finally {
      dispose()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 恢复取数 + 删行清理快照
// **Validates: Requirements 4.6**
// ═══════════════════════════════════════════════════════════════════════════

describe('D6-P8 恢复取数：作用域一格', () => {
  it('恢复取数把被点格退回 S1，且当场写进 store', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      const derived1 = rowOf(api, 'block1', 'catA')!.currentUnadjusted
      setRaw(responses, itemId('block1', 'catA', 'currentUnadjusted'), derived1 + 1000)
      await nextTick()
      expect(rowOf(api, 'block1', 'catA')!.cellOverrides?.currentUnadjusted?.state).toBe('S2')

      api.restoreDerivedValue('block1', 'catA', 'currentUnadjusted')
      expect(
        Number(readRawValue(responses, itemId('block1', 'catA', 'currentUnadjusted'))),
        '恢复取数当场写进 store 的不是派生值',
      ).toBe(derived1)
      expect(Number(readRawValue(responses, snapId('block1', 'catA', 'currentUnadjusted')))).toBe(derived1)

      await nextTick()
      const r = rowOf(api, 'block1', 'catA')!
      expect(r.cellOverrides?.currentUnadjusted, '恢复后应回 S1，无 override').toBeUndefined()
      expect(r.currentUnadjusted).toBe(derived1)
    } finally {
      dispose()
    }
  })

  it('恢复一格不影响同行另一列、也不影响另一区块与另一行', async () => {
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      for (const { blockKey, rowKey, field } of DERIVED_CELLS) {
        const v = (rowOf(api, blockKey, rowKey) as any)[field] as number
        setRaw(responses, itemId(blockKey, rowKey, field), v + 1000)
      }
      // 另一行也覆盖一格，验证不被连带。
      setRaw(responses, itemId('block1', 'catB', 'currentUnadjusted'), 12345)
      await nextTick()
      expect(countOverrideMarks(api)).toBe(DERIVED_CELLS.length + 1)

      api.restoreDerivedValue('block1', 'catA', 'currentUnadjusted')
      await nextTick()
      expect(rowOf(api, 'block1', 'catA')!.cellOverrides?.currentUnadjusted).toBeUndefined()
      expect(rowOf(api, 'block1', 'catA')!.cellOverrides?.priorUnadjusted, '同行另一列被连带').toBeDefined()
      expect(rowOf(api, 'block2', 'catA')!.cellOverrides?.currentUnadjusted, '另一区块被连带').toBeDefined()
      expect(rowOf(api, 'block1', 'catB')!.cellOverrides?.currentUnadjusted, '另一行被连带').toBeDefined()
      expect(countOverrideMarks(api)).toBe(DERIVED_CELLS.length)
    } finally {
      dispose()
    }
  })

  it('🔴 删行必须连快照键一起删（否则同名类别重现时被误判 S4 显示 0）', async () => {
    // 场景：删掉 catA 行 → 只删 stored 不删 snap ⇒ 残留 snap；
    //       日后同名类别重现（聚合里又有 catA）⇒ stored=null, snap=旧值, derived=新值
    //       ⇒ `_eq(null, 旧值)=false` 判已覆盖 + 上游已变 ⇒ S4 ⇒ 显示 stored??0 = **0**。
    const crossSheet = makeCrossSheet()
    const responses = ref(new Map<string, ChecklistResponse>()) as Responses
    const { api, dispose } = run(responses, crossSheet)
    try {
      await nextTick()
      // 同步器已写入 catA 的 stored + snap。
      expect(readRawValue(responses, snapId('block1', 'catA', 'currentUnadjusted'))).toBe('100')
      expect(readRawValue(responses, snapId('block1', 'catA', 'priorUnadjusted'))).toBe('10')

      api.removeDynamicRow('block1', 'catA')
      await nextTick()

      expect(
        responses.value.has(snapId('block1', 'catA', 'currentUnadjusted')),
        '删行没删 currentUnadjusted 的快照键 ⇒ 孤儿快照',
      ).toBe(false)
      expect(
        responses.value.has(snapId('block1', 'catA', 'priorUnadjusted')),
        '删行没删 priorUnadjusted 的快照键 ⇒ 孤儿快照',
      ).toBe(false)
      expect(responses.value.has(itemId('block1', 'catA', 'currentUnadjusted'))).toBe(false)
    } finally {
      dispose()
    }
  })
})
