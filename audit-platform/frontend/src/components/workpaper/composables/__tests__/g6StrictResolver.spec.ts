import { describe, expect, it, vi, beforeEach } from 'vitest'
import {
  resolveG6MainWorkpaperDetailed,
  resolveG6EclWorkpaperDetailed,
  writeG6ClassificationSummary,
  saveG62DetailRows,
  saveG64AdjustmentEntries,
  mapG62RowsToSppiSeeds,
  matchG6SaveItemsEvent,
  parseG6ClassificationSummary,
} from '../g6CrossHelpers'

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
  },
}))

import http from '@/utils/http'

describe('G6 strict resolver', () => {
  beforeEach(() => {
    vi.mocked(http.get).mockReset()
    vi.mocked(http.put).mockReset()
  })

  it('allowFallback=false 时解析失败不回退当前 wp', async () => {
    vi.mocked(http.get).mockRejectedValue(new Error('network'))
    const result = await resolveG6MainWorkpaperDetailed(
      'proj-1',
      'sppi-wp',
      { allowFallback: false },
    )
    expect(result.wpId).toBeNull()
    expect(result.source).toBe('none')
    expect(result.error).toContain('未解析到实例')
  })

  it('默认允许 fallback 时回退当前 wp', async () => {
    vi.mocked(http.get).mockRejectedValue(new Error('network'))
    const result = await resolveG6EclWorkpaperDetailed('proj-1', 'main-wp')
    expect(result.wpId).toBe('main-wp')
    expect(result.source).toBe('fallback')
  })

  it('writeG6ClassificationSummary 不把 SPPI wp 当 Main 写入', async () => {
    vi.mocked(http.get).mockRejectedValue(new Error('network'))
    vi.mocked(http.put).mockResolvedValue({ data: {} })
    const result = await writeG6ClassificationSummary({
      projectId: 'proj-1',
      sppiWpId: 'sppi-wp',
      summary: {
        businessModel: 'hold_and_sell',
        businessModelLabel: '兼有',
        sppiOverall: 'pass',
        expectedClassification: 'FVOCI',
        level: 'ok',
        message: 'ok',
        accountConflict: false,
        updatedAt: '2026-01-01',
        source: 'G6-8',
      },
    })
    expect(result.mainOk).toBe(false)
    expect(result.sppiOk).toBe(true)
    expect(result.mainWpId).toBeNull()
    expect(result.resolveError).toBeTruthy()
    // 仅写入 SPPI 一次
    expect(vi.mocked(http.put)).toHaveBeenCalledTimes(1)
    expect(vi.mocked(http.put).mock.calls[0][0]).toContain('/workpapers/sppi-wp/')
  })

  it('saveG62DetailRows 解析失败直接返回 null 且不写库', async () => {
    vi.mocked(http.get).mockRejectedValue(new Error('network'))
    const wpId = await saveG62DetailRows('proj-1', [{ investProject: 'A' }], 'sppi-wp')
    expect(wpId).toBeNull()
    expect(vi.mocked(http.put)).not.toHaveBeenCalled()
  })

  it('saveG64AdjustmentEntries 解析失败不写库', async () => {
    vi.mocked(http.get).mockRejectedValue(new Error('network'))
    const wpId = await saveG64AdjustmentEntries('proj-1', [], 'sppi-wp')
    expect(wpId).toBeNull()
    expect(vi.mocked(http.put)).not.toHaveBeenCalled()
  })

  it('mapG62RowsToSppiSeeds 优先 crossSheetInvestmentId 且允许同名异券', () => {
    const seeds = mapG62RowsToSppiSeeds([
      { id: 'row-1', crossSheetInvestmentId: 'stable-a', investProject: '国债A' },
      { id: 'row-2', crossSheetInvestmentId: 'stable-b', investProject: '国债A' },
      { investProject: '旧券无ID' },
      { investProject: '旧券无ID' },
    ])
    expect(seeds.map(s => s.id)).toEqual(['stable-a', 'stable-b', 'g6-2-旧券无ID'])
    expect(seeds.filter(s => s.name === '国债A')).toHaveLength(2)
  })

  it('matchG6SaveItemsEvent 按 wpId 过滤', () => {
    const ok = new CustomEvent('g6:save-items', {
      detail: { wpId: 'wp-1', items: [{ item_id: 'G6-1-rows', remark: '{}' }] },
    })
    const wrong = new CustomEvent('g6:save-items', {
      detail: { wpId: 'wp-2', items: [{ item_id: 'G6-1-rows', remark: '{}' }] },
    })
    const legacy = new CustomEvent('g6:save-items', {
      detail: { items: [{ item_id: 'G6-1-rows', remark: '{}' }] },
    })
    expect(matchG6SaveItemsEvent(ok, 'wp-1')?.length).toBe(1)
    expect(matchG6SaveItemsEvent(wrong, 'wp-1')).toBeNull()
    expect(matchG6SaveItemsEvent(legacy, 'wp-1')).toBeNull()
  })

  it('parseG6ClassificationSummary 保留 instruments 矩阵', () => {
    const parsed = parseG6ClassificationSummary({
      remark: JSON.stringify({
        businessModel: 'hold_and_sell',
        expectedClassification: 'FVTPL',
        instruments: [
          { instrumentId: 'a', instrumentName: '债A', expectedClassification: 'FVOCI-Debt' },
        ],
      }),
    })
    expect(parsed?.instruments).toHaveLength(1)
    expect(parsed?.instruments?.[0].instrumentName).toBe('债A')
  })
})
