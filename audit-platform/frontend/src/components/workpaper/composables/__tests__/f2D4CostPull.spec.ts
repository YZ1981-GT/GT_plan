/**
 * Task 3 — f2D4CostPull 单测
 *
 * 覆盖 Property 4：
 * - buildCostCarryforwardReconcile：matched ⟺ |diff| ≤ 容差；diff 符号正确；
 *   容差 = operatingCost×tolPct（operatingCost=0 → 绝对容差 1）。
 * - extractOperatingCost：取 6401 审定发生额（优先 audited，回退 借-贷）。
 * - pullOperatingCost：优雅降级（缺参 / 空数据 / 请求失败均不抛错）。
 *
 * fast-check numRuns=20；api 用 vi.mock。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as fc from 'fast-check'

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn() },
}))

import { api } from '@/services/apiProxy'
import {
  extractOperatingCost,
  buildCostCarryforwardReconcile,
  pullOperatingCost,
  OPERATING_COST_ACCOUNT,
} from '../f2D4CostPull'

const mockGet = vi.mocked(api.get)

beforeEach(() => {
  vi.clearAllMocks()
})

describe('extractOperatingCost', () => {
  it('prefers audited_amount for 6401', () => {
    const rows = [
      { account_code: '6001', audited_amount: 999 },
      { account_code: '6401', audited_amount: 1_200_000, debit_amount: 1, credit_amount: 2 },
    ]
    expect(extractOperatingCost(rows)).toBeCloseTo(1_200_000)
  })

  it('falls back to debit - credit when no audited field', () => {
    const rows = [{ accountCode: '6401', debit_amount: 800_000, credit_amount: 50_000 }]
    expect(extractOperatingCost(rows)).toBeCloseTo(750_000)
  })

  it('returns 0 when account missing / non-array', () => {
    expect(extractOperatingCost([{ account_code: '6001', audited_amount: 5 }])).toBe(0)
    expect(extractOperatingCost(null)).toBe(0)
    expect(extractOperatingCost('bad')).toBe(0)
  })

  it('respects custom account code', () => {
    expect(extractOperatingCost([{ account_code: '6402', audited_amount: 42 }], '6402')).toBe(42)
  })
})

describe('buildCostCarryforwardReconcile — Property 4', () => {
  it('matched ⟺ |diff| ≤ tolerance; diff sign & tolerance correct (fast-check)', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true }),
        fc.double({ min: 0, max: 1, noNaN: true }),
        (outbound, opCost, invBal, tolPct) => {
          const r = buildCostCarryforwardReconcile(outbound, opCost, invBal, tolPct)
          // diff = outbound − operatingCost（符号正确）
          expect(r.diff).toBeCloseTo(outbound - opCost, 4)
          // invBalance 回显
          expect(r.invBalance).toBeCloseTo(invBal, 4)
          // 容差 = 存货余额(invBalance)×tolPct，绝对下限 1（Req 3.3）
          const expectedTol = Math.max(Math.abs(invBal) * tolPct, 1)
          expect(r.tolerance).toBeCloseTo(expectedTol, 6)
          // matched ⟺ |diff| ≤ tolerance
          expect(r.matched).toBe(Math.abs(r.diff) <= r.tolerance)
        },
      ),
      { numRuns: 20 },
    )
  })

  it('diff sign: outbound > cost → positive; outbound < cost → negative', () => {
    expect(buildCostCarryforwardReconcile(1000, 600, 5000).diff).toBeCloseTo(400)
    expect(buildCostCarryforwardReconcile(600, 1000, 5000).diff).toBeCloseTo(-400)
  })

  it('tolerance floors at 1 when invBalance is 0', () => {
    const r = buildCostCarryforwardReconcile(0.5, 0, 0)
    expect(r.tolerance).toBe(1)
    expect(r.matched).toBe(true) // |0.5| ≤ 1
  })

  it('matched within invBalance×tolPct (Req 3.3)', () => {
    // invBalance=8,000,000, tolPct=5% → tolerance 400,000
    const within = buildCostCarryforwardReconcile(1_300_000, 1_000_000, 8_000_000, 0.05)
    expect(within.tolerance).toBeCloseTo(400_000)
    expect(within.diff).toBeCloseTo(300_000)
    expect(within.matched).toBe(true)

    const beyond = buildCostCarryforwardReconcile(1_500_000, 1_000_000, 8_000_000, 0.05)
    expect(beyond.diff).toBeCloseTo(500_000)
    expect(beyond.matched).toBe(false)
  })

  it('coerces invalid numbers to 0 (invBalance=0 → tolerance 1)', () => {
    const r = buildCostCarryforwardReconcile(NaN as any, undefined as any, NaN as any)
    expect(r.outboundTotal).toBe(0)
    expect(r.operatingCost).toBe(0)
    expect(r.invBalance).toBe(0)
    expect(r.tolerance).toBe(1)
    expect(r.matched).toBe(true)
  })
})

describe('pullOperatingCost — graceful degradation', () => {
  it('returns error when projectId missing', async () => {
    const r = await pullOperatingCost('', 2025)
    expect(r.status).toBe('error')
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('returns error when year invalid', async () => {
    const r = await pullOperatingCost('p1', 0)
    expect(r.status).toBe('error')
  })

  it('returns empty when no rows', async () => {
    mockGet.mockResolvedValueOnce({ items: [] })
    const r = await pullOperatingCost('p1', 2025)
    expect(r.status).toBe('empty')
    expect(r.operatingCost).toBe(0)
  })

  it('returns ok with audited cost', async () => {
    mockGet.mockResolvedValueOnce({ items: [{ account_code: OPERATING_COST_ACCOUNT, audited_amount: 3_000_000 }] })
    const r = await pullOperatingCost('p1', 2025)
    expect(r.status).toBe('ok')
    expect(r.operatingCost).toBeCloseTo(3_000_000)
  })

  it('returns error on request failure (no throw)', async () => {
    mockGet.mockRejectedValueOnce(new Error('boom'))
    const r = await pullOperatingCost('p1', 2025)
    expect(r.status).toBe('error')
    expect(r.operatingCost).toBe(0)
  })
})
