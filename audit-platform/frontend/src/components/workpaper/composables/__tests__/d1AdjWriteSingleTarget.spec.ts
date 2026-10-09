/**
 * D1-1 审定表写侧**单写** —— 真调 `useD1Adjudication`，不是只测纯函数。
 *
 * spec: d1-sync-row-table-engine-and-d1-coverage · Task 32（需求 6.1 / 6.2）
 *
 * ═══ 为什么必须跑 composable ═══
 *
 * 「单写」的定义是**写侧只写新形态、不再写 per-cell**。这个性质只存在于 composable 的
 * `updateCell` / `applyAdjustmentEntry` 里 —— model 层的 `serializeD1AdjRows` 是纯函数，
 * 它产出什么串跟「有没有人顺手又写了一遍 per-cell」无关。
 *
 * 🔴 本 spec 有直接教训：tasks.md 明文警告「D4 spec 有 13 条纯函数判据全绿而生产坏掉
 * （同步器把显示值当派生值写回 snap ⇒ 覆盖标记自我擦除）」。只验纯函数就是重犯那一类。
 *
 * ⚠️ 非组件环境调 composable 会有 `onBeforeUnmount` 的 Vue warn（既有
 * `useD1SeedPriority.spec.ts` 同款），不影响断言。
 */
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import {
  D1_ADJ_ROWS_KEY,
  d1AdjAnchor,
  d1AdjRowKey,
  isD1AdjAnchor,
  readD1AdjRowAmounts,
} from '../d1AdjudicationModel'
import { useD1Adjudication } from '../useD1Adjudication'

type Resp = { item_id: string; conclusion: string | null; remark: string | null }

function setup(seed: Record<string, string> = {}) {
  const map = new Map<string, Resp>()
  for (const [item_id, remark] of Object.entries(seed)) {
    map.set(item_id, { item_id, conclusion: null, remark })
  }
  const allResponses = ref(map)
  const savedBatches: Resp[][] = []
  const api = useD1Adjudication({
    allResponses,
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    saveImmediate: vi.fn(async (items: Resp[]) => {
      savedBatches.push(items)
    }),
    loadSubWorkpaperData: vi.fn(async () => ({})),
    isReadonly: ref(false),
    openReviewDialog: vi.fn(),
    tbSeedAmount: ref(0),
  } as unknown as Parameters<typeof useD1Adjudication>[0])
  return { api, allResponses, savedBatches }
}

/** 写入后新增/更新的 `D1-adj-*` 键（排除 seed 里本来就有的）。 */
function touchedAdjKeys(
  allResponses: { value: Map<string, Resp> },
  seedKeys: readonly string[],
): string[] {
  return [...allResponses.value.keys()]
    .filter((k) => isD1AdjAnchor(k) && !seedKeys.includes(k))
    .sort()
}

describe('updateCell —— 单写行数组', () => {
  it('🔴 只写 D1-adj-rows，不写任何 per-cell 锚点', () => {
    const { api, allResponses } = setup()
    api.updateCell(d1AdjRowKey('gross', 'bank'), 'prior-unadj', 123.45)

    const touched = touchedAdjKeys(allResponses, [])
    expect(touched).toContain(D1_ADJ_ROWS_KEY)
    // 除行数组键外，不得出现任何 per-cell 键
    expect(touched.filter((k) => k !== D1_ADJ_ROWS_KEY)).toEqual([])
    // 特别点名：改造前写的就是这个键
    expect(allResponses.value.has(d1AdjAnchor('gross', 'bank', 'prior-unadj'))).toBe(false)
  })

  it('写入值能被读侧双读读回', () => {
    const { api, allResponses } = setup()
    api.updateCell(d1AdjRowKey('gross', 'bank'), 'current-unadj', 2000.5)
    const a = readD1AdjRowAmounts(allResponses.value as never, 'gross', 'bank')
    expect(a.currentUnadjusted).toBe(2000.5)
  })

  it('🔴 既有 per-cell 旧值在首次编辑后被固化进行对象（迁移不归零）', () => {
    const oldKey = d1AdjAnchor('gross', 'bank', 'prior-unadj')
    const { api, allResponses } = setup({ [oldKey]: '500' })
    api.updateCell(d1AdjRowKey('gross', 'bank'), 'current-unadj', 600)

    const rowsRaw = allResponses.value.get(D1_ADJ_ROWS_KEY)!.remark!
    const rows = JSON.parse(rowsRaw) as Array<Record<string, unknown>>
    const row = rows.find((r) => r.rowId === d1AdjRowKey('gross', 'bank'))!
    expect(row['prior-unadj']).toBe(500) // 旧 per-cell 值已随行落库
    expect(row['current-unadj']).toBe(600)
    // 旧键本身**原样留着**（只读不写，物理删除归后续 spec）
    expect(allResponses.value.get(oldKey)!.remark).toBe('500')
  })

  it('连续两次编辑不同格：两者都在（不是后写覆盖前写）', () => {
    const { api, allResponses } = setup()
    const rowId = d1AdjRowKey('bd', 'commercial')
    api.updateCell(rowId, 'prior-unadj', 10)
    api.updateCell(rowId, 'current-unadj', 20)
    const a = readD1AdjRowAmounts(allResponses.value as never, 'bd', 'commercial')
    expect(a.priorUnadjusted).toBe(10)
    expect(a.currentUnadjusted).toBe(20)
  })

  it('isReadonly 时不写任何东西', () => {
    const map = new Map<string, Resp>()
    const allResponses = ref(map)
    const api = useD1Adjudication({
      allResponses,
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      saveImmediate: vi.fn(async () => {}),
      loadSubWorkpaperData: vi.fn(async () => ({})),
      isReadonly: ref(true),
      openReviewDialog: vi.fn(),
      tbSeedAmount: ref(0),
    } as unknown as Parameters<typeof useD1Adjudication>[0])
    api.updateCell(d1AdjRowKey('gross', 'bank'), 'prior-unadj', 1)
    expect([...allResponses.value.keys()].filter(isD1AdjAnchor)).toEqual([])
  })
})

describe('debounce 保存会把行数组键一起提交', () => {
  it('🔴 flushAdjItems 按 isD1AdjAnchor 前缀收集 ⇒ D1-adj-rows 在提交批次里', async () => {
    vi.useFakeTimers()
    try {
      const { api, allResponses, savedBatches } = setup()
      api.updateCell(d1AdjRowKey('gross', 'bank'), 'prior-unadj', 42)
      expect(savedBatches.length).toBe(0) // 2s debounce 未到
      vi.advanceTimersByTime(2100)
      expect(savedBatches.length).toBe(1)
      const ids = savedBatches[0].map((i) => i.item_id)
      expect(ids).toContain(D1_ADJ_ROWS_KEY)
      // 提交的内容就是当前 store 里的行数组
      expect(savedBatches[0].find((i) => i.item_id === D1_ADJ_ROWS_KEY)!.remark).toBe(
        allResponses.value.get(D1_ADJ_ROWS_KEY)!.remark,
      )
    } finally {
      vi.useRealTimers()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// Task 33：composable 层的四态接线（isEditable 放开 + watch 自动跑同步器）
// ═══════════════════════════════════════════════════════════════════════════

describe('Task 33 —— 四态在 composable 层的接线', () => {
  /** 造一份 D1-2 明细（cross-sheet 上游），让审定表原值区有派生值。 */
  function d1CatRows() {
    return JSON.stringify([
      {
        rowId: 'fixed-bank',
        category: '银行承兑汇票',
        isFixed: true,
        priorUnadjusted: 1000,
        currentIncrease: 200,
        currentDecrease: 100,
      },
    ])
  }

  it('🔴 cross-sheet 命中的行**不再**强制只读（isEditable 不看 isFromCrossSheet）', () => {
    const { api } = setup({ 'D1-cat-rows': d1CatRows() })
    const gross = api.adjudicationSections.value.find((s) => s.sectionKey === 'gross')!
    const bank = gross.rows.find((r) => r.label.includes('银行承兑'))!
    expect(bank.isFromCrossSheet, '本用例前提是该行确实来自 cross-sheet').toBe(true)
    // 修前：isEditable = editable && !isFromCrossSheet ⇒ false ⇒ 手工值改不了（静默丢数据）
    expect(bank.isEditable).toBe(true)
  })

  it('净值区仍恒只读（它是公式：原值 − 坏账）', () => {
    const { api } = setup({ 'D1-cat-rows': d1CatRows() })
    const net = api.adjudicationSections.value.find((s) => s.sectionKey === 'net-value')!
    expect(net.rows.every((r) => r.isEditable === false)).toBe(true)
  })

  it('🔴 watch 在 setup 时就跑过同步器 ⇒ derivedSnapshot 已落，四态不再停在降级态', () => {
    const { allResponses } = setup({ 'D1-cat-rows': d1CatRows() })
    const raw = allResponses.value.get(D1_ADJ_ROWS_KEY)?.remark
    expect(raw, '同步器没跑 ⇒ snap 恒 null ⇒ 认不出 S3/S4').toBeTruthy()
    const rows = JSON.parse(raw!) as Array<Record<string, unknown>>
    const row = rows.find((r) => r.rowId === d1AdjRowKey('gross', 'bank'))!
    expect(row.derivedSnapshot).toBeTruthy()
  })

  it('🔴 手工覆盖后再跑同步器：覆盖值不被冲掉，且行上带 S2 标记', () => {
    const { api, allResponses } = setup({ 'D1-cat-rows': d1CatRows() })
    const rowId = d1AdjRowKey('gross', 'bank')
    api.updateCell(rowId, 'prior-unadj', 5555)
    // 再跑一次同步器（模拟上游 watch 又触发）
    api.syncDerivedIntoStore()

    const gross = api.adjudicationSections.value.find((s) => s.sectionKey === 'gross')!
    const bank = gross.rows.find((r) => r.rowKey === rowId)!
    expect(bank.priorUnadjusted, '覆盖值被派生值冲掉了').toBe(5555)
    expect(['S2', 'S4']).toContain(bank.cellStates['prior-unadj'])
    // store 里也确实是覆盖值
    const rows = JSON.parse(allResponses.value.get(D1_ADJ_ROWS_KEY)!.remark!) as Array<
      Record<string, unknown>
    >
    expect(rows.find((r) => r.rowId === rowId)!['prior-unadj']).toBe(5555)
  })

  it('恢复取数把该格退回跟随上游（S1）', () => {
    const { api } = setup({ 'D1-cat-rows': d1CatRows() })
    const rowId = d1AdjRowKey('gross', 'bank')
    api.updateCell(rowId, 'prior-unadj', 5555)
    api.restoreDerivedValue(rowId, 'prior-unadj')

    const gross = api.adjudicationSections.value.find((s) => s.sectionKey === 'gross')!
    const bank = gross.rows.find((r) => r.rowKey === rowId)!
    expect(bank.cellStates['prior-unadj']).toBe('S1')
    expect(bank.priorUnadjusted).toBe(1000) // 回到 D1-2 的上游值
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 非金额字段（reason）必须仍落 per-cell —— Task 32 切写侧时漏掉的分支
// ═══════════════════════════════════════════════════════════════════════════

describe('updateCell 的非金额字段分支', () => {
  it('🔴 reason（文本）仍写 per-cell 锚点，不被行数组路径静默丢弃', () => {
    // 根因：`serializeRows` 只序列化 spec.valueFields（数字）与结构键，文本字段会被丢弃。
    // 模板列「原因分析」调的正是 updateCell(row.rowKey, 'reason', v)，
    // Task 32 只切金额路径时它会静默丢失。
    const { api, allResponses } = setup()
    const rowId = d1AdjRowKey('gross', 'bank')
    api.updateCell(rowId, 'reason', '本期新增银行承兑汇票贴现' as unknown as number)

    const anchor = d1AdjAnchor('gross', 'bank', 'reason' as never)
    expect(allResponses.value.get(anchor)?.remark).toBe('本期新增银行承兑汇票贴现')
    // 不应该被塞进行数组（它不是 valueField）
    const rowsRaw = allResponses.value.get(D1_ADJ_ROWS_KEY)?.remark
    if (rowsRaw) {
      expect(rowsRaw).not.toContain('本期新增银行承兑汇票贴现')
    }
  })

  it('reason 写入后读侧 readD1AnchorReason 能读回（两侧口径一致）', async () => {
    const { api, allResponses } = setup()
    const rowId = d1AdjRowKey('gross', 'commercial')
    api.updateCell(rowId, 'reason', '商业承兑到期兑付' as unknown as number)
    const { readD1AnchorReason } = await import('../d1AdjudicationModel')
    expect(readD1AnchorReason(allResponses.value as never, 'gross', 'commercial')).toBe(
      '商业承兑到期兑付',
    )
  })

  it('金额字段仍走行数组（不被本分支误伤）', () => {
    const { api, allResponses } = setup()
    const rowId = d1AdjRowKey('gross', 'bank')
    api.updateCell(rowId, 'prior-aje', 66)
    expect(allResponses.value.has(D1_ADJ_ROWS_KEY)).toBe(true)
    expect(allResponses.value.has(d1AdjAnchor('gross', 'bank', 'prior-aje'))).toBe(false)
  })
})
