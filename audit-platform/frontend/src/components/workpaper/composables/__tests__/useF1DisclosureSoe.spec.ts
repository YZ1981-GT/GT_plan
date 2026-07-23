/**
 * useF1DisclosureSoe — 账龄+坏账 / 超1年 / 前五名 / 同步八、7
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'
import { useF1DisclosureSoe } from '../useF1DisclosureSoe'
import { buildF1SoeSubTableData, buildF1SyncPayload } from '../f1DisclosureSyncPayload'
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
    expect(sub['预付款项按账龄列示'][0].label).toContain('含1年')
    expect(sub['账龄超过1年的大额预付款项'][0].debtor_unit).toBe('供应商A')
    expect(sub['按欠款方归集的期末余额前五名的预付款项']).toHaveLength(6)

    const payload = buildF1SyncPayload('soe', 'wp-1', ['soe_standalone'], sub)
    expect(payload?.section_id).toBe('八、7')
    expect(payload?.sheet_name).toBe('F1-note-soe')
  })
})
