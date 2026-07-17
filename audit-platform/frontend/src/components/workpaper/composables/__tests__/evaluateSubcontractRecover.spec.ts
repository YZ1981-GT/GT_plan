/**
 * evaluateSubcontractRecover 契约（F2-35 委托加工计价勾稽）。
 * 锁定：收回≈发出+加工费；未收回/计价差异/待填 状态正确。
 */
import { describe, it, expect } from 'vitest'
import { evaluateSubcontractRecover } from '../useF2InspectionCheckFormulas'

describe('evaluateSubcontractRecover', () => {
  it('收回 = 发出 + 加工费 → ok', () => {
    const c = evaluateSubcontractRecover({ issueCost: 1000, fee: 200, recoverCost: 1200 })
    expect(c.status).toBe('ok')
    expect(c.expected).toBe(1200)
    expect(c.variance).toBe(0)
  })

  it('未发出（issueCost=0）→ pending', () => {
    expect(evaluateSubcontractRecover({ issueCost: 0, fee: 0, recoverCost: 0 }).status).toBe('pending')
  })

  it('收回 < 发出 → unrecovered', () => {
    const c = evaluateSubcontractRecover({ issueCost: 1000, fee: 200, recoverCost: 600 })
    expect(c.status).toBe('unrecovered')
  })

  it('收回=0 但已发出 → unrecovered', () => {
    expect(evaluateSubcontractRecover({ issueCost: 1000, fee: 200, recoverCost: 0 }).status).toBe('unrecovered')
  })

  it('收回 ≥ 发出但 ≠ 发出+加工费 → valuation', () => {
    // 收回 1000 = 发出 1000，但未含加工费 200 → 应为 1200
    const c = evaluateSubcontractRecover({ issueCost: 1000, fee: 200, recoverCost: 1000 })
    expect(c.status).toBe('valuation')
    expect(c.expected).toBe(1200)
    expect(c.variance).toBe(-200)
  })

  it('收回多含（>发出+加工费）→ valuation 正差异', () => {
    const c = evaluateSubcontractRecover({ issueCost: 1000, fee: 200, recoverCost: 1350 })
    expect(c.status).toBe('valuation')
    expect(c.variance).toBe(150)
  })

  it('容差内（差≤0.01）→ ok', () => {
    const c = evaluateSubcontractRecover({ issueCost: 1000, fee: 200.005, recoverCost: 1200.01 })
    expect(c.status).toBe('ok')
  })
})
