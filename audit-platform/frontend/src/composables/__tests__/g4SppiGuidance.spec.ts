/**
 * g4SppiGuidance + SPPI×业务模式勾稽 + 基准测试/自动规则 单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  ENRICHED_METHODOLOGY_MAP,
  BOND_JUDGMENT_LOGIC_TABLE,
  SPPI_BOTTOM_TIPS,
  SPPI_AUDIT_PROCEDURES,
} from '../g4SppiGuidance'
import {
  determineFinalClassification,
  determineSPPIConclusion,
  suggestAbsSppiByTranche,
  suggestFinancialStep1Conclusion,
  suggestFinancialStep2Conclusion,
  calcBenchmarkPeriodDiff,
  calcBenchmarkDiffRate,
  isBenchmarkDiffMaterial,
  determineBenchmarkSppiConclusion,
} from '../useG4SppiFormulaEngine'

describe('g4SppiGuidance', () => {
  it('方法论映射覆盖 7 种分析项目', () => {
    const keys = [
      'simple', 'floating_rate', 'rate_adjustment',
      'prepayment', 'extension', 'non_recourse', 'linked_instrument',
    ]
    for (const k of keys) {
      expect(ENRICHED_METHODOLOGY_MAP[k]).toBeTruthy()
      expect(ENRICHED_METHODOLOGY_MAP[k].length).toBeGreaterThan(20)
    }
  })

  it('判断逻辑对照表与底部提示非空', () => {
    expect(BOND_JUDGMENT_LOGIC_TABLE.length).toBe(7)
    expect(SPPI_BOTTOM_TIPS.length).toBe(6)
    expect(SPPI_AUDIT_PROCEDURES.length).toBeGreaterThanOrEqual(5)
  })
})

describe('G4-6 × G4-5 综合分类', () => {
  it('任一 SPPI 失败 → FVTPL（无论业务模式）', () => {
    expect(determineFinalClassification('AC', 'FAIL')).toContain('公允价值')
    expect(determineFinalClassification('FVOCI', 'FAIL')).toContain('公允价值')
  })

  it('SPPI 通过 + AC 业务模式 → 摊余成本', () => {
    expect(determineFinalClassification('AC', 'PASS')).toContain('摊余成本')
  })

  it('权益转换/杠杆必失败', () => {
    expect(determineSPPIConclusion(false, false, true, false)).toBe('FAIL')
    expect(determineSPPIConclusion(false, false, false, true)).toBe('FAIL')
  })
})

describe('ABS / 理财自动规则', () => {
  it('ABS 次级 → FAIL，优先级 → PASS', () => {
    expect(suggestAbsSppiByTranche('次级')).toBe('FAIL')
    expect(suggestAbsSppiByTranche('优先A')).toBe('PASS')
    expect(suggestAbsSppiByTranche('中间级')).toBeNull()
  })

  it('理财第一步：不保本 FAIL；保本固定 PASS；有浮动待定', () => {
    expect(suggestFinancialStep1Conclusion({
      guaranteesPrincipal: false, hasFixedReturn: true, hasFloatingReturn: false,
    })).toBe('FAIL')
    expect(suggestFinancialStep1Conclusion({
      guaranteesPrincipal: true, hasFixedReturn: true, hasFloatingReturn: false,
    })).toBe('PASS')
    expect(suggestFinancialStep1Conclusion({
      guaranteesPrincipal: true, hasFixedReturn: true, hasFloatingReturn: true,
    })).toBeNull()
  })

  it('理财第二步：不现实→PASS，现实→FAIL', () => {
    expect(suggestFinancialStep2Conclusion(true)).toBe('PASS')
    expect(suggestFinancialStep2Conclusion(false)).toBe('FAIL')
  })
})

describe('基准测试公式', () => {
  it('期差与差异率', () => {
    expect(calcBenchmarkPeriodDiff(110, 100)).toBe(10)
    const rate = calcBenchmarkDiffRate([
      { period: 1, contractCf: 110, benchmarkCf: 100 },
      { period: 2, contractCf: 100, benchmarkCf: 100 },
    ])
    expect(rate).toBe(5)
  })

  it('重大性阈值与结论', () => {
    expect(isBenchmarkDiffMaterial(5, 10)).toBe(false)
    expect(isBenchmarkDiffMaterial(12, 10)).toBe(true)
    expect(determineBenchmarkSppiConclusion(5, 10)).toBe('PASS')
    expect(determineBenchmarkSppiConclusion(12, 10)).toBe('FAIL')
  })
})
