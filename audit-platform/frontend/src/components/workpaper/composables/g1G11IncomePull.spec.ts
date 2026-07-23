import { describe, it, expect } from 'vitest'
import { buildG1G11Reconcile } from './g1G11IncomePull'

describe('buildG1G11Reconcile', () => {
  it('合计 = 利息 + 股利 + 处置，差异 = 合计 - G11审定', () => {
    const r = buildG1G11Reconcile({
      g1InterestTotal: 100,
      g1DividendTotal: 50,
      g1DisposalTotal: 30,
      g11Audited: 180,
      g11Source: 'audited',
    })
    expect(r.g1Total).toBe(180)
    expect(r.difference).toBe(0)
    expect(r.isConsistent).toBe(true)
  })

  it('差异绝对值 < 1 视为一致', () => {
    const r = buildG1G11Reconcile({
      g1InterestTotal: 100.4,
      g1DividendTotal: 0,
      g1DisposalTotal: 0,
      g11Audited: 100,
      g11Source: 'audited',
    })
    expect(r.isConsistent).toBe(true)
  })

  it('差异 >= 1 视为不一致', () => {
    const r = buildG1G11Reconcile({
      g1InterestTotal: 200,
      g1DividendTotal: 0,
      g1DisposalTotal: 0,
      g11Audited: 150,
      g11Source: 'audited',
    })
    expect(r.difference).toBe(50)
    expect(r.isConsistent).toBe(false)
  })

  it('透传 g11Source', () => {
    const r = buildG1G11Reconcile({
      g1InterestTotal: 0,
      g1DividendTotal: 0,
      g1DisposalTotal: 0,
      g11Audited: 0,
      g11Source: 'unavailable',
    })
    expect(r.g11Source).toBe('unavailable')
    expect(r.isConsistent).toBe(true) // 0 vs 0
  })
})
