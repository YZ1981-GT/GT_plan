/**
 * F2 NRV 售价参考取数 — 纯函数 + 优雅降级单测（Task 5, Req 10）
 *
 * 覆盖：
 * - parseSalesPriceEntries：正确算单价（credit/qty）；按 itemName 过滤；跳过 qty/credit<=0。
 * - pullRecentSalesPrice：不可得时 status=empty + prices=[]；请求失败 → error。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

import { api } from '@/services/apiProxy'
import {
  parseSalesPriceEntries,
  pullRecentSalesPrice,
  SALES_PRICE_SOURCE_LEDGER,
} from '../f2NrvPricePull'

const mockGet = vi.mocked(api.get)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('parseSalesPriceEntries', () => {
  it('computes unitPrice = credit / qty; skips qty<=0 or credit<=0', () => {
    const entries = [
      { credit_amount: 1000, credit_quantity: 10, aux_name: '产品A' },
      { credit_amount: 500, credit_quantity: 0, aux_name: '产品B' }, // skipped (qty=0)
      { credit_amount: 2000, credit_quantity: 20, aux_name: '产品C' },
      { credit_amount: -100, credit_quantity: 5, aux_name: '产品D' }, // skipped (credit<0)
    ]
    const prices = parseSalesPriceEntries(entries)
    expect(prices).toHaveLength(2)
    expect(prices[0].unitPrice).toBeCloseTo(100) // A: 1000/10
    expect(prices[0].name).toBe('产品A')
    expect(prices[0].source).toBe(SALES_PRICE_SOURCE_LEDGER)
    expect(prices[1].unitPrice).toBeCloseTo(100) // C: 2000/20
  })

  it('filters by itemName (normalized includes match)', () => {
    const entries = [
      { credit_amount: 600, credit_quantity: 6, aux_name: '原材料甲' },
      { credit_amount: 800, credit_quantity: 4, aux_name: '原材料乙' },
    ]
    const prices = parseSalesPriceEntries(entries, '原材料甲')
    expect(prices).toHaveLength(1)
    expect(prices[0].name).toBe('原材料甲')
    expect(prices[0].unitPrice).toBeCloseTo(100)
  })

  it('returns empty for null/empty entries', () => {
    expect(parseSalesPriceEntries(null)).toEqual([])
    expect(parseSalesPriceEntries([])).toEqual([])
    expect(parseSalesPriceEntries('bad')).toEqual([])
  })

  it('names unnamed entries as 未命名商品', () => {
    const entries = [
      { credit_amount: 500, credit_quantity: 5 }, // no name fields
    ]
    const prices = parseSalesPriceEntries(entries)
    expect(prices).toHaveLength(1)
    expect(prices[0].name).toBe('未命名商品')
    expect(prices[0].unitPrice).toBeCloseTo(100)
  })

  it('respects custom source label', () => {
    const entries = [{ credit_amount: 100, credit_quantity: 1, aux_name: 'X' }]
    const prices = parseSalesPriceEntries(entries, undefined, 'D4明细')
    expect(prices[0].source).toBe('D4明细')
  })
})

describe('pullRecentSalesPrice — graceful degradation', () => {
  it('error when projectId missing', async () => {
    const r = await pullRecentSalesPrice('', 2025)
    expect(r.status).toBe('error')
    expect(r.prices).toEqual([])
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('error when year invalid', async () => {
    const r = await pullRecentSalesPrice('p1', 0)
    expect(r.status).toBe('error')
  })

  it('empty when no valid prices (all qty=0)', async () => {
    mockGet.mockResolvedValueOnce({
      items: [{ credit_amount: 1000, credit_quantity: 0, aux_name: 'X' }],
    })
    const r = await pullRecentSalesPrice('p1', 2025)
    expect(r.status).toBe('empty')
    expect(r.prices).toEqual([])
  })

  it('ok with extracted prices', async () => {
    mockGet.mockResolvedValueOnce({
      items: [
        { credit_amount: 5000, credit_quantity: 50, aux_name: '产品Z' },
      ],
    })
    const r = await pullRecentSalesPrice('p1', 2025)
    expect(r.status).toBe('ok')
    expect(r.prices).toHaveLength(1)
    expect(r.prices[0].unitPrice).toBeCloseTo(100)
    expect(r.prices[0].name).toBe('产品Z')
  })

  it('filters by itemName when provided', async () => {
    mockGet.mockResolvedValueOnce({
      items: [
        { credit_amount: 300, credit_quantity: 3, aux_name: '甲产品' },
        { credit_amount: 400, credit_quantity: 4, aux_name: '乙产品' },
      ],
    })
    const r = await pullRecentSalesPrice('p1', 2025, '甲产品')
    expect(r.status).toBe('ok')
    expect(r.prices).toHaveLength(1)
    expect(r.prices[0].name).toBe('甲产品')
  })

  it('error on request failure (no throw)', async () => {
    mockGet.mockRejectedValueOnce(new Error('network'))
    const r = await pullRecentSalesPrice('p1', 2025)
    expect(r.status).toBe('error')
    expect(r.prices).toEqual([])
  })
})
