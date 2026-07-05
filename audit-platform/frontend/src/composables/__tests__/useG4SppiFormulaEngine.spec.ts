/**
 * Unit Tests — G4 债权投资(SPPI组) 公式引擎
 *
 * Spec: .kiro/specs/g4-bond-investment-sppi/ Task 2.1
 * Requirements: 6.1~6.10
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  determineBusinessModel,
  determineSPPIConclusion,
  calcInventoryTotal,
  calcReportDateQuantity,
  calcReportDateTotal,
  calcReconciliationVariance,
  isReconciliationBalanced,
  calcSumColumn,
  determineFinalClassification,
  FINAL_CLASSIFICATION_LABELS,
} from '../useG4SppiFormulaEngine'

// ═══════════════════════════════════════════════════════════════════
// parseNum
// ═══════════════════════════════════════════════════════════════════

describe('parseNum', () => {
  it('returns 0 for null', () => {
    expect(parseNum(null)).toBe(0)
  })

  it('returns 0 for undefined', () => {
    expect(parseNum(undefined)).toBe(0)
  })

  it('returns 0 for empty string', () => {
    expect(parseNum('')).toBe(0)
  })

  it('returns 0 for NaN', () => {
    expect(parseNum(NaN)).toBe(0)
  })

  it('returns 0 for non-numeric strings', () => {
    expect(parseNum('abc')).toBe(0)
    expect(parseNum('  ')).toBe(0)
  })

  it('returns 0 for Infinity', () => {
    expect(parseNum(Infinity)).toBe(0)
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('returns the number for valid numbers', () => {
    expect(parseNum(42)).toBe(42)
    expect(parseNum(3.14)).toBe(3.14)
    expect(parseNum(-100)).toBe(-100)
    expect(parseNum(0)).toBe(0)
  })

  it('parses numeric strings', () => {
    expect(parseNum('123')).toBe(123)
    expect(parseNum('3.14')).toBe(3.14)
  })
})

// ═══════════════════════════════════════════════════════════════════
// determineBusinessModel
// ═══════════════════════════════════════════════════════════════════

describe('determineBusinessModel', () => {
  it('returns INCOMPLETE when any answer is null', () => {
    expect(determineBusinessModel({ q1: null, q2: false, q3: false, q4: false, q5: false })).toBe('INCOMPLETE')
    expect(determineBusinessModel({ q1: true, q2: null, q3: false, q4: false, q5: false })).toBe('INCOMPLETE')
    expect(determineBusinessModel({ q1: true, q2: false, q3: null, q4: false, q5: false })).toBe('INCOMPLETE')
  })

  it('returns FVTPL when q5=true (持有以获取公允价值变动)', () => {
    expect(determineBusinessModel({ q1: true, q2: false, q3: false, q4: false, q5: true })).toBe('FVTPL')
    expect(determineBusinessModel({ q1: false, q2: false, q3: false, q4: false, q5: true })).toBe('FVTPL')
  })

  it('returns FVTPL when q3=true (出售频繁且金额重大)', () => {
    expect(determineBusinessModel({ q1: true, q2: true, q3: true, q4: false, q5: false })).toBe('FVTPL')
    expect(determineBusinessModel({ q1: false, q2: false, q3: true, q4: false, q5: false })).toBe('FVTPL')
  })

  it('returns FVOCI when q4=true (同时以收取现金流和出售为目标)', () => {
    expect(determineBusinessModel({ q1: true, q2: false, q3: false, q4: true, q5: false })).toBe('FVOCI')
    expect(determineBusinessModel({ q1: false, q2: true, q3: false, q4: true, q5: false })).toBe('FVOCI')
  })

  it('returns AC when q1=true && q2=false (以收取合同现金流量为目标，无出售活动)', () => {
    expect(determineBusinessModel({ q1: true, q2: false, q3: false, q4: false, q5: false })).toBe('AC')
  })

  it('returns FVTPL for fallback case (all false)', () => {
    expect(determineBusinessModel({ q1: false, q2: false, q3: false, q4: false, q5: false })).toBe('FVTPL')
  })

  it('returns FVTPL when q1=true but q2=true (有出售活动)', () => {
    expect(determineBusinessModel({ q1: true, q2: true, q3: false, q4: false, q5: false })).toBe('FVTPL')
  })

  it('priority: q5 > q3 > q4 > AC check', () => {
    // q5 takes precedence over q3
    expect(determineBusinessModel({ q1: true, q2: true, q3: true, q4: true, q5: true })).toBe('FVTPL')
    // q3 takes precedence over q4
    expect(determineBusinessModel({ q1: true, q2: true, q3: true, q4: true, q5: false })).toBe('FVTPL')
    // q4 takes precedence over AC
    expect(determineBusinessModel({ q1: true, q2: false, q3: false, q4: true, q5: false })).toBe('FVOCI')
  })
})

// ═══════════════════════════════════════════════════════════════════
// determineSPPIConclusion
// ═══════════════════════════════════════════════════════════════════

describe('determineSPPIConclusion', () => {
  it('returns PASS when all false', () => {
    expect(determineSPPIConclusion(false, false, false, false)).toBe('PASS')
  })

  it('returns FAIL when hasEquityConversion=true', () => {
    expect(determineSPPIConclusion(false, false, true, false)).toBe('FAIL')
    expect(determineSPPIConclusion(true, true, true, false)).toBe('FAIL')
  })

  it('returns FAIL when hasLeverage=true', () => {
    expect(determineSPPIConclusion(false, false, false, true)).toBe('FAIL')
    expect(determineSPPIConclusion(true, true, false, true)).toBe('FAIL')
  })

  it('returns FURTHER_ANALYSIS when only earlyRedemption=true', () => {
    expect(determineSPPIConclusion(true, false, false, false)).toBe('FURTHER_ANALYSIS')
  })

  it('returns FURTHER_ANALYSIS when only extension=true', () => {
    expect(determineSPPIConclusion(false, true, false, false)).toBe('FURTHER_ANALYSIS')
  })

  it('returns FURTHER_ANALYSIS when both earlyRedemption and extension=true', () => {
    expect(determineSPPIConclusion(true, true, false, false)).toBe('FURTHER_ANALYSIS')
  })

  it('FAIL overrides FURTHER_ANALYSIS', () => {
    expect(determineSPPIConclusion(true, true, true, false)).toBe('FAIL')
    expect(determineSPPIConclusion(true, false, false, true)).toBe('FAIL')
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcInventoryTotal
// ═══════════════════════════════════════════════════════════════════

describe('calcInventoryTotal', () => {
  it('computes faceValue * quantity with 2dp', () => {
    expect(calcInventoryTotal(100, 10)).toBe(1000)
    expect(calcInventoryTotal(99.99, 3)).toBe(299.97)
    expect(calcInventoryTotal(0, 100)).toBe(0)
  })

  it('rounds to 2 decimal places', () => {
    // 33.333 * 3 = 99.999, round(99.999*100)/100 = round(9999.9)/100 = 10000/100 = 100.00
    expect(calcInventoryTotal(33.333, 3)).toBe(100)
    // 1.005 * 2 = 2.01, round(2.01*100)/100 = 201/100 = 2.01
    expect(calcInventoryTotal(1.005, 2)).toBe(2.01)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcReportDateQuantity
// ═══════════════════════════════════════════════════════════════════

describe('calcReportDateQuantity', () => {
  it('adds countDateQty + change', () => {
    expect(calcReportDateQuantity(100, 10)).toBe(110)
    expect(calcReportDateQuantity(100, -10)).toBe(90)
    expect(calcReportDateQuantity(0, 0)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcReportDateTotal
// ═══════════════════════════════════════════════════════════════════

describe('calcReportDateTotal', () => {
  it('computes faceValue * quantity with 2dp', () => {
    expect(calcReportDateTotal(100, 5)).toBe(500)
    expect(calcReportDateTotal(1.5, 3)).toBe(4.5)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcReconciliationVariance
// ═══════════════════════════════════════════════════════════════════

describe('calcReconciliationVariance', () => {
  it('computes reportDateTotal - bookTotal with 2dp', () => {
    expect(calcReconciliationVariance(1000, 1000)).toBe(0)
    expect(calcReconciliationVariance(1000, 999)).toBe(1)
    expect(calcReconciliationVariance(999, 1000)).toBe(-1)
    expect(calcReconciliationVariance(100.50, 100)).toBe(0.5)
  })
})

// ═══════════════════════════════════════════════════════════════════
// isReconciliationBalanced
// ═══════════════════════════════════════════════════════════════════

describe('isReconciliationBalanced', () => {
  it('returns true when |difference| < 0.01', () => {
    expect(isReconciliationBalanced(1000, 1000)).toBe(true)
    expect(isReconciliationBalanced(1000, 1000.005)).toBe(true)
  })

  it('returns false when |difference| >= 0.01', () => {
    expect(isReconciliationBalanced(1000, 999)).toBe(false)
    expect(isReconciliationBalanced(1000, 1000.02)).toBe(false)
    expect(isReconciliationBalanced(100, 100.1)).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcSumColumn
// ═══════════════════════════════════════════════════════════════════

describe('calcSumColumn', () => {
  it('sums array elements', () => {
    expect(calcSumColumn([1, 2, 3, 4, 5])).toBe(15)
    expect(calcSumColumn([100, -50, 25])).toBe(75)
  })

  it('returns 0 for empty array', () => {
    expect(calcSumColumn([])).toBe(0)
  })

  it('handles null/undefined in array via parseNum', () => {
    expect(calcSumColumn([1, 2, null as any, 3])).toBe(6)
  })
})

// ═══════════════════════════════════════════════════════════════════
// determineFinalClassification
// ═══════════════════════════════════════════════════════════════════

describe('determineFinalClassification', () => {
  it('FAIL → always FVTPL regardless of business model', () => {
    expect(determineFinalClassification('AC', 'FAIL')).toBe(FINAL_CLASSIFICATION_LABELS.FVTPL)
    expect(determineFinalClassification('FVOCI', 'FAIL')).toBe(FINAL_CLASSIFICATION_LABELS.FVTPL)
    expect(determineFinalClassification('FVTPL', 'FAIL')).toBe(FINAL_CLASSIFICATION_LABELS.FVTPL)
  })

  it('AC + PASS → 以摊余成本计量的金融资产', () => {
    expect(determineFinalClassification('AC', 'PASS')).toBe('以摊余成本计量的金融资产')
  })

  it('FVOCI + PASS → 以公允价值计量且其变动计入其他综合收益的金融资产', () => {
    expect(determineFinalClassification('FVOCI', 'PASS')).toBe('以公允价值计量且其变动计入其他综合收益的金融资产')
  })

  it('FVTPL + PASS → FVTPL classification', () => {
    expect(determineFinalClassification('FVTPL', 'PASS')).toBe(FINAL_CLASSIFICATION_LABELS.FVTPL)
  })

  it('any + FURTHER_ANALYSIS → FVTPL', () => {
    expect(determineFinalClassification('AC', 'FURTHER_ANALYSIS')).toBe(FINAL_CLASSIFICATION_LABELS.FVTPL)
    expect(determineFinalClassification('FVOCI', 'FURTHER_ANALYSIS')).toBe(FINAL_CLASSIFICATION_LABELS.FVTPL)
    expect(determineFinalClassification('FVTPL', 'FURTHER_ANALYSIS')).toBe(FINAL_CLASSIFICATION_LABELS.FVTPL)
  })
})
