/**
 * F2 期后出库取数 — 纯函数 + 优雅降级单测（Task 4, Req 4）
 *
 * 覆盖 Property 5：aggregateOutboundByName 归集 totalAmount = 输入贷方合计；幂等。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

import {
  normalizeInvName,
  aggregateOutboundByName,
  pullPostPeriodOutbound,
  UNMATCHED_NAME,
  type PostPeriodOutboundEntry,
} from '../f2LedgerPostOutbound'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
  vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('test-token')
})

afterEach(() => {
  vi.clearAllMocks()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function mockFetchOk(data: unknown) {
  ;(globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
    ok: true,
    json: async () => ({ data }),
  })
}

function mockFetchNotOk() {
  ;(globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({ ok: false, status: 404 })
}

function mockFetchReject(msg: string) {
  ;(globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error(msg))
}

describe('normalizeInvName', () => {
  it('removes whitespace + full-width spaces + lowercase', () => {
    expect(normalizeInvName('  原材料　甲  ')).toBe('原材料甲')
    expect(normalizeInvName('ABC Def')).toBe('abcdef')
  })

  it('is idempotent', () => {
    const s = '  库存　商品 A '
    expect(normalizeInvName(normalizeInvName(s))).toBe(normalizeInvName(s))
  })

  it('handles empty string', () => {
    expect(normalizeInvName('')).toBe('')
  })
})

describe('aggregateOutboundByName — Property 5', () => {
  it('totalAmount = sum of all credit_amount > 0 entries', () => {
    const entries: PostPeriodOutboundEntry[] = [
      { credit_amount: 100, aux_name: 'A' },
      { credit_amount: 200, aux_name: 'B' },
      { credit_amount: 50, aux_name: 'A' },
    ]
    const r = aggregateOutboundByName(entries)
    expect(r.totalAmount).toBe(350)
    expect(r.byName[normalizeInvName('A')].amount).toBe(150)
    expect(r.byName[normalizeInvName('B')].amount).toBe(200)
  })

  it('entries without name go to UNMATCHED_NAME bucket', () => {
    const entries: PostPeriodOutboundEntry[] = [
      { credit_amount: 300 }, // no name fields
      { credit_amount: 100, aux_name: 'X' },
    ]
    const r = aggregateOutboundByName(entries)
    expect(r.byName[UNMATCHED_NAME].amount).toBe(300)
    expect(r.unmatchedCount).toBe(1)
    expect(r.totalAmount).toBe(400)
  })

  it('skips entries with credit_amount <= 0', () => {
    const entries: PostPeriodOutboundEntry[] = [
      { credit_amount: -50, aux_name: 'A' },
      { credit_amount: 0, aux_name: 'B' },
      { credit_amount: 200, aux_name: 'C' },
    ]
    const r = aggregateOutboundByName(entries)
    expect(r.totalAmount).toBe(200)
    expect(Object.keys(r.byName)).toHaveLength(1)
  })

  it('empty/non-array returns zero totalAmount', () => {
    expect(aggregateOutboundByName([] as any).totalAmount).toBe(0)
    expect(aggregateOutboundByName(null as any).totalAmount).toBe(0)
  })

  it('qty is aggregated per name', () => {
    const entries: PostPeriodOutboundEntry[] = [
      { credit_amount: 100, aux_name: 'W', credit_quantity: 10 } as any,
      { credit_amount: 200, aux_name: 'W', credit_quantity: 20 } as any,
    ]
    const r = aggregateOutboundByName(entries)
    expect(r.byName[normalizeInvName('W')].qty).toBe(30)
    expect(r.totalQty).toBe(30)
  })
})

describe('pullPostPeriodOutbound — graceful degradation', () => {
  it('error when projectId missing', async () => {
    const r = await pullPostPeriodOutbound('', 2025, '1405')
    expect(r.status).toBe('error')
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('error when accountCode missing', async () => {
    const r = await pullPostPeriodOutbound('p1', 2025, '')
    expect(r.status).toBe('error')
  })

  it('error when year invalid', async () => {
    const r = await pullPostPeriodOutbound('p1', NaN, '1405')
    expect(r.status).toBe('error')
  })

  it('empty when HTTP returns no items', async () => {
    mockFetchOk([])
    const r = await pullPostPeriodOutbound('p1', 2025, '1405')
    expect(r.status).toBe('empty')
    expect(r.totalAmount).toBe(0)
  })

  it('ok with aggregated results', async () => {
    mockFetchOk([
      { credit_amount: 500, aux_name: '甲材料' },
      { credit_amount: 300, aux_name: '甲材料' },
      { credit_amount: 200, aux_name: '乙材料' },
    ])
    const r = await pullPostPeriodOutbound('p1', 2025, '1405')
    expect(r.status).toBe('ok')
    expect(r.totalAmount).toBe(1000)
    expect(Object.keys(r.byName)).toHaveLength(2)
  })

  it('empty when HTTP not ok (no throw)', async () => {
    mockFetchNotOk()
    const r = await pullPostPeriodOutbound('p1', 2025, '1405')
    expect(r.status).toBe('empty')
    expect(r.totalAmount).toBe(0)
  })

  it('error on fetch rejection (no throw)', async () => {
    mockFetchReject('network')
    const r = await pullPostPeriodOutbound('p1', 2025, '1405')
    expect(r.status).toBe('error')
    expect(r.totalAmount).toBe(0)
  })

  it('uses next year (bsYear+1) in URL', async () => {
    mockFetchOk([])
    await pullPostPeriodOutbound('p1', 2025, '1405')
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('year=2026'),
      expect.anything(),
    )
    expect(globalThis.fetch).toHaveBeenCalledWith(
      expect.stringContaining('date_from=2026-01-01'),
      expect.anything(),
    )
  })
})
