/**
 * Component Logic Tests — J2 组件逻辑验证
 *
 * 测试 sheetName 分发逻辑 + 三区块审定表 + 精算假设面板
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/ Task 7.2
 */
import { describe, it, expect } from 'vitest'
import { useJ2Adjudication } from '../useJ2Adjudication'
import { useJ2AccrualCheck } from '../useJ2AccrualCheck'
import { useJ2Detail } from '../useJ2Detail'
import { useJ2Disclosure } from '../useJ2Disclosure'
import { useJ2DualMode } from '../useJ2DualMode'

// ═══════════════════════════════════════════════════════════════════
// sheetName 分发逻辑测试
// ═══════════════════════════════════════════════════════════════════

describe('sheetName dispatch logic', () => {
  function resolveSheet(sheetName: string): string {
    if (sheetName.includes('底稿目录')) return '底稿目录'
    if (sheetName.includes('J2-1') || sheetName.includes('审定表')) return 'J2-1'
    if (sheetName.includes('J2-2') || sheetName.includes('明细表')) return 'J2-2'
    if (sheetName.includes('J2-3') || sheetName.includes('调整分录')) return 'J2-3'
    if (sheetName.includes('J2-4') || sheetName.includes('计提') || sheetName.includes('检查表')) return 'J2-4'
    if (sheetName.includes('上市')) return 'J2附注(上市)'
    if (sheetName.includes('国有') || sheetName.includes('国企')) return 'J2附注(国企)'
    const m = sheetName.match(/^(J2-\d+)/)
    return m ? m[1] : sheetName
  }

  it('dispatches index sheet', () => {
    expect(resolveSheet('底稿目录')).toBe('底稿目录')
  })
  it('dispatches J2-1', () => {
    expect(resolveSheet('审定表J2-1')).toBe('J2-1')
  })
  it('dispatches J2-2', () => {
    expect(resolveSheet('明细表J2-2')).toBe('J2-2')
  })
  it('dispatches J2-3', () => {
    expect(resolveSheet('调整分录汇总表J2-3')).toBe('J2-3')
  })
  it('dispatches J2-4', () => {
    expect(resolveSheet('计提情况检查表J2-4')).toBe('J2-4')
  })
  it('dispatches listed disclosure', () => {
    expect(resolveSheet('附注披露信息（上市公司）')).toBe('J2附注(上市)')
  })
  it('dispatches SOE disclosure', () => {
    expect(resolveSheet('附注披露信息（国有企业）')).toBe('J2附注(国企)')
  })
})

// ═══════════════════════════════════════════════════════════════════
// 三区块审定表测试
// ═══════════════════════════════════════════════════════════════════

describe('useJ2Adjudication — 三区块审定表', () => {
  it('initializes with three sections + total', () => {
    const adj = useJ2Adjudication({ wpId: 'test', projectId: 'test' })
    expect(adj.definedBenefitRow.value.label).toBe('设定受益计划')
    expect(adj.otherLongTermRow.value.label).toBe('其他长期职工福利')
    expect(adj.terminationRow.value.label).toBe('辞退福利')
  })

  it('recalculates audited = unadj + aje', () => {
    const adj = useJ2Adjudication({ wpId: 'test', projectId: 'test' })
    adj.definedBenefitRow.value.beginUnadj = 1000
    adj.definedBenefitRow.value.beginAje = 50
    adj.recalcAll()
    expect(adj.definedBenefitRow.value.beginAudited).toBe(1050)
  })

  it('total row sums all three sections', () => {
    const adj = useJ2Adjudication({ wpId: 'test', projectId: 'test' })
    adj.definedBenefitRow.value.endUnadj = 100
    adj.otherLongTermRow.value.endUnadj = 200
    adj.terminationRow.value.endUnadj = 300
    adj.recalcAll()
    expect(adj.totalRow.value.endUnadj).toBe(600)
  })

  it('loadFromHtmlData populates rows', () => {
    const adj = useJ2Adjudication({ wpId: 'test', projectId: 'test' })
    adj.loadFromHtmlData({
      adjudication: {
        definedBenefit: { label: '设定受益计划', beginUnadj: 5000, endUnadj: 6000 },
      },
    })
    expect(adj.definedBenefitRow.value.beginUnadj).toBe(5000)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 精算假设面板测试
// ═══════════════════════════════════════════════════════════════════

describe('useJ2AccrualCheck — 精算假设面板', () => {
  it('initializes with default assumptions', () => {
    const check = useJ2AccrualCheck()
    expect(check.assumptions.value.discountRate).toBe(0.04)
    expect(check.assumptions.value.salaryGrowthRate).toBe(0.08)
  })

  it('validation reflects assumptions state', () => {
    const check = useJ2AccrualCheck()
    expect(check.validation.value.isValid).toBe(true)

    check.assumptions.value.discountRate = 0  // invalid
    expect(check.validation.value.isValid).toBe(false)
  })

  it('ISA620 completeness tracks progress', () => {
    const check = useJ2AccrualCheck()
    expect(check.isa620Completeness.value.done).toBe(0)
    expect(check.isa620Completeness.value.total).toBe(8)

    check.isa620.value.actuaryName = '张精算'
    check.isa620.value.actuaryFirm = 'XX事务所'
    expect(check.isa620Completeness.value.done).toBe(2)
  })

  it('loadFromHtmlData populates assumptions', () => {
    const check = useJ2AccrualCheck()
    check.loadFromHtmlData({
      assumptions: { discountRate: 0.05, salaryGrowthRate: 0.10, mortalityRate: 0.003, turnoverRate: 0.12 },
      isa620: { actuaryName: '测试', overallConclusion: 'rely' },
    })
    expect(check.assumptions.value.discountRate).toBe(0.05)
    expect(check.isa620.value.actuaryName).toBe('测试')
  })
})

// ═══════════════════════════════════════════════════════════════════
// 明细表测试
// ═══════════════════════════════════════════════════════════════════

describe('useJ2Detail — DBO明细', () => {
  it('creates default items', () => {
    const detail = useJ2Detail()
    detail.items.value = detail.createDefaultItems()
    expect(detail.items.value.length).toBe(3)
  })

  it('recalcItem computes endBalance correctly (负债类)', () => {
    const detail = useJ2Detail()
    const item = detail.createDefaultItems()[0]
    item.beginBalance = 10000
    item.serviceCost = 500
    item.interestCost = 400
    item.actuarialLoss = 200
    item.benefitsPaid = 300
    item.actuarialGain = 100
    detail.recalcItem(item)
    // end = 10000 + (500+400+200+0) - (300+100+0) = 10700
    expect(item.endBalance).toBe(10700)
  })

  it('calculates net liability', () => {
    const detail = useJ2Detail()
    const item = detail.createDefaultItems()[0]
    item.beginBalance = 10000
    item.planAssetFV = 3000
    detail.recalcItem(item)
    // net = endBalance(10000) - planAssetFV(3000) = 7000
    expect(item.netLiability).toBe(7000)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 双模式测试
// ═══════════════════════════════════════════════════════════════════

describe('useJ2DualMode', () => {
  it('defaults to html mode', () => {
    const dm = useJ2DualMode()
    expect(dm.mode.value).toBe('html')
    expect(dm.isHtmlMode.value).toBe(true)
  })
  it('toggles mode', () => {
    const dm = useJ2DualMode()
    dm.toggleMode()
    expect(dm.mode.value).toBe('onlyoffice')
    expect(dm.isOOMode.value).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 附注披露测试
// ═══════════════════════════════════════════════════════════════════

describe('useJ2Disclosure', () => {
  it('listed version has 5 sections', () => {
    const d = useJ2Disclosure('listed')
    d.initDefault()
    expect(d.sections.value.length).toBe(5)
    expect(d.sections.value[0].title).toBe('长期应付职工薪酬')
  })
  it('soe version has 3 sections', () => {
    const d = useJ2Disclosure('soe')
    d.initDefault()
    expect(d.sections.value.length).toBe(3)
  })
})
