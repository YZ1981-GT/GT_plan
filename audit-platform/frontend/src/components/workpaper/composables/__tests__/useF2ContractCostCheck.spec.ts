import { describe, it, expect } from 'vitest'
import { calcSubtotal, calcImpairment, isLossContract } from '../useF2SpecialFormulaEngine'

describe('F2-56 contract check coverage logic', () => {
  it('coverage = checked / population × 100', () => {
    const checked = calcSubtotal([100, 200, 50])
    const population = 1000
    expect((checked / population) * 100).toBe(35)
  })
})

describe('contract impairment/loss formulas', () => {
  it('impairment non-negative', () => {
    expect(calcImpairment(500, 300)).toBe(200)
    expect(calcImpairment(100, 200)).toBe(0)
  })

  it('loss contract', () => {
    expect(isLossContract(1000, 1200)).toBe(true)
  })
})
