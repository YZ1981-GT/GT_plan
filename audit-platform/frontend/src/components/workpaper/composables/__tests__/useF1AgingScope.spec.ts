/**
 * F1 账龄口径单一真源 + 跨表一致性回归
 *
 * 修复前缺陷：F1-2 明细表支持表级账龄枚举覆盖，但 F1-1 审定表 / crossSheet / 附注
 * 各自读项目级配置 → 切 5 年段后审定表按 3 年段建行，`over3` 读不到
 * `y3to4/y4to5/over5` → 3 年以上金额在审定表与附注消失、超 1 年筛选漏行。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick, computed } from 'vue'
import { PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import { resolveF1Segments, useF1AgingScope } from '../useF1AgingScope'
import { useF1CrossSheet } from '../useF1CrossSheet'
import { useF1Adjudication } from '../useF1Adjudication'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockRejectedValue(new Error('no aging api')), post: vi.fn() },
}))

vi.mock('@/composables/useAgingConfig', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/composables/useAgingConfig')>()
  return {
    ...actual,
    // 项目级配置固定 3 年段（模拟“项目没改、只在表级切 5 年段”的真实场景）
    useAgingConfig: () => ({
      segments: ref(actual.PRESET_SEGMENTS.THREE_YEAR),
      bands: ref([]),
      preset: ref('THREE_YEAR' as const),
      loading: ref(false),
      refresh: vi.fn(),
    }),
  }
})

function detailRow(over: Record<string, number>) {
  return {
    rowId: 'r1',
    customerName: '甲供应商',
    nature: '货款',
    relationType: '非关联方',
    priorUnadjusted: 0,
    priorAudited: 500,
    debit: 0,
    credit: 0,
    endUnadjusted: 1000,
    endAudited: 1000,
    agingPrior: { within1: 500, ...over },
    agingCurrent: { within1: 0, ...over },
    agingAudited: { within1: 0, ...over },
  }
}

describe('resolveF1Segments（纯函数）', () => {
  it('表级 3年段/5年段优先于项目配置', () => {
    expect(resolveF1Segments('FIVE_YEAR', [], 'THREE_YEAR', PRESET_SEGMENTS.THREE_YEAR))
      .toHaveLength(6)
    expect(resolveF1Segments('THREE_YEAR', [], 'CUSTOM', PRESET_SEGMENTS.FIVE_YEAR))
      .toHaveLength(4)
  })

  it('表级 CUSTOM 生效需 ≥2 段，不足时回退项目/3年段', () => {
    const custom: AgingSegment[] = [
      { key: 'custom-0', label: '短期', dayFrom: 0, dayTo: null },
      { key: 'custom-1', label: '长期', dayFrom: 0, dayTo: null },
    ]
    expect(resolveF1Segments('CUSTOM', custom, 'THREE_YEAR', PRESET_SEGMENTS.THREE_YEAR))
      .toEqual(custom)
    expect(resolveF1Segments('CUSTOM', [], 'THREE_YEAR', PRESET_SEGMENTS.THREE_YEAR))
      .toHaveLength(4)
  })

  it('无表级覆盖时用项目配置，项目为空兜底 3 年段', () => {
    expect(resolveF1Segments('', [], 'FIVE_YEAR', PRESET_SEGMENTS.FIVE_YEAR)).toHaveLength(6)
    expect(resolveF1Segments('', [], undefined, [])).toHaveLength(4)
  })
})

describe('useF1AgingScope（表级覆盖单一真源）', () => {
  beforeEach(() => {
    vi.spyOn(window, 'addEventListener').mockImplementation(() => undefined)
    vi.spyOn(window, 'removeEventListener').mockImplementation(() => undefined)
  })

  it('读取持久化的表级覆盖；setPreset 落库并即时反映', async () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F1-det-aging-preset', { item_id: 'F1-det-aging-preset', conclusion: null, remark: 'FIVE_YEAR' })
    const save = vi.fn()
    const scope = useF1AgingScope({
      allResponses: ref(map),
      projectId: ref('p1'),
      debouncedSave: save,
      isReadonly: ref(false),
    })
    await nextTick()
    expect(scope.preset.value).toBe('FIVE_YEAR')
    expect(scope.segments.value.map(s => s.key)).toContain('y4to5')
    expect(scope.hasSheetOverride.value).toBe(true)

    expect(scope.setPreset('THREE_YEAR')).toBe(true)
    await nextTick()
    expect(scope.segments.value).toHaveLength(4)
    expect(save).toHaveBeenCalledWith('F1-det-aging-preset', { remark: 'THREE_YEAR' })
  })
})

describe('账龄口径跨表一致（crossSheet ↔ F1-1 审定表）', () => {
  beforeEach(() => {
    vi.spyOn(window, 'addEventListener').mockImplementation(() => undefined)
    vi.spyOn(window, 'removeEventListener').mockImplementation(() => undefined)
  })

  function build(segments: AgingSegment[], detail: any) {
    const map = new Map<string, ChecklistResponse>()
    map.set('F1-det-rows', {
      item_id: 'F1-det-rows', conclusion: null, remark: JSON.stringify([detail]),
    })
    const allResponses = ref(map)
    const segs = computed(() => segments)
    const crossSheet = useF1CrossSheet({ allResponses, segments: segs as any })
    const adj = useF1Adjudication({
      allResponses,
      wpId: ref('wp-1'),
      projectId: ref('p1'),
      saveImmediate: vi.fn(),
      debouncedSave: vi.fn(),
      crossSheet,
      isReadonly: ref(false),
      agingSegments: segs as any,
    })
    return { crossSheet, adj, allResponses }
  }

  it('5 年段：审定表按 6 段建行，且 3 年以上各段金额不丢（修复前 over3 读 0）', async () => {
    const { crossSheet, adj } = build(
      PRESET_SEGMENTS.FIVE_YEAR,
      detailRow({ y1to2: 0, y2to3: 0, y3to4: 300, y4to5: 200, over5: 500 }),
    )
    await nextTick()
    const agingSection = adj.sections.value[1]
    expect(agingSection.rows).toHaveLength(6)
    const byKey = Object.fromEntries(agingSection.rows.map(r => [r.rowKey, r.currentUnadjusted]))
    expect(byKey.y3to4).toBe(300)
    expect(byKey.y4to5).toBe(200)
    expect(byKey.over5).toBe(500)
    // 账龄合计 = 明细期末审定合计 → 与性质分类合计一致，无假差异告警
    expect(agingSection.subtotalRow.currentUnadjusted).toBe(1000)
    expect(adj.crossValidationWarning.value).toBeNull()
    // 超 1 年筛选覆盖 5 年段各档（F1-5 长期挂款 / 附注超 1 年重要项）
    expect(crossSheet.longTermRows.value).toHaveLength(1)
  })

  it('3 年段：段键与审定行一致，缺段返 0 而非 undefined', async () => {
    const { adj } = build(
      PRESET_SEGMENTS.THREE_YEAR,
      detailRow({ y1to2: 0, y2to3: 0, over3: 1000 }),
    )
    await nextTick()
    const rows = adj.sections.value[1].rows
    expect(rows.map(r => r.rowKey)).toEqual(['within1', 'y1to2', 'y2to3', 'over3'])
    expect(rows.find(r => r.rowKey === 'over3')!.currentUnadjusted).toBe(1000)
    expect(rows.find(r => r.rowKey === 'y1to2')!.currentUnadjusted).toBe(0)
  })

  it('自定义段：首段外均计入「超 1 年」筛选', async () => {
    const custom: AgingSegment[] = [
      { key: 'custom-0', label: '1年以内', dayFrom: 0, dayTo: null },
      { key: 'custom-1', label: '1年以上', dayFrom: 0, dayTo: null },
    ]
    const { crossSheet, adj } = build(custom, {
      ...detailRow({}),
      agingPrior: { 'custom-0': 500, 'custom-1': 0 },
      agingCurrent: { 'custom-0': 0, 'custom-1': 1000 },
      agingAudited: { 'custom-0': 0, 'custom-1': 1000 },
    })
    await nextTick()
    expect(adj.sections.value[1].rows.map(r => r.rowKey)).toEqual(['custom-0', 'custom-1'])
    expect(crossSheet.longTermRows.value).toHaveLength(1)
  })
})

describe('F1-3 → F1-1 调整净额 & 审定表 persist-first', () => {
  beforeEach(() => {
    vi.spyOn(window, 'addEventListener').mockImplementation(() => undefined)
    vi.spyOn(window, 'removeEventListener').mockImplementation(() => undefined)
  })

  it('调整汇总取净额（借方调增 − 贷方调减），贷方不再被丢弃', async () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F1-aje-rows', {
      item_id: 'F1-aje-rows',
      conclusion: null,
      remark: JSON.stringify([
        { rowId: 'a1', category: '账项调整', debitAmount: 1000, creditAmount: 0 },
        { rowId: 'a2', category: '账项调整', debitAmount: 0, creditAmount: 400 },
        { rowId: 'a3', category: '重分类调整', debitAmount: 0, creditAmount: 250 },
      ]),
    })
    const crossSheet = useF1CrossSheet({ allResponses: ref(map) })
    await nextTick()
    expect(crossSheet.adjustmentTotals.value.ajeTotal).toBe(600)
    expect(crossSheet.adjustmentTotals.value.rjeTotal).toBe(-250)
  })

  it('手工录入优先于明细聚合；明细真为 0 时不回退幽灵手工值', async () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F1-det-rows', {
      item_id: 'F1-det-rows',
      conclusion: null,
      remark: JSON.stringify([{
        ...detailRow({ y1to2: 0, y2to3: 0, over3: 0 }),
        nature: '货款',
        agingAudited: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 },
        endAudited: 0,
      }]),
    })
    // 审定表手工录入「货款」期末未审 888（明细聚合为 0）
    map.set('F1-adj-nature-goods-currentUnadjusted', {
      item_id: 'F1-adj-nature-goods-currentUnadjusted', conclusion: null, remark: '888',
    })
    const allResponses = ref(map)
    const segs = computed(() => PRESET_SEGMENTS.THREE_YEAR)
    const crossSheet = useF1CrossSheet({ allResponses, segments: segs as any })
    const adj = useF1Adjudication({
      allResponses,
      wpId: ref('wp-1'),
      projectId: ref('p1'),
      saveImmediate: vi.fn(),
      debouncedSave: vi.fn(),
      crossSheet,
      isReadonly: ref(false),
      agingSegments: segs as any,
    })
    await nextTick()
    const goods = adj.sections.value[0].rows.find(r => r.rowKey === 'goods')!
    // 手工值生效（修复前：明细聚合非 0 时手工被忽略；明细为 0 时又回退手工=幽灵值）
    expect(goods.currentUnadjusted).toBe(888)
    // 未手工录入的行在明细已编制时取聚合值（此处聚合为 0）
    const other = adj.sections.value[0].rows.find(r => r.rowKey === 'other')!
    expect(other.currentUnadjusted).toBe(0)
  })
})
