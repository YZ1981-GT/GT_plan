/**
 * Unit Tests — J2 公式引擎 + 精算引擎
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/ Tasks 7.1
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
  calcProportion,
} from '../useJ2FormulaEngine'
import {
  calcEndDBO,
  calcInterestCost,
  calcNetLiability,
  calcActuarialGainLoss,
  validateAssumptions,
  calcSensitivity,
} from '../useJ2ActuarialEngine'

// ═══════════════════════════════════════════════════════════════════
// useJ2FormulaEngine
// ═══════════════════════════════════════════════════════════════════

describe('useJ2FormulaEngine', () => {
  describe('parseNum', () => {
    it('parses numbers correctly', () => {
      expect(parseNum(123)).toBe(123)
      expect(parseNum('456.78')).toBe(456.78)
      expect(parseNum(null)).toBe(0)
      expect(parseNum(undefined)).toBe(0)
      expect(parseNum('')).toBe(0)
      expect(parseNum(NaN)).toBe(0)
      expect(parseNum(Infinity)).toBe(0)
    })
  })

  describe('calcAuditedAmount', () => {
    it('returns sum of three components', () => {
      expect(calcAuditedAmount(100, 20, 5)).toBe(125)
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
      expect(calcAuditedAmount(1000, -50, 30)).toBe(980)
    })
  })

  describe('calcLiabilityEndBalance (负债类贷方！)', () => {
    it('computes end = begin + credit - debit', () => {
      expect(calcLiabilityEndBalance(1000, 200, 50)).toBe(1150)
      expect(calcLiabilityEndBalance(0, 500, 300)).toBe(200)
      expect(calcLiabilityEndBalance(1000, 0, 1000)).toBe(0)
    })

    it('can go negative (over-paid)', () => {
      expect(calcLiabilityEndBalance(100, 0, 200)).toBe(-100)
    })
  })

  describe('calcChangeAmount', () => {
    it('returns current - prior', () => {
      expect(calcChangeAmount(150, 100)).toBe(50)
      expect(calcChangeAmount(80, 100)).toBe(-20)
    })
  })

  describe('calcChangeRate', () => {
    it('returns rate as decimal', () => {
      expect(calcChangeRate(100, 150)).toBeCloseTo(0.5)
      expect(calcChangeRate(200, 100)).toBeCloseTo(-0.5)
    })
    it('handles zero base', () => {
      expect(calcChangeRate(0, 0)).toBe(0)
      expect(calcChangeRate(0, 100)).toBe(1)
    })
  })

  describe('calcSubtotal', () => {
    it('sums array', () => {
      expect(calcSubtotal([100, 200, 300])).toBe(600)
      expect(calcSubtotal([])).toBe(0)
      expect(calcSubtotal([0, 0, 0])).toBe(0)
    })
  })

  describe('calcProportion', () => {
    it('returns ratio', () => {
      expect(calcProportion(250, 1000)).toBeCloseTo(0.25)
    })
    it('handles zero total', () => {
      expect(calcProportion(100, 0)).toBe(0)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════
// useJ2ActuarialEngine
// ═══════════════════════════════════════════════════════════════════

describe('useJ2ActuarialEngine', () => {
  describe('calcEndDBO', () => {
    it('computes DBO end with six elements', () => {
      // 1000 + 50 + 40 + 20 - 10 - 30 = 1070
      expect(calcEndDBO(1000, 50, 40, 20, 10, 30)).toBe(1070)
    })
    it('returns begin when all zero', () => {
      expect(calcEndDBO(5000, 0, 0, 0, 0, 0)).toBe(5000)
    })
  })

  describe('calcInterestCost', () => {
    it('computes interest = DBO × rate', () => {
      expect(calcInterestCost(10000, 0.04)).toBeCloseTo(400)
      expect(calcInterestCost(50000, 0.05)).toBeCloseTo(2500)
    })
    it('returns 0 when DBO is 0', () => {
      expect(calcInterestCost(0, 0.04)).toBe(0)
    })
  })

  describe('calcNetLiability', () => {
    it('computes net = DBO - plan assets', () => {
      expect(calcNetLiability(10000, 3000)).toBe(7000)
      expect(calcNetLiability(5000, 8000)).toBe(-3000) // 净资产
    })
  })

  describe('calcActuarialGainLoss', () => {
    it('positive = loss (actual > expected)', () => {
      expect(calcActuarialGainLoss(11000, 10000)).toBe(1000)
    })
    it('negative = gain (actual < expected)', () => {
      expect(calcActuarialGainLoss(9000, 10000)).toBe(-1000)
    })
  })

  describe('validateAssumptions', () => {
    it('valid assumptions pass', () => {
      const result = validateAssumptions({
        discountRate: 0.04,
        salaryGrowthRate: 0.08,
        mortalityRate: 0.005,
        turnoverRate: 0.10,
      })
      expect(result.isValid).toBe(true)
    })

    it('invalid discount rate fails', () => {
      const result = validateAssumptions({
        discountRate: 0,
        salaryGrowthRate: 0.08,
        mortalityRate: 0.005,
        turnoverRate: 0.10,
      })
      expect(result.isValid).toBe(false)
      expect(result.warnings.length).toBeGreaterThan(0)
    })

    it('extreme values produce warnings', () => {
      const result = validateAssumptions({
        discountRate: 0.01,  // below 2% = warning
        salaryGrowthRate: 0.20, // above 15% = warning
        mortalityRate: 0.001,
        turnoverRate: 0.35,   // above 30% = warning
      })
      expect(result.isValid).toBe(true)  // still valid, just warnings
      expect(result.warnings.length).toBeGreaterThan(0)
    })
  })

  describe('calcSensitivity', () => {
    it('computes sensitivity correctly', () => {
      const result = calcSensitivity(10000, 10, 0.005)
      // increase: -10000 * 10 * 0.005 = -500
      expect(result.increaseImpact).toBeCloseTo(-500)
      // decrease: +500
      expect(result.decreaseImpact).toBeCloseTo(500)
      expect(result.increasedValue).toBeCloseTo(9500)
      expect(result.decreasedValue).toBeCloseTo(10500)
    })
  })
})
