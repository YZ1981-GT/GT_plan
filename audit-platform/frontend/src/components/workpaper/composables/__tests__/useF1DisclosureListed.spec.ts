/**
 * useF1DisclosureListed — 账龄折叠 / 占比 / 同步快照
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import {
  collapseAgingForListedDisclosure,
  useF1DisclosureListed,
} from '../useF1DisclosureListed'
import { calcPercentage } from '../useF1FormulaEngine'
import {
  F1_LISTED_SUBTABLE,
  buildF1ListedSubTableData,
  buildF1SyncPayload,
} from '../f1DisclosureSyncPayload'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn() },
}))

describe('calcPercentage / collapseAgingForListedDisclosure', () => {
  it('占比分母为 0 时返回 0', () => {
    expect(calcPercentage(100, 0)).toBe(0)
    expect(calcPercentage(50, 200)).toBe(25)
  })

  it('按枚举段生成账龄行（含 prior_）', () => {
    const buckets = collapseAgingForListedDisclosure({
      within1: 700,
      y1to2: 200,
      y2to3: 50,
      over3: 50,
      prior_within1: 600,
      prior_y1to2: 100,
      prior_y2to3: 0,
      prior_over3: 0,
    })
    expect(buckets).toHaveLength(4)
    expect(buckets[0].label).toBe('1年以内')
    expect(buckets[1].label).toBe('1至2年')
    expect(buckets.map((b) => b.endAmount).reduce((a, b) => a + b, 0)).toBe(1000)
  })

  it('5年段保留全部 6 档（不再折入 3年以上）', () => {
    const buckets = collapseAgingForListedDisclosure(
      {
        within1: 500,
        y1to2: 100,
        y2to3: 100,
        y3to4: 50,
        y4to5: 50,
        over5: 100,
        prior_within1: 0,
        prior_y1to2: 0,
        prior_y2to3: 0,
        prior_y3to4: 0,
        prior_y4to5: 0,
        prior_over5: 0,
      },
      [
        { key: 'within1', label: '1年以内', dayFrom: 0, dayTo: 365 },
        { key: 'y1to2', label: '1-2年', dayFrom: 366, dayTo: 730 },
        { key: 'y2to3', label: '2-3年', dayFrom: 731, dayTo: 1095 },
        { key: 'y3to4', label: '3-4年', dayFrom: 1096, dayTo: 1460 },
        { key: 'y4to5', label: '4-5年', dayFrom: 1461, dayTo: 1825 },
        { key: 'over5', label: '5年以上', dayFrom: 1826, dayTo: null },
      ],
    )
    expect(buckets).toHaveLength(6)
    expect(buckets.find((b) => b.key === 'y3to4')?.endAmount).toBe(50)
    expect(buckets.find((b) => b.key === 'over5')?.endAmount).toBe(100)
    expect(buckets.map((b) => b.endAmount).reduce((a, b) => a + b, 0)).toBe(900)
  })
})

describe('useF1DisclosureListed integration', () => {
  beforeEach(() => {
    vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true)
    vi.spyOn(window, 'addEventListener').mockImplementation(() => undefined)
    vi.spyOn(window, 'removeEventListener').mockImplementation(() => undefined)
  })

  function makeCrossSheet(aging: Record<string, number>, longTerm: any[] = []) {
    return {
      agingAggregation: computed(() => aging),
      agingSegments: computed(() => [
        { key: 'within1', label: '1年以内', dayFrom: 0, dayTo: 365 },
        { key: 'y1to2', label: '1-2年', dayFrom: 366, dayTo: 730 },
        { key: 'y2to3', label: '2-3年', dayFrom: 731, dayTo: 1095 },
        { key: 'over3', label: '3年以上', dayFrom: 1096, dayTo: null },
      ]),
      longTermRows: computed(() => longTerm),
      natureAggregation: computed(() => ({})),
      adjudicationForDisclosure: computed(() => ({
        natureAggregation: {},
        agingAggregation: aging,
        longTermRows: longTerm,
      })),
    } as any
  }

  it('账龄行带比例；Top5 与超1年取数；同步 payload 含三表', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F1-det-rows', {
      item_id: 'F1-det-rows',
      conclusion: null,
      remark: JSON.stringify([
        { customerName: '甲', endAudited: 400, priorAudited: 100, agingAudited: { within1: 0, y1to2: 400 } },
        { customerName: '乙', endAudited: 300, priorAudited: 0, agingAudited: { within1: 300 } },
        { customerName: '丙', endAudited: 200, priorAudited: 0, agingAudited: { within1: 200 } },
        { customerName: '丁', endAudited: 100, priorAudited: 0, agingAudited: { within1: 100 } },
        { customerName: '戊', endAudited: 50, priorAudited: 0, agingAudited: { within1: 50 } },
        { customerName: '己', endAudited: 40, priorAudited: 0, agingAudited: { within1: 40 } },
      ]),
    })

    const api = useF1DisclosureListed({
      allResponses: ref(map),
      wpId: ref('wp-1'),
      projectId: ref('p1'),
      saveImmediate: vi.fn(),
      debouncedSave: vi.fn(),
      crossSheet: makeCrossSheet(
        {
          within1: 690,
          y1to2: 400,
          y2to3: 0,
          over3: 0,
          prior_within1: 500,
          prior_y1to2: 100,
          prior_y2to3: 0,
          prior_over3: 0,
        },
        [{ customerName: '甲', endAudited: 400, agingDescription: '1-2年', agingAudited: {} }],
      ),
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })

    expect(api.agingRows.value[0].endAmount).toBe(690)
    expect(api.agingTotal.value.endAmount).toBe(1090)
    expect(api.agingRows.value[0].endPct).toBeCloseTo((690 / 1090) * 100, 5)
    expect(api.over1YearRows.value[0].debtorName).toBe('甲')
    expect(api.over1YearRows.value[0].proportionPct).toBeCloseTo((400 / 1090) * 100, 5)
    expect(api.top5Rows.value).toHaveLength(5)
    expect(api.top5Rows.value[0].entityName).toBe('甲')

    const snap = api.getSyncSnapshot()
    const sub = buildF1ListedSubTableData(snap)
    // 4 段 + 小计 + 减：减值准备 + 合计
    expect(sub[F1_LISTED_SUBTABLE.AGING] as unknown[]).toHaveLength(7)
    expect((sub[F1_LISTED_SUBTABLE.OVER1] as any[])[0].label).toBe('甲')
    expect(sub[F1_LISTED_SUBTABLE.TOP5] as unknown[]).toHaveLength(6) // 5 + 合计

    const payload = buildF1SyncPayload('listed', 'wp-1', ['listed_standalone'], sub)
    expect(payload?.section_id).toBe('五、7')
    // 真实 tab 名（DB workpaper_sheet_classification），使附注反向跳转能精确定位
    expect(payload?.sheet_name).toBe('附注披露信息(上市公司)')
  })

  it('减值准备双期入表：小计 − 减：减值准备 = 合计', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F1-note-listed-impairment-provision', {
      item_id: 'F1-note-listed-impairment-provision', conclusion: null, remark: '90',
    })
    map.set('F1-note-listed-impairment-provision-prior', {
      item_id: 'F1-note-listed-impairment-provision-prior', conclusion: null, remark: '60',
    })

    const api = useF1DisclosureListed({
      allResponses: ref(map),
      wpId: ref('wp-1'),
      projectId: ref('p1'),
      saveImmediate: vi.fn(),
      debouncedSave: vi.fn(),
      crossSheet: makeCrossSheet({
        within1: 1000, y1to2: 0, y2to3: 0, over3: 0,
        prior_within1: 800, prior_y1to2: 0, prior_y2to3: 0, prior_over3: 0,
      }),
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })

    expect(api.agingTotal.value.label).toBe('小计')
    expect(api.agingImpairmentRow.value.endAmount).toBe(90)
    expect(api.agingImpairmentRow.value.priorAmount).toBe(60)
    expect(api.agingNet.value.endAmount).toBe(1000 - 90)
    expect(api.agingNet.value.priorAmount).toBe(800 - 60)
  })

  it('5年段：附注账龄行推 6 档 + 三行尾，标签用附注简写', () => {
    const fiveYearSegs = [
      { key: 'within1', label: '1年以内', dayFrom: 0, dayTo: 365 },
      { key: 'y1to2', label: '1-2年', dayFrom: 366, dayTo: 730 },
      { key: 'y2to3', label: '2-3年', dayFrom: 731, dayTo: 1095 },
      { key: 'y3to4', label: '3-4年', dayFrom: 1096, dayTo: 1460 },
      { key: 'y4to5', label: '4-5年', dayFrom: 1461, dayTo: 1825 },
      { key: 'over5', label: '5年以上', dayFrom: 1826, dayTo: null },
    ]
    const api = useF1DisclosureListed({
      allResponses: ref(new Map<string, ChecklistResponse>()),
      wpId: ref('wp-1'),
      projectId: ref('p1'),
      saveImmediate: vi.fn(),
      debouncedSave: vi.fn(),
      crossSheet: {
        agingAggregation: computed(() => ({
          within1: 100, y1to2: 100, y2to3: 100, y3to4: 100, y4to5: 100, over5: 100,
        })),
        agingSegments: computed(() => fiveYearSegs),
        longTermRows: computed(() => []),
        natureAggregation: computed(() => ({})),
        adjudicationForDisclosure: computed(() => ({
          natureAggregation: {}, agingAggregation: {}, longTermRows: [],
        })),
      } as any,
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })

    expect(api.agingRows.value.map((r) => r.label)).toEqual([
      '1年以内', '1至2年', '2至3年', '3至4年', '4至5年', '5年以上',
    ])
    const rows = buildF1ListedSubTableData(api.getSyncSnapshot())[F1_LISTED_SUBTABLE.AGING] as any[]
    expect(rows).toHaveLength(9) // 6 段 + 小计 + 减：减值准备 + 合计
    expect(rows.slice(-3).map((r) => r.label)).toEqual(['小计', '减：减值准备', '合计'])
  })

  it('自定义段：标签回退 segment.label，行数随段数', () => {
    const customSegs = [
      { key: 'custom-0', label: '半年以内', dayFrom: 0, dayTo: null },
      { key: 'custom-1', label: '半年至一年', dayFrom: 0, dayTo: null },
      { key: 'custom-2', label: '一年以上', dayFrom: 0, dayTo: null },
    ]
    const api = useF1DisclosureListed({
      allResponses: ref(new Map<string, ChecklistResponse>()),
      wpId: ref('wp-1'),
      projectId: ref('p1'),
      saveImmediate: vi.fn(),
      debouncedSave: vi.fn(),
      crossSheet: {
        agingAggregation: computed(() => ({ 'custom-0': 50, 'custom-1': 30, 'custom-2': 20 })),
        agingSegments: computed(() => customSegs),
        longTermRows: computed(() => []),
        natureAggregation: computed(() => ({})),
        adjudicationForDisclosure: computed(() => ({
          natureAggregation: {}, agingAggregation: {}, longTermRows: [],
        })),
      } as any,
      isReadonly: ref(false),
      applicableStandards: ref(['listed_standalone']),
    })

    expect(api.agingRows.value.map((r) => r.label)).toEqual(['半年以内', '半年至一年', '一年以上'])
    expect(api.agingTotal.value.endAmount).toBe(100)
  })
})
