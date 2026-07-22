/**
 * H1 ← H6 清理余额跨底稿取数 单测
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import {
  extractH61Balances,
  mapH62ToClearingRows,
  pullH6ClearingForH1Listed,
  pullH6ClearingForH1Soe,
} from '../h1SoeClearingH6Pull'

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { api } from '@/services/apiProxy'

describe('extractH61Balances / mapH62ToClearingRows', () => {
  it('reads begin/end from H6-1 balance rows', () => {
    const { begin, end } = extractH61Balances([
      { name: '清理收入', category: 'income', audited: 100 },
      { name: '期初余额', category: 'balance', audited: 30, beginBalance: 30 },
      { name: '本期发生', category: 'balance', audited: -10 },
      { name: '期末余额', category: 'balance', audited: 20, endBalance: 20 },
    ])
    expect(begin).toBe(30)
    expect(end).toBe(20)
  })

  it('reads begin/end from Excel-aligned H6-1 rows', () => {
    const { begin, end } = extractH61Balances([
      { name: '设备A', beginAudited: 10, endAudited: 0, beginUnadjusted: 10, endUnadjusted: 0 },
      { name: '设备B', beginAudited: 20, endAudited: 5, beginUnadjusted: 20, endUnadjusted: 5 },
    ])
    expect(begin).toBe(30)
    expect(end).toBe(5)
  })

  it('maps H6-2 active rows and flags over-1-year', () => {
    const old = new Date()
    old.setFullYear(old.getFullYear() - 2)
    const { rows, overOneYearCount, overOneYearNote } = mapH62ToClearingRows([
      {
        rowId: '1',
        assetName: '旧设备',
        netBookValue: 50,
        disposalReason: '报废',
        status: '清理中',
        startDate: old.toISOString().slice(0, 10),
      },
      {
        rowId: '2',
        assetName: '已结转',
        netBookValue: 0,
        disposalReason: '出售',
        status: '已结转',
        startDate: '2026-01-01',
      },
    ])
    expect(rows).toHaveLength(1)
    expect(rows[0].name).toBe('旧设备')
    expect(rows[0].endCarrying).toBe(50)
    expect(rows[0].reason).toContain('超1年')
    expect(overOneYearCount).toBe(1)
    expect(overOneYearNote).toContain('旧设备')
  })
})

describe('pullH6ClearingForH1Soe', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  it('returns wp_missing when H6 not in project', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({ wp_id: null } as any)
    const r = await pullH6ClearingForH1Soe('proj-1')
    expect(r.status).toBe('wp_missing')
  })

  it('pulls end balance and detail from H6 checklist', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ wp_id: 'wp-h6' } as any)
      .mockResolvedValueOnce([
        { item_id: 'H6-1-end-balance-audited', remark: '1200' },
        {
          item_id: 'H6-1-rows',
          remark: JSON.stringify([
            { name: '期初余额', category: 'balance', audited: 800 },
            { name: '期末余额', category: 'balance', audited: 1200 },
          ]),
        },
        {
          item_id: 'H6-2-rows',
          remark: JSON.stringify([
            {
              rowId: 'd1',
              assetName: '叉车',
              netBookValue: 1200,
              disposalReason: '待拍卖',
              status: '清理中',
              startDate: '2026-03-01',
            },
          ]),
        },
      ] as any)

    const r = await pullH6ClearingForH1Soe('proj-1')
    expect(r.status).toBe('ok')
    expect(r.h6WpId).toBe('wp-h6')
    expect(r.clearingEnd).toBe(1200)
    expect(r.clearingBegin).toBe(800)
    expect(r.clearingRows).toHaveLength(1)
    expect(r.clearingRows[0].name).toBe('叉车')
    expect(r.transitZero).toBe(false)
  })
})

describe('pullH6ClearingForH1Listed', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
  })

  it('maps soe carrying fields to listed end/prior balances', async () => {
    vi.mocked(api.get)
      .mockResolvedValueOnce({ wp_id: 'wp-h6' } as any)
      .mockResolvedValueOnce([
        { item_id: 'H6-1-end-balance-audited', remark: '100' },
        {
          item_id: 'H6-2-rows',
          remark: JSON.stringify([
            {
              rowId: 'd1',
              assetName: '机床',
              netBookValue: 100,
              disposalReason: '报废',
              status: '清理中',
              startDate: '2026-01-01',
            },
          ]),
        },
      ] as any)

    const r = await pullH6ClearingForH1Listed('proj-1')
    expect(r.status).toBe('ok')
    expect(r.clearingRows[0]).toMatchObject({
      name: '机床',
      endBalance: 100,
      reason: '报废',
    })
    expect(r.clearingPrior).toBeDefined()
  })
})
