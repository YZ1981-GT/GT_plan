import { describe, it, expect } from 'vitest'
import { buildH3MortgageReconcile } from '../h3MortgageReconcile'

describe('buildH3MortgageReconcile', () => {
  // P5: 抵押差额 = h3RestrictedTotal - (l1 + l3)
  it('P5: diff = h3 - (L1 + L3), within tolerance → ok', () => {
    const result = buildH3MortgageReconcile(5000, 3000, 2000)
    expect(result.diff).toBe(0)
    expect(result.lTotal).toBe(5000)
    expect(result.status).toBe('ok')
  })

  it('P5: diff exceeds tolerance → warning', () => {
    const result = buildH3MortgageReconcile(5000, 3000, 1000)
    expect(result.diff).toBe(1000) // 5000 - 4000
    expect(result.status).toBe('warning')
  })

  it('P5: small diff within tolerance (1 yuan) → ok', () => {
    const result = buildH3MortgageReconcile(5000.5, 3000, 2000)
    expect(result.diff).toBeCloseTo(0.5)
    expect(result.status).toBe('ok')
  })

  // P6: pull 失败 → status unavailable
  it('P6: both L1 and L3 null → status unavailable, diff null', () => {
    const result = buildH3MortgageReconcile(5000, null, null)
    expect(result.status).toBe('unavailable')
    expect(result.diff).toBeNull()
    expect(result.lTotal).toBeNull()
    expect(result.h3RestrictedTotal).toBe(5000)
  })

  // P7: 空数据（一方为null一方有值）
  it('P7: L1 null + L3 has value → uses L3 only', () => {
    const result = buildH3MortgageReconcile(5000, null, 4000)
    expect(result.lTotal).toBe(4000)
    expect(result.diff).toBe(1000)
    expect(result.status).toBe('warning')
  })

  it('P7: L1 has value + L3 null → uses L1 only', () => {
    const result = buildH3MortgageReconcile(3000, 3000, null)
    expect(result.lTotal).toBe(3000)
    expect(result.diff).toBe(0)
    expect(result.status).toBe('ok')
  })

  // H3 无抵押(0) + L 无数据 → 两者都0不告警
  it('both zero → ok (no mortgage on either side)', () => {
    const result = buildH3MortgageReconcile(0, 0, 0)
    expect(result.diff).toBe(0)
    expect(result.status).toBe('ok')
  })
})
