/**
 * 单元测试 — M8 一般风险准备 双引擎综合验证
 *
 * 覆盖：
 * 1. useM8FormulaEngine — 审定数 + 权益类期末(贷方!) + 分类小计
 * 2. useM8RiskEngine — 风险资产计提 + 计提差异
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/ Task 7.1
 * Requirements: P1-P5
 *
 * 科目：4104 一般风险准备（贷方/权益类！期末=期初+贷方-借方）
 *
 * ⚠️ 方向与M3库存股（借方备抵）完全相反！
 *   M8一般风险准备（贷方权益）：期末 = 期初 + 贷方(计提) - 借方(转回/使用)
 *   M3库存股（借方备抵）：      期末 = 期初 + 借方(回购) - 贷方(注销)
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM8FormulaEngine'
import {
  calcRiskProvision,
  calcProvisionDiff,
} from '../composables/useM8RiskEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// Part 1: useM8FormulaEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useM8FormulaEngine — calcAuditedAmount (P1)', () => {
  it('审定数 = 未审 + AJE + RJE：200万+10万-5万=205万', () => {
    expect(calcAuditedAmount(2_000_000, 100_000, -50_000)).toBe(2_050_000)
  })

  it('全零输入：0+0+0=0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负数AJE（调减）', () => {
    expect(calcAuditedAmount(1_000_000, -200_000, 0)).toBe(800_000)
  })

  it('负数RJE（重分类调出）', () => {
    expect(calcAuditedAmount(3_000_000, 0, -1_000_000)).toBe(2_000_000)
  })

  it('AJE+RJE双调增', () => {
    expect(calcAuditedAmount(5_000_000, 300_000, 200_000)).toBe(5_500_000)
  })

  // null/NaN/undefined → 0 handling
  it('NaN未审数被视为0', () => {
    expect(calcAuditedAmount(NaN, 100_000, 50_000)).toBe(150_000)
  })

  it('null AJE被视为0', () => {
    expect(calcAuditedAmount(1_000_000, null as unknown as number, 50_000)).toBe(1_050_000)
  })

  it('undefined RJE被视为0', () => {
    expect(calcAuditedAmount(1_000_000, 100_000, undefined as unknown as number)).toBe(1_100_000)
  })

  it('Infinity被视为0', () => {
    expect(calcAuditedAmount(Infinity, 100, 200)).toBe(300)
  })

  it('全部非法值归零', () => {
    expect(calcAuditedAmount(NaN, null as unknown as number, undefined as unknown as number)).toBe(0)
  })
})

describe('useM8FormulaEngine — calcEquityEndBalance (P2)', () => {
  it('权益类贷方：期末 = 期初+贷方(计提)-借方(转回)', () => {
    // 期初800万 + 贷方(计提)200万 - 借方(转回)50万 = 950万
    expect(calcEquityEndBalance(8_000_000, 2_000_000, 500_000)).toBe(9_500_000)
  })

  it('全零：0+0-0=0', () => {
    expect(calcEquityEndBalance(0, 0, 0)).toBe(0)
  })

  it('仅有计提（贷方增加），无转回', () => {
    expect(calcEquityEndBalance(5_000_000, 1_000_000, 0)).toBe(6_000_000)
  })

  it('仅有转回（借方减少），无计提', () => {
    expect(calcEquityEndBalance(3_000_000, 0, 500_000)).toBe(2_500_000)
  })

  // ⚠️ 关键边界case：验证权益类方向
  it('⚠️ 方向验证：calcEquityEndBalance(100, 50, 30) === 120 (NOT 80)', () => {
    const result = calcEquityEndBalance(100, 50, 30)
    // 权益类：期末 = 期初 + 贷方 - 借方 = 100 + 50 - 30 = 120
    expect(result).toBe(120)
    // 反证：资产类方向(期初+借-贷) = 100 + 30 - 50 = 80
    expect(result).not.toBe(80)
  })

  it('权益类方向与资产类方向对比验证', () => {
    const begin = 1_000_000
    const credit = 300_000  // 计提增加（贷方）
    const debit = 100_000   // 转回减少（借方）
    const equityResult = calcEquityEndBalance(begin, credit, debit)
    // 权益类：1000000 + 300000 - 100000 = 1200000
    expect(equityResult).toBe(1_200_000)
    // 反证：如果错用资产类方向 begin + debit - credit = 800000
    const wrongAssetDirection = begin + debit - credit
    expect(equityResult).not.toBe(wrongAssetDirection)
  })

  it('大数值不溢出：10亿级', () => {
    expect(calcEquityEndBalance(1_000_000_000, 500_000_000, 200_000_000)).toBe(1_300_000_000)
  })

  it('期末为负（转回>期初+计提，公式数学正确）', () => {
    // 100万 + 50万 - 300万 = -150万
    expect(calcEquityEndBalance(1_000_000, 500_000, 3_000_000)).toBe(-1_500_000)
  })

  it('期初为0、仅贷方计提', () => {
    expect(calcEquityEndBalance(0, 10_000_000, 0)).toBe(10_000_000)
  })

  // null/NaN handling
  it('NaN期初被safe转为0', () => {
    expect(calcEquityEndBalance(NaN, 500_000, 200_000)).toBe(300_000)
  })

  it('null贷方被safe转为0', () => {
    expect(calcEquityEndBalance(1_000_000, null as unknown as number, 200_000)).toBe(800_000)
  })

  it('undefined借方被safe转为0', () => {
    expect(calcEquityEndBalance(1_000_000, 500_000, undefined as unknown as number)).toBe(1_500_000)
  })
})

describe('useM8FormulaEngine — calcSubtotal (P5)', () => {
  it('空数组返回0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素返回自身', () => {
    expect(calcSubtotal([5_000_000])).toBe(5_000_000)
  })

  it('多元素求和', () => {
    expect(calcSubtotal([1_000_000, 2_000_000, 3_000_000])).toBe(6_000_000)
  })

  it('含正负混合值正确求和', () => {
    expect(calcSubtotal([500_000, -200_000, 100_000, -50_000])).toBe(350_000)
  })

  it('NaN/null/undefined值被过滤为0', () => {
    expect(calcSubtotal([100_000, NaN, null as unknown as number, undefined as unknown as number, 200_000])).toBe(300_000)
  })

  it('非数组输入返回0', () => {
    expect(calcSubtotal(null as unknown as number[])).toBe(0)
    expect(calcSubtotal(undefined as unknown as number[])).toBe(0)
  })

  it('全NaN数组返回0', () => {
    expect(calcSubtotal([NaN, NaN, NaN])).toBe(0)
  })

  it('大数组（20个元素）正确求和', () => {
    const arr = Array.from({ length: 20 }, (_, i) => (i + 1) * 100_000)
    // sum = 100000*(1+2+...+20) = 100000*210 = 21_000_000
    expect(calcSubtotal(arr)).toBe(21_000_000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Part 2: useM8RiskEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useM8RiskEngine — calcRiskProvision (P3)', () => {
  it('基本计算：风险资产1000万×1.5%=15万', () => {
    expect(calcRiskProvision(10_000_000, 0.015)).toBe(150_000)
  })

  it('⚠️ 标准计提率验证：10_000_000×0.015=150_000', () => {
    const result = calcRiskProvision(10_000_000, 0.015)
    expect(result).toBe(150_000)
  })

  it('零计提比例：1亿×0=0', () => {
    expect(calcRiskProvision(100_000_000, 0)).toBe(0)
  })

  it('零风险资产：0×1.5%=0', () => {
    expect(calcRiskProvision(0, 0.015)).toBe(0)
  })

  it('大额风险资产：50亿×1.5%=7500万', () => {
    expect(calcRiskProvision(5_000_000_000, 0.015)).toBe(75_000_000)
  })

  it('较高计提比例2%：1000万×2%=20万', () => {
    expect(calcRiskProvision(10_000_000, 0.02)).toBe(200_000)
  })

  it('小额风险资产：100万×1.5%=1.5万', () => {
    expect(calcRiskProvision(1_000_000, 0.015)).toBe(15_000)
  })

  // null/NaN handling
  it('NaN风险资产被视为0', () => {
    expect(calcRiskProvision(NaN, 0.015)).toBe(0)
  })

  it('NaN比例被视为0', () => {
    expect(calcRiskProvision(10_000_000, NaN)).toBe(0)
  })

  it('null/undefined参数被视为0', () => {
    expect(calcRiskProvision(null as unknown as number, 0.015)).toBe(0)
    expect(calcRiskProvision(10_000_000, undefined as unknown as number)).toBe(0)
  })
})

describe('useM8RiskEngine — calcProvisionDiff (P4)', () => {
  it('精确匹配：应计提=账面，diff=0', () => {
    expect(calcProvisionDiff(150_000, 150_000)).toBe(0)
  })

  it('计提不足(正差)：应计提200_000 > 账面150_000 → +50_000', () => {
    const diff = calcProvisionDiff(200_000, 150_000)
    expect(diff).toBe(50_000)
    expect(diff).toBeGreaterThan(0) // 正=计提不足
  })

  it('超额计提(负差)：应计提100_000 < 账面150_000 → -50_000', () => {
    const diff = calcProvisionDiff(100_000, 150_000)
    expect(diff).toBe(-50_000)
    expect(diff).toBeLessThan(0) // 负=超额计提
  })

  it('⚠️ diff方向验证：calcProvisionDiff(200_000, 150_000)=50_000', () => {
    // 设计：estimated - booked，正=计提不足
    const result = calcProvisionDiff(200_000, 150_000)
    expect(result).toBe(50_000)
  })

  it('全零场景', () => {
    expect(calcProvisionDiff(0, 0)).toBe(0)
  })

  it('大额差异：应计7500万-账面5000万=+2500万（计提不足）', () => {
    expect(calcProvisionDiff(75_000_000, 50_000_000)).toBe(25_000_000)
  })

  it('完整计提场景：风险资产10亿×1.5%=1500万 vs 账面1200万', () => {
    const estimated = calcRiskProvision(1_000_000_000, 0.015) // 15_000_000
    const booked = 12_000_000
    const diff = calcProvisionDiff(estimated, booked)
    expect(diff).toBe(3_000_000) // 计提不足300万
    expect(diff).toBeGreaterThan(0)
  })

  // null/NaN handling
  it('NaN estimated被视为0', () => {
    expect(calcProvisionDiff(NaN, 100_000)).toBe(-100_000)
  })

  it('NaN booked被视为0', () => {
    expect(calcProvisionDiff(500_000, NaN)).toBe(500_000)
  })

  it('null/undefined参数被视为0', () => {
    expect(calcProvisionDiff(null as unknown as number, 100_000)).toBe(-100_000)
    expect(calcProvisionDiff(200_000, undefined as unknown as number)).toBe(200_000)
  })
})
