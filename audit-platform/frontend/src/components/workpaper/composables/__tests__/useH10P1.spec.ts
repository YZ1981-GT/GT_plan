/**
 * H10 P1 — 跨 WP H6 勾稽 / 抽凭回填 / 调整 eventBus
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useH10CrossSheet } from '../useH10CrossSheet'
import { useH10Check, H10_CHECK_MIN_SAMPLE_RATIO } from '../useH10Check'
import { useH10Adjustment } from '../useH10Adjustment'
import { pullH6ClearingNetForH10 } from '../h10RelatedH6Pull'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
  },
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() },
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { prompt: vi.fn() },
}))

describe('pullH6ClearingNetForH10', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('汇总 H6-2-rows 的 netGainLoss', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ wp_id: 'h6-wp' } as any)
      .mockResolvedValueOnce([
        {
          item_id: 'H6-2-rows',
          remark: JSON.stringify([
            { netGainLoss: 100 },
            { gainLoss: 50 },
          ]),
        },
      ] as any)

    const r = await pullH6ClearingNetForH10('p1')
    expect(r.status).toBe('ok')
    expect(r.netGainLoss).toBe(150)
    expect(r.rowCount).toBe(2)
  })

  it('无 H6 底稿时返回 wp_missing', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({} as any)
    const r = await pullH6ClearingNetForH10('p1')
    expect(r.status).toBe('wp_missing')
  })
})

describe('useH10CrossSheet remote H6', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('refreshH6CrossCheck 优先使用远程净损益', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ wp_id: 'h6-wp' } as any)
      .mockResolvedValueOnce([
        {
          item_id: 'H6-2-rows',
          remark: JSON.stringify([{ netGainLoss: 200 }]),
        },
      ] as any)

    const allResponses = ref(new Map<string, any>([
      ['H10-adj-rows', {
        item_id: 'H10-adj-rows',
        remark: JSON.stringify({
          fixed_asset_disposal: { currentUnadjusted: 200, currentAje: 0, currentRje: 0 },
        }),
      }],
    ]))
    const projectId = ref('p1')
    const cross = useH10CrossSheet({ allResponses, projectId })
    expect(cross.h10VsH6.value.h6Available).toBe(false)

    const result = await cross.refreshH6CrossCheck()
    expect(result.h6Available).toBe(true)
    expect(result.h6Source).toBe('remote')
    expect(result.h6NetGainLoss).toBe(200)
    expect(result.isMatch).toBe(true)
  })
})

describe('useH10Check fillFromSampledVouchers', () => {
  it('回填凭证索引并计算抽查比例', () => {
    const allResponses = ref(new Map<string, any>([
      ['H10-detail-rows', {
        item_id: 'H10-detail-rows',
        remark: JSON.stringify([
          { id: 'd1', assetName: '设备A' },
          { id: 'd2', assetName: '设备B' },
          { id: 'd3', assetName: '设备C' },
          { id: 'd4', assetName: '设备D' },
          { id: 'd5', assetName: '设备E' },
        ]),
      }],
    ]))
    const saves: Array<{ id: string; remark?: string }> = []
    const api = useH10Check({
      allResponses,
      debouncedSave: (id, d) => { saves.push({ id, remark: d.remark ?? undefined }) },
      isReadonly: ref(false),
    })

    expect(api.detailPopulation.value).toBe(5)
    expect(api.sampleRatioLow.value).toBe(true)

    const n = api.fillFromSampledVouchers([
      { voucherNo: 'V001', date: '2025-01-01', summary: '处置1' },
    ])
    expect(n).toBe(1)
    expect(api.rows.value[0].voucherRef).toContain('V001')
    expect(api.sampleRatio.value).toBeCloseTo(0.2, 5)
    expect(api.sampleRatioLow.value).toBe(false)
    expect(H10_CHECK_MIN_SAMPLE_RATIO).toBe(0.2)
  })
})

describe('useH10Adjustment eventBus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('syncWriteback 同时 emit eventBus 与 window CustomEvent', () => {
    const allResponses = ref(new Map<string, any>())
    const adj = useH10Adjustment({
      allResponses,
      debouncedSave: (id, d) => {
        allResponses.value.set(id, { item_id: id, conclusion: null, remark: d.remark ?? null })
      },
      isReadonly: ref(false),
    })

    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
    adj.updateRow // touch
    // 直接写一行并 sync
    const list = [{
      rowId: 'a1',
      seq: 1,
      entryType: 'AJE' as const,
      date: '',
      summary: '测试',
      accountCode: '6115',
      accountName: '资产处置损益',
      debitAmount: 0,
      creditAmount: 100,
      preparedBy: '',
      remark: '',
    }]
    allResponses.value.set('H10-adjustment-rows', {
      item_id: 'H10-adjustment-rows',
      conclusion: null,
      remark: JSON.stringify(list),
    })
    adj.syncWriteback(list)

    expect(eventBus.emit).toHaveBeenCalledWith(
      'adjustment:created',
      expect.objectContaining({ wpCode: 'H10', entryType: 'AJE', amount: 100 }),
    )
    expect(dispatchSpy).toHaveBeenCalled()
    dispatchSpy.mockRestore()
  })
})
