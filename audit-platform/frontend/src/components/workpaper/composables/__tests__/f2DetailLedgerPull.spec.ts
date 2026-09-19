import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock api.get
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
  },
}))

import { api } from '@/services/apiProxy'
import { pullF2DetailFromLedger, F2_DETAIL_SHEET_ACCOUNT } from '../f2DetailLedgerPull'

describe('f2DetailLedgerPull', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('aggregates by account_name (Property 1)', async () => {
    // 同一 account_name 多条分录合并
    ;(api.get as any).mockResolvedValueOnce({
      items: [
        { account_name: '原材料-甲', account_code: '1401.01', debit_amount: 1000, credit_amount: 200 },
        { account_name: '原材料-甲', account_code: '1401.01', debit_amount: 500, credit_amount: 100 },
        { account_name: '原材料-乙', account_code: '1401.02', debit_amount: 300, credit_amount: 50 },
      ],
    })

    const result = await pullF2DetailFromLedger('pid', '1401', 2025)
    expect(result.rows).toHaveLength(2)

    const jia = result.rows.find(r => r.name === '原材料-甲')
    expect(jia).toBeDefined()
    expect(jia!.increase).toBe(1500) // 1000+500
    expect(jia!.decrease).toBe(300)  // 200+100

    const yi = result.rows.find(r => r.name === '原材料-乙')
    expect(yi!.increase).toBe(300)
    expect(yi!.decrease).toBe(50)
  })

  it('returns empty on error (Property 4)', async () => {
    ;(api.get as any).mockRejectedValueOnce(new Error('network fail'))

    const result = await pullF2DetailFromLedger('pid', '1401', 2025)
    expect(result.rows).toHaveLength(0)
    expect(result.totalIncrease).toBe(0)
    expect(result.totalDecrease).toBe(0)
    expect(result.pagesFetched).toBe(0)
  })

  it('only fetches target account (Property 5)', async () => {
    ;(api.get as any).mockResolvedValueOnce({ items: [] })

    await pullF2DetailFromLedger('pid', '1406', 2025)
    expect(api.get).toHaveBeenCalledWith(
      expect.stringContaining('/ledger/entries/1406'),
      expect.anything(),
    )
  })

  it('handles multi-page aggregation', async () => {
    // Page 1: 满页（200条）
    const page1 = Array.from({ length: 200 }, (_, i) => ({
      account_name: `item-${i % 5}`,
      account_code: `1401.${String(i % 5).padStart(2, '0')}`,
      debit_amount: 10,
      credit_amount: 2,
    }))
    // Page 2: 不满页
    const page2 = [
      { account_name: 'item-0', account_code: '1401.00', debit_amount: 100, credit_amount: 20 },
    ]

    ;(api.get as any)
      .mockResolvedValueOnce({ items: page1 })
      .mockResolvedValueOnce({ items: page2 })

    const result = await pullF2DetailFromLedger('pid', '1401', 2025)
    expect(result.pagesFetched).toBe(2)
    // item-0: 200/5=40 条×10 + 100 = 500 increase
    const item0 = result.rows.find(r => r.name === 'item-0')
    expect(item0!.increase).toBe(500) // 40*10 + 100
    expect(item0!.decrease).toBe(100) // 40*2 + 20
  })

  it('returns empty for missing params', async () => {
    const result = await pullF2DetailFromLedger('', '1401', 2025)
    expect(result.rows).toHaveLength(0)
    expect(api.get).not.toHaveBeenCalled()
  })

  it('F2_DETAIL_SHEET_ACCOUNT has 11 entries', () => {
    expect(Object.keys(F2_DETAIL_SHEET_ACCOUNT)).toHaveLength(11)
    expect(F2_DETAIL_SHEET_ACCOUNT['F2-3']).toBe('1401')
    expect(F2_DETAIL_SHEET_ACCOUNT['F2-13']).toBe('1411')
  })
})
