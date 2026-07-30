/**
 * useF1DisclosureSoe — 账龄+坏账 / 超1年 / 前五名 / 同步八、7
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import { useF1DisclosureSoe } from '../useF1DisclosureSoe'
import {
  F1_SOE_SUBTABLE,
  buildF1SoeSubTableData,
  buildF1SyncPayload,
} from '../f1DisclosureSyncPayload'
import type { ChecklistResponse } from '../useF1FormData'

describe('useF1DisclosureSoe', () => {
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

  it('四档账龄含含1年标签与坏账列；同步 payload 指向八、7', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F1-det-rows', {
      item_id: 'F1-det-rows',
      conclusion: null,
      remark: JSON.stringify([
        { customerName: '供应商A', endAudited: 500, priorAudited: 0 },
        { customerName: '供应商B', endAudited: 300, priorAudited: 0 },
        { customerName: '供应商C', endAudited: 200, priorAudited: 0 },
        { customerName: '供应商D', endAudited: 100, priorAudited: 0 },
        { customerName: '供应商E', endAudited: 80, priorAudited: 0 },
        { customerName: '供应商F', endAudited: 20, priorAudited: 0 },
      ]),
    })
    map.set('F1-note-soe-aging-bad-debt', {
      item_id: 'F1-note-soe-aging-bad-debt',
      conclusion: null,
      remark: JSON.stringify({ within1: { end: 10, prior: 5 } }),
    })

    const api = useF1DisclosureSoe({
      allResponses: ref(map),
      wpId: ref('wp-1'),
      projectId: ref('p1'),
      saveImmediate: vi.fn(),
      debouncedSave: vi.fn(),
      crossSheet: makeCrossSheet(
        {
          within1: 800,
          y1to2: 200,
          y2to3: 0,
          over3: 0,
          prior_within1: 700,
          prior_y1to2: 100,
          prior_y2to3: 0,
          prior_over3: 0,
        },
        [{ customerName: '供应商A', endAudited: 500, agingDescription: '1至2年', agingAudited: {} }],
      ),
      isReadonly: ref(false),
      applicableStandards: ref(['soe_standalone']),
    })

    expect(api.agingRows.value[0].label).toContain('含1年')
    expect(api.agingRows.value[0].endBadDebt).toBe(10)
    expect(api.agingTotal.value.endAmount).toBe(1000)
    expect(api.over1YearRows.value[0].debtorUnit).toBe('供应商A')
    expect(api.top5Rows.value).toHaveLength(5)

    const snap = api.getSyncSnapshot()
    const sub = buildF1SoeSubTableData(snap)
    const agingRows = sub[F1_SOE_SUBTABLE.AGING] as any[]
    expect(agingRows[0].label).toContain('含1年')
    // 4 段 + 小计 + 减：减值准备 + 合计
    expect(agingRows).toHaveLength(7)
    expect(agingRows.slice(-3).map((r) => r.label)).toEqual(['小计', '减：减值准备', '合计'])
    expect((sub[F1_SOE_SUBTABLE.OVER1] as any[])[0].debtor_unit).toBe('供应商A')
    expect(sub[F1_SOE_SUBTABLE.TOP5] as unknown[]).toHaveLength(6)

    const payload = buildF1SyncPayload('soe', 'wp-1', ['soe_standalone'], sub)
    expect(payload?.section_id).toBe('八、7')
    // 真实 tab 名（DB workpaper_sheet_classification）
    expect(payload?.sheet_name).toBe('附注披露信息(国企)')
  })

  it('逐段减值准备聚合为「减：减值准备」行；合计 = 小计 − 减值准备', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F1-note-soe-aging-bad-debt', {
      item_id: 'F1-note-soe-aging-bad-debt',
      conclusion: null,
      remark: JSON.stringify({
        within1: { end: 10, prior: 5 },
        y1to2: { end: 20, prior: 15 },
      }),
    })

    const api = useF1DisclosureSoe({
      allResponses: ref(map),
      wpId: ref('wp-1'),
      projectId: ref('p1'),
      saveImmediate: vi.fn(),
      debouncedSave: vi.fn(),
      crossSheet: makeCrossSheet({
        within1: 800, y1to2: 200, y2to3: 0, over3: 0,
        prior_within1: 700, prior_y1to2: 100, prior_y2to3: 0, prior_over3: 0,
      }),
      isReadonly: ref(false),
      applicableStandards: ref(['soe_standalone']),
    })

    expect(api.agingTotal.value.label).toBe('小计')
    expect(api.agingImpairmentRow.value.endAmount).toBe(30)
    expect(api.agingImpairmentRow.value.priorAmount).toBe(20)
    expect(api.agingNet.value.endAmount).toBe(1000 - 30)
    expect(api.agingNet.value.priorAmount).toBe(800 - 20)

    const rows = buildF1SoeSubTableData(api.getSyncSnapshot())[F1_SOE_SUBTABLE.AGING] as any[]
    // 附注侧为 5 列：逐段减值准备列不再出现在明细行
    expect(rows[0].end_bad_debt).toBeUndefined()
    expect(rows[5].end_amount).toBe(30)
    expect(rows[6].end_amount).toBe(970)
  })

  it('5年段：账龄行推 6 档，首档仍带「含1年」', () => {
    const fiveYearSegs = [
      { key: 'within1', label: '1年以内', dayFrom: 0, dayTo: 365 },
      { key: 'y1to2', label: '1-2年', dayFrom: 366, dayTo: 730 },
      { key: 'y2to3', label: '2-3年', dayFrom: 731, dayTo: 1095 },
      { key: 'y3to4', label: '3-4年', dayFrom: 1096, dayTo: 1460 },
      { key: 'y4to5', label: '4-5年', dayFrom: 1461, dayTo: 1825 },
      { key: 'over5', label: '5年以上', dayFrom: 1826, dayTo: null },
    ]
    const api = useF1DisclosureSoe({
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
      applicableStandards: ref(['soe_standalone']),
    })

    expect(api.agingRows.value.map((r) => r.label)).toEqual([
      '1年以内（含1年）', '1至2年', '2至3年', '3至4年', '4至5年', '5年以上',
    ])
    const rows = buildF1SoeSubTableData(api.getSyncSnapshot())[F1_SOE_SUBTABLE.AGING] as any[]
    expect(rows).toHaveLength(9)
  })
})
