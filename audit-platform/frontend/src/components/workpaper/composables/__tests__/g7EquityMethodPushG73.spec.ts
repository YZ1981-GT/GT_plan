/**
 * g7EquityMethodPushG73 — 推送 G7-3 单测（if_match / 不发 adjustment:updated）
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpMocks = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: httpMocks }))

vi.mock('@/services/workpaperApi', () => ({
  listWorkpapers: vi.fn(),
  getWorkpaper: vi.fn(async () => ({
    id: 'main-wp',
    wp_code: 'G7',
    component_type: 'g7-long-term-equity-main',
  })),
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() },
}))

import { eventBus } from '@/utils/eventBus'
import { pushSuggestedAdjustmentsToG73 } from '../../g7-long-term-equity-method/calculation/g7EquityMethodPushG73'
import { G714_SUGGESTED_SOURCE_KIND } from '../../g7-long-term-equity-method/calculation/g7EquityMethodCalcModel'

describe('pushSuggestedAdjustmentsToG73', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    httpMocks.get.mockImplementation(async (url: string) => {
      if (String(url).includes('acnr/resolve-instance')) {
        return { data: { data: { wp_id: 'main-wp' } } }
      }
      if (String(url).includes('checklist-responses')) {
        return {
          data: [{
            item_id: 'G7-3-rows',
            conclusion: JSON.stringify([
              { id: 'manual-1', description: '手工', sourceKind: '', debitAmount: 1, creditAmount: 0 },
              {
                id: 'old-sug',
                description: '旧建议',
                sourceKind: G714_SUGGESTED_SOURCE_KIND,
                remark: `sourceKind=${G714_SUGGESTED_SOURCE_KIND}`,
                debitAmount: 9,
                creditAmount: 0,
              },
            ]),
            version: 'v1',
          }],
        }
      }
      return { data: {} }
    })
    httpMocks.put.mockResolvedValue({ data: { ok: true } })
  })

  it('合并写入并仅替换同源建议；不发 adjustment:updated', async () => {
    const events: CustomEvent[] = []
    const handler = (ev: Event) => events.push(ev as CustomEvent)
    window.addEventListener('g7:adjustment-pushed', handler)

    const result = await pushSuggestedAdjustmentsToG73({
      projectId: 'proj-1',
      currentWpId: 'equity-wp',
      lines: [{
        id: 'sug-dr',
        investeeName: '甲',
        description: '新建议',
        category: '账项调整',
        reportItem: '长期股权投资',
        accountCode: '1511',
        accountName: '长期股权投资',
        debitAmount: 100,
        creditAmount: 0,
        indexRef: 'G7-14',
        remark: `sourceKind=${G714_SUGGESTED_SOURCE_KIND}`,
        source: 'incomeDifference',
        sourceKind: G714_SUGGESTED_SOURCE_KIND,
      }, {
        id: 'sug-cr',
        investeeName: '甲',
        description: '新建议',
        category: '账项调整',
        reportItem: '长期股权投资',
        accountCode: '6111',
        accountName: '投资收益',
        debitAmount: 0,
        creditAmount: 100,
        indexRef: 'G7-14',
        remark: `sourceKind=${G714_SUGGESTED_SOURCE_KIND}`,
        source: 'incomeDifference',
        sourceKind: G714_SUGGESTED_SOURCE_KIND,
      }],
    })

    window.removeEventListener('g7:adjustment-pushed', handler)

    expect(result.ok).toBe(true)
    expect(result.written).toBe(2)
    expect(eventBus.emit).not.toHaveBeenCalledWith('adjustment:updated')
    expect(events.some(e => e.type === 'g7:adjustment-pushed')).toBe(true)

    const putBody = httpMocks.put.mock.calls[0]?.[1]
    const item = putBody?.items?.[0]
    expect(item?.if_match).toBe('v1')
    const merged = JSON.parse(item.conclusion)
    expect(merged.some((r: any) => r.id === 'manual-1')).toBe(true)
    expect(merged.some((r: any) => r.id === 'old-sug')).toBe(false)
    expect(merged.filter((r: any) => r.sourceKind === G714_SUGGESTED_SOURCE_KIND)).toHaveLength(2)
  })

  it('版本冲突返回 conflict', async () => {
    httpMocks.put.mockRejectedValue({
      response: { status: 409, data: { detail: { code: 'version_conflict' } } },
    })
    const result = await pushSuggestedAdjustmentsToG73({
      projectId: 'proj-1',
      lines: [{
        id: 'x',
        investeeName: '甲',
        description: 'x',
        category: '账项调整',
        reportItem: '长期股权投资',
        accountCode: '1511',
        accountName: '长期股权投资',
        debitAmount: 1,
        creditAmount: 0,
        indexRef: 'G7-14',
        remark: '',
        source: 'incomeDifference',
        sourceKind: G714_SUGGESTED_SOURCE_KIND,
      }],
    })
    expect(result.ok).toBe(false)
    expect(result.conflict).toBe(true)
  })
})
