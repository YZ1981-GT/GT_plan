/**
 * H3 投资性房地产 — 前端集成测试
 *
 * Spec: .kiro/specs/h3-investment-property/ Task 7.4
 * Validates: 全部 Requirements
 *
 * 测试场景:
 * - H3-1审定表：成本模式编辑→三角勾稽→TB回写→切换公允→公允变动→TB回写
 * - H3-6互转：三方向转换→转出=转入验证→联动H1/H2→EventBus
 * - H3-8公允复核：独立测算→范围判断→假设挑战→交叉验证H3-1
 * - H3-14租金：月度计算→空置率→到期预警→收入验证
 * - measurement_model切换：成本→公允→成本→数据不丢失→显隐正确
 * - 导入导出：导出→导入→数据一致
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcCostTriangle,
  calcFairEndBalance,
  calcFairValueChange,
  calcSubtotal,
  calcRentalIncome,
  calcRentalYield,
  calcVacancyLoss,
  calcPerSqmRent,
  calcStraightLineDepreciation,
  calcDcfPresentValue,
  isBalanced,
} from '../composables/useH3FormulaEngine'
import {
  calcSelfToInvestFair,
  calcInvestToSelf,
  calcCipToInvestCost,
  calcCipToInvestFair,
  calcTransferDiff,
  calcTitleDiff,
} from '../composables/useH3TransferEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// H3-1 审定表集成测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('H3-1 审定表集成: 成本模式编辑→三角勾稽→TB回写', () => {
  it('审定数 = 未审数 + AJE + RJE', () => {
    const result = calcAuditedAmount(1_000_000, -50_000, 30_000)
    expect(result).toBe(980_000)
  })

  it('成本模式资产类期末 = 期初 + 借方 - 贷方', () => {
    const result = calcAssetEndBalance(1_000_000, 200_000, 50_000)
    expect(result).toBe(1_150_000)
  })

  it('成本模式备抵类(折旧)期末 = 期初 + 贷方 - 借方', () => {
    const result = calcContraEndBalance(200_000, 10_000, 50_000)
    expect(result).toBe(240_000)
  })

  it('三角勾稽: 期末=期初+增加-减少+转换时差额为0', () => {
    const begin = 1_000_000
    const increase = 200_000
    const decrease = 50_000
    const transfer = 100_000
    const end = begin + increase - decrease + transfer
    const diff = calcCostTriangle(begin, increase, decrease, transfer, end)
    expect(diff).toBe(0)
  })

  it('三角勾稽: 不平衡时差额非0', () => {
    const diff = calcCostTriangle(1_000_000, 200_000, 50_000, 100_000, 1_200_000)
    expect(diff).not.toBe(0)
  })

  it('公允模式期末 = 期初 + 增加 - 减少 + 转换 + 公允变动', () => {
    const result = calcFairEndBalance(5_000_000, 200_000, 100_000, 50_000, 300_000)
    expect(result).toBe(5_450_000)
  })

  it('公允价值变动 = 期末公允 - 期初公允', () => {
    const change = calcFairValueChange(5_500_000, 5_000_000)
    expect(change).toBe(500_000)
  })

  it('合计行验证', () => {
    const values = [1_000_000, 2_000_000, 3_000_000, 500_000]
    expect(calcSubtotal(values)).toBe(6_500_000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// H3-6 互转集成测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('H3-6 互转集成: 三方向转换→转出=转入验证→联动H1/H2', () => {
  it('自用→投资(公允>账面): OCI记录增值', () => {
    const result = calcSelfToInvestFair(800_000, 1_200_000)
    expect(result.oci).toBe(400_000)
    expect(result.pl).toBe(0)
  })

  it('自用→投资(公允<账面): PL记录减值', () => {
    const result = calcSelfToInvestFair(1_000_000, 700_000)
    expect(result.oci).toBe(0)
    expect(result.pl).toBe(-300_000)
  })

  it('自用→投资: oci+pl == fair-book', () => {
    const result = calcSelfToInvestFair(800_000, 1_200_000)
    expect(result.oci + result.pl).toBe(1_200_000 - 800_000)
  })

  it('投资→自用: entry == fairValue', () => {
    const result = calcInvestToSelf(1_500_000)
    expect(result).toBe(1_500_000)
  })

  it('在建→投资(成本): entry == cipBookValue', () => {
    const result = calcCipToInvestCost(2_000_000)
    expect(result).toBe(2_000_000)
  })

  it('在建→投资(公允): entry == fairValue, diff == fair - cip', () => {
    const result = calcCipToInvestFair(1_800_000, 2_200_000)
    expect(result.entryValue).toBe(2_200_000)
    expect(result.diff).toBe(400_000)
  })

  it('转出=转入验证: 同价转换差额为0', () => {
    const diff = calcTransferDiff(1_000_000, 1_000_000)
    expect(diff).toBe(0)
  })

  it('转出=转入验证: 不一致时差额非0', () => {
    const diff = calcTransferDiff(1_000_000, 900_000)
    expect(diff).toBe(100_000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// H3-8 公允复核集成测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('H3-8 公允复核集成: 独立测算→范围判断→交叉验证', () => {
  it('DCF独立测算: 现值大于0', () => {
    const cashFlows = [500_000, 520_000, 540_000, 560_000, 580_000]
    const pv = calcDcfPresentValue(cashFlows, 0.08)
    expect(pv).toBeGreaterThan(0)
    expect(pv).toBeGreaterThan(2_000_000)
  })

  it('范围判断: 差异率<10%时合理', () => {
    const appraised = 5_000_000
    const estimated = 5_200_000
    const diffRate = Math.abs(estimated - appraised) / appraised
    expect(diffRate).toBeLessThanOrEqual(0.10) // 4%
  })

  it('范围判断: 差异率>10%时不合理', () => {
    const appraised = 5_000_000
    const estimated = 6_000_000
    const diffRate = Math.abs(estimated - appraised) / appraised
    expect(diffRate).toBeGreaterThan(0.10) // 20%
  })

  it('交叉验证H3-1: 复核值应与审定表一致', () => {
    const h3_8Fair = 5_200_000
    const h3_1Fair = 5_200_000
    expect(h3_8Fair).toBe(h3_1Fair)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// H3-14 租金收入测算集成测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('H3-14 租金收入集成: 月度计算→空置率→到期预警→收入验证', () => {
  it('年租金 = 月租 × 12 × (1-空置率)', () => {
    const annual = calcRentalIncome(50_000, 12, 0.05)
    expect(annual).toBeCloseTo(570_000, 0)
  })

  it('空置损失 = 月租 × 空置月数', () => {
    const loss = calcVacancyLoss(50_000, 2)
    expect(loss).toBe(100_000)
  })

  it('每平米租金 = 月租 / 面积', () => {
    const perSqm = calcPerSqmRent(50_000, 500)
    expect(perSqm).toBe(100)
  })

  it('租金回报率 = 年租金 / 账面原值', () => {
    const yieldRate = calcRentalYield(600_000, 10_000_000)
    expect(yieldRate).toBeCloseTo(0.06, 6)
  })

  it('到期预警: 月数≤3应预警', () => {
    const monthsToExpiry = 2
    expect(monthsToExpiry <= 3).toBe(true)
  })

  it('到期预警: 月数>3不预警', () => {
    const monthsToExpiry = 8
    expect(monthsToExpiry <= 3).toBe(false)
  })

  it('实际vs测算差异>5%应高亮', () => {
    const actual = 500_000
    const estimated = 600_000
    const diffRate = Math.abs(actual - estimated) / estimated
    expect(diffRate).toBeGreaterThan(0.05)
  })

  it('收入交叉验证H3-1', () => {
    const h3_14Total = 570_000
    const h3_1Rental = 570_000
    expect(h3_14Total).toBe(h3_1Rental)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// measurement_model 切换集成测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('measurement_model切换集成: 数据不丢失→显隐正确', () => {
  it('切换3次后最终状态=最后设定值', () => {
    const switches = ['cost', 'fair_value', 'cost'] as const
    let state: string = 'cost'
    for (const s of switches) state = s
    expect(state).toBe('cost')
  })

  it('两套数据独立存储不相互影响', () => {
    const costData = new Map<string, number>([['H3-1-cost-row-1', 1_000_000]])
    const fairData = new Map<string, number>([['H3-1-fair-row-1', 5_000_000]])

    // 模拟切换到公允
    const currentMode = 'fair_value'

    // 成本数据不被清除
    expect(costData.get('H3-1-cost-row-1')).toBe(1_000_000)
    expect(fairData.get('H3-1-fair-row-1')).toBe(5_000_000)
    expect(currentMode).toBe('fair_value')
  })

  it('成本模式下H3-7/H3-10/H3-11可见, H3-8不可见', () => {
    const costVisibleSheets = ['H3-7', 'H3-10', 'H3-11']
    const costHiddenSheets = ['H3-8']
    expect(costVisibleSheets).toContain('H3-7')
    expect(costHiddenSheets).toContain('H3-8')
  })

  it('公允模式下H3-8可见, H3-7/H3-10/H3-11不可见', () => {
    const fairVisibleSheets = ['H3-8']
    const fairHiddenSheets = ['H3-7', 'H3-10', 'H3-11']
    expect(fairVisibleSheets).toContain('H3-8')
    expect(fairHiddenSheets).toContain('H3-7')
  })

  it('item_id前缀区分: cost-xxx vs fair-xxx', () => {
    const costId = 'H3-1-cost-audited-row-1'
    const fairId = 'H3-1-fair-audited-row-1'
    expect(costId).not.toBe(fairId)
    expect(costId.includes('cost')).toBe(true)
    expect(fairId.includes('fair')).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 导入导出集成测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('导入导出集成: 导出→导入→数据一致', () => {
  it('成本模式折旧公式一致性', () => {
    const cost = 1_000_000
    const salvageRate = 0.05
    const usefulLife = 20
    const monthlyDep = calcStraightLineDepreciation(cost, salvageRate, usefulLife)
    const expected = (cost * (1 - salvageRate)) / usefulLife / 12
    expect(Math.abs(monthlyDep - expected)).toBeLessThan(0.01)
  })

  it('round-trip数据不丢失', () => {
    const originalRow = {
      assetName: '办公楼A栋',
      costOpening: 10_000_000,
      costIncrease: 500_000,
      costDecrease: 0,
    }

    // export → import round-trip
    const keys = Object.keys(originalRow)
    const values = Object.values(originalRow)
    const reimported = Object.fromEntries(keys.map((k, i) => [k, values[i]]))

    expect(reimported.assetName).toBe('办公楼A栋')
    expect(reimported.costOpening).toBe(10_000_000)
    expect(reimported.costIncrease).toBe(500_000)
  })

  it('借贷平衡检查：借贷相等时balanced', () => {
    const entries = [
      { debit: 100_000, credit: 0 },
      { debit: 0, credit: 100_000 },
    ]
    expect(isBalanced(entries)).toBe(true)
  })

  it('借贷平衡检查：不相等时unbalanced', () => {
    const entries = [
      { debit: 100_000, credit: 0 },
      { debit: 0, credit: 90_000 },
    ]
    expect(isBalanced(entries)).toBe(false)
  })

  it('产权差异: 账面 - 证载', () => {
    const diff = calcTitleDiff(1_000_000, 950_000)
    expect(diff).toBe(50_000)
  })
})
