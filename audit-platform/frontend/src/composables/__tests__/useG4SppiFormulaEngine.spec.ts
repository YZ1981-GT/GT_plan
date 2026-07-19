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
  detectBusinessModelInconsistencies,
  determineSPPIConclusion,
  calcInventoryTotal,
  calcReportDateQuantity,
  calcReportDateTotal,
  calcReconciliationVariance,
  calcQuantityVariance,
  isReconciliationBalanced,
  isReconciliationFullyBalanced,
  calcSumColumn,
  determineFinalClassification,
  FINAL_CLASSIFICATION_LABELS,
} from '../useG4SppiFormulaEngine'

function allNo(overrides: Partial<Parameters<typeof determineBusinessModel>[0]> = {}) {
  return {
    q1: false,
    q2: false,
    q2_1: false,
    q2_2: false,
    q2_3: false,
    q3: false,
    q4: false,
    q5: false,
    ...overrides,
  }
}

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

describe('determineBusinessModel (Excel 否定筛查)', () => {
  it('returns INCOMPLETE when any answer is null', () => {
    expect(determineBusinessModel(allNo({ q1: null }))).toBe('INCOMPLETE')
    expect(determineBusinessModel(allNo({ q2_1: null }))).toBe('INCOMPLETE')
    expect(determineBusinessModel(allNo({ q5: null }))).toBe('INCOMPLETE')
  })

  it('returns AC when all 否', () => {
    expect(determineBusinessModel(allNo())).toBe('AC')
  })

  it('returns FVTPL when trading flags true (q2 / q2_* / q5)', () => {
    expect(determineBusinessModel(allNo({ q2: true }))).toBe('FVTPL')
    expect(determineBusinessModel(allNo({ q2_1: true }))).toBe('FVTPL')
    expect(determineBusinessModel(allNo({ q2_3: true }))).toBe('FVTPL')
    expect(determineBusinessModel(allNo({ q5: true }))).toBe('FVTPL')
  })

  it('returns FVTPL when q3=true (基于公允价值管理)', () => {
    expect(determineBusinessModel(allNo({ q3: true }))).toBe('FVTPL')
  })

  it('returns FVOCI when q1 or q4 true (大额频繁出售)', () => {
    expect(determineBusinessModel(allNo({ q1: true }))).toBe('FVOCI')
    expect(determineBusinessModel(allNo({ q4: true }))).toBe('FVOCI')
  })

  it('priority aligns Excel A23 then CAS q3-only', () => {
    // Excel step1：q1=是 + 非交易 + 非FV → 直接 FVOCI（不再看题5）
    expect(determineBusinessModel(allNo({ q1: true, q5: true }))).toBe('FVOCI')
    // Excel step2：q1=是 + FV管理 → 其他
    expect(determineBusinessModel(allNo({ q1: true, q3: true }))).toBe('FVTPL')
    // Excel：q4=是 且 q5≠是 → 收取+出售（即使题3=是，先走未来出售分支）
    expect(determineBusinessModel(allNo({ q3: true, q4: true }))).toBe('FVOCI')
    // 仅未来交易性
    expect(determineBusinessModel(allNo({ q5: true }))).toBe('FVTPL')
    expect(determineBusinessModel(allNo({ q1: true, q4: true }))).toBe('FVOCI')
  })
})

describe('detectBusinessModelInconsistencies', () => {
  it('flags q2 vs children mismatch and q3-only CAS note', () => {
    expect(
      detectBusinessModelInconsistencies(allNo({ q2: true, q2_1: false, q2_2: false, q2_3: false })),
    ).toEqual(expect.arrayContaining([expect.stringContaining('题2勾选「是」')]))
    expect(
      detectBusinessModelInconsistencies(allNo({ q3: true })),
    ).toEqual(expect.arrayContaining([expect.stringContaining('CAS22')]))
  })
})

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

describe('calcInventoryTotal', () => {
  it('computes faceValue * quantity with 2dp', () => {
    expect(calcInventoryTotal(100, 10)).toBe(1000)
    expect(calcInventoryTotal(99.99, 3)).toBe(299.97)
    expect(calcInventoryTotal(0, 100)).toBe(0)
  })

  it('rounds to 2 decimal places', () => {
    expect(calcInventoryTotal(33.333, 3)).toBe(100)
    expect(calcInventoryTotal(1.005, 2)).toBe(2.01)
  })
})

describe('calcReportDateQuantity', () => {
  it('报表日 = 盘点日 − 增加 + 减少', () => {
    expect(calcReportDateQuantity(1000, 100, 20)).toBe(920)
    expect(calcReportDateQuantity(100, 0, 0)).toBe(100)
    expect(calcReportDateQuantity(500, 50, 50)).toBe(500)
  })

  it('双参数兼容：报表日 = 盘点日 − 净增加', () => {
    expect(calcReportDateQuantity(1000, 80)).toBe(920)
    expect(calcReportDateQuantity(100, -10)).toBe(110)
    expect(calcReportDateQuantity(0, 0)).toBe(0)
  })
})

describe('calcReportDateTotal', () => {
  it('computes faceValue * quantity with 2dp', () => {
    expect(calcReportDateTotal(100, 5)).toBe(500)
    expect(calcReportDateTotal(1.5, 3)).toBe(4.5)
  })
})

describe('calcReconciliationVariance', () => {
  it('computes reportDateTotal - bookTotal with 2dp', () => {
    expect(calcReconciliationVariance(1000, 1000)).toBe(0)
    expect(calcReconciliationVariance(1000, 999)).toBe(1)
    expect(calcReconciliationVariance(999, 1000)).toBe(-1)
    expect(calcReconciliationVariance(100.50, 100)).toBe(0.5)
  })
})

describe('calcQuantityVariance', () => {
  it('computes reportQuantity - bookQuantity', () => {
    expect(calcQuantityVariance(100, 100)).toBe(0)
    expect(calcQuantityVariance(100, 95)).toBe(5)
    expect(calcQuantityVariance(90, 100)).toBe(-10)
  })
})

describe('isReconciliationFullyBalanced', () => {
  it('requires both quantity and amount within tolerance', () => {
    expect(isReconciliationFullyBalanced(100, 100, 1000, 1000)).toBe(true)
    expect(isReconciliationFullyBalanced(100, 99, 1000, 1000)).toBe(false)
    expect(isReconciliationFullyBalanced(100, 100, 1000, 999)).toBe(false)
  })
})

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
