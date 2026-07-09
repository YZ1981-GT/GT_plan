/**
 * 单元测试 — L4 应付债券 三大引擎综合验证
 *
 * 覆盖：
 * 1. useL4FormulaEngine — 审定数公式链 + 负债类期末余额 + 初始计量 + 分类小计
 * 2. useL4EIREngine — 实际利率法2分支 + 边界(eir=0)（补充 useL4EIREngine.test.ts）
 * 3. useL4EquityLiabEngine — 权益负债划分 + 负债成分现值
 *
 * Spec: .kiro/specs/l4-bonds-payable/ Task 7.1
 * Requirements: P1-P9
 *
 * 科目：2502 应付债券（贷方/负债类！期末=期初+贷方-借方）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcInitialAmount,
  calcPremiumDiscount,
  calcSubtotal,
} from '../useL4FormulaEngine'
import {
  calcInterestExpense,
  calcEndAmortizedCost_Bullet,
  calcEndAmortizedCost_Installment,
  generateSchedule,
  validateSchedule,
  solveEIR,
} from '../useL4EIREngine'
import {
  calcLiabilityComponent,
  calcEquityComponent,
} from '../useL4EquityLiabEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// Part 1: useL4FormulaEngine 单元测试（P1, P2, P8）
// ═══════════════════════════════════════════════════════════════════════════════

describe('useL4FormulaEngine — calcAuditedAmount (P1)', () => {
  it('基础场景：未审100万 + AJE 5万 + RJE -2万 = 103万', () => {
    expect(calcAuditedAmount(1_000_000, 50_000, -20_000)).toBe(1_030_000)
  })

  it('全零输入：0 + 0 + 0 = 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负数未审数（负债类贷方为正，但允许通用计算）', () => {
    expect(calcAuditedAmount(-500_000, 100_000, 50_000)).toBe(-350_000)
  })

  it('只有 AJE 调增', () => {
    expect(calcAuditedAmount(2_000_000, 200_000, 0)).toBe(2_200_000)
  })

  it('只有 RJE 重分类', () => {
    expect(calcAuditedAmount(2_000_000, 0, -500_000)).toBe(1_500_000)
  })
})

describe('useL4FormulaEngine — calcLiabilityEndBalance (P2)', () => {
  it('负债类贷方基础：期初100万 + 贷方发行50万 - 借方兑付20万 = 130万', () => {
    expect(calcLiabilityEndBalance(1_000_000, 500_000, 200_000)).toBe(1_300_000)
  })

  it('期初为0：新发行债券 0 + 1000万 - 0 = 1000万', () => {
    expect(calcLiabilityEndBalance(0, 10_000_000, 0)).toBe(10_000_000)
  })

  it('全部兑付：期初500万 + 0 - 500万 = 0', () => {
    expect(calcLiabilityEndBalance(5_000_000, 0, 5_000_000)).toBe(0)
  })

  it('过度兑付（异常情况允许负值）：期初100万 + 0 - 150万 = -50万', () => {
    expect(calcLiabilityEndBalance(1_000_000, 0, 1_500_000)).toBe(-500_000)
  })

  it('利息调整增加：期初980万 + 贷方利息调整5万 - 0 = 985万', () => {
    expect(calcLiabilityEndBalance(9_800_000, 50_000, 0)).toBe(9_850_000)
  })

  it('全零：0 + 0 - 0 = 0', () => {
    expect(calcLiabilityEndBalance(0, 0, 0)).toBe(0)
  })
})

describe('useL4FormulaEngine — calcInitialAmount (P8)', () => {
  it('基础：发行价1050万 - 交易费用50万 = 1000万', () => {
    expect(calcInitialAmount(10_500_000, 500_000)).toBe(10_000_000)
  })

  it('零交易费用（平价直发）：920万 - 0 = 920万', () => {
    expect(calcInitialAmount(9_200_000, 0)).toBe(9_200_000)
  })

  it('小额交易费用：100万 - 1万 = 99万', () => {
    expect(calcInitialAmount(1_000_000, 10_000)).toBe(990_000)
  })
})

describe('useL4FormulaEngine — calcPremiumDiscount', () => {
  it('溢价发行：初始入账105万 - 面值100万 = 溢价5万', () => {
    expect(calcPremiumDiscount(1_050_000, 1_000_000)).toBe(50_000)
  })

  it('折价发行：初始入账92万 - 面值100万 = 折价-8万', () => {
    expect(calcPremiumDiscount(920_000, 1_000_000)).toBe(-80_000)
  })

  it('平价发行：初始入账100万 - 面值100万 = 0', () => {
    expect(calcPremiumDiscount(1_000_000, 1_000_000)).toBe(0)
  })
})

describe('useL4FormulaEngine — calcSubtotal', () => {
  it('多品种小计：[100万, 200万, 300万] = 600万', () => {
    expect(calcSubtotal([1_000_000, 2_000_000, 3_000_000])).toBe(6_000_000)
  })

  it('空数组：[] = 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素：[500万] = 500万', () => {
    expect(calcSubtotal([5_000_000])).toBe(5_000_000)
  })

  it('含负值（溢折价汇总）：[50000, -30000, 20000]', () => {
    expect(calcSubtotal([50_000, -30_000, 20_000])).toBe(40_000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Part 2: useL4EIREngine 补充验证（P3, P4, P5, P6, P7）
// 注意：主测试在 useL4EIREngine.test.ts，此处为补充/交叉验证
// ═══════════════════════════════════════════════════════════════════════════════

describe('useL4EIREngine — 补充验证', () => {
  describe('P3: calcInterestExpense 利息费用', () => {
    it('大额摊余成本 × 小利率：5000万 × 3.5% = 175万', () => {
      expect(calcInterestExpense(50_000_000, 0.035)).toBeCloseTo(1_750_000, 2)
    })

    it('EIR=0 边界 (P7)：任意摊余成本 × 0 = 0', () => {
      expect(calcInterestExpense(999_999_999, 0)).toBe(0)
    })
  })

  describe('P4/P5: 两分支对比验证', () => {
    it('bullet vs installment：相同利息费用时差异=couponPaid', () => {
      const begin = 1_000_000
      const ie = 60_000
      const coupon = 50_000
      const bulletEnd = calcEndAmortizedCost_Bullet(begin, ie)
      const installEnd = calcEndAmortizedCost_Installment(begin, ie, coupon)
      expect(bulletEnd - installEnd).toBeCloseTo(coupon, 10)
    })
  })

  describe('P6: generateSchedule installment 典型验证', () => {
    it('溢价+折价场景末期endCost均≈面值', () => {
      // 折价
      const s1 = generateSchedule(900_000, 1_000_000, 0.04, 0.07, 5, 'installment')
      expect(s1[4].endCost).toBe(1_000_000)

      // 溢价
      const s2 = generateSchedule(1_100_000, 1_000_000, 0.06, 0.03, 4, 'installment')
      expect(s2[3].endCost).toBe(1_000_000)
    })

    it('periods=1 单期：直接调整到面值', () => {
      const schedule = generateSchedule(950_000, 1_000_000, 0.05, 0.08, 1, 'installment')
      expect(schedule).toHaveLength(1)
      expect(schedule[0].endCost).toBe(1_000_000)
    })
  })

  describe('P6: generateSchedule bullet 分支验证', () => {
    it('bullet分支：摊余成本逐期递增（利息全资本化）', () => {
      const schedule = generateSchedule(950_000, 1_000_000, 0.05, 0.07, 3, 'bullet')
      for (let i = 1; i < schedule.length; i++) {
        expect(schedule[i].beginCost).toBeGreaterThan(schedule[i - 1].beginCost)
      }
    })

    it('bullet分支EIR=0：所有interestExpense=0，endCost不变', () => {
      const schedule = generateSchedule(1_000_000, 1_000_000, 0.05, 0, 3, 'bullet')
      for (const row of schedule) {
        expect(row.interestExpense).toBe(0)
        expect(row.endCost).toBe(row.beginCost)
      }
    })
  })

  describe('validateSchedule 边界', () => {
    it('installment分支：tailDiff=0（尾差已强制调整）', () => {
      const schedule = generateSchedule(920_000, 1_000_000, 0.04, 0.06, 5, 'installment')
      const { isValid, tailDiff } = validateSchedule(schedule, 1_000_000)
      expect(isValid).toBe(true)
      expect(tailDiff).toBe(0)
    })
  })

  describe('solveEIR 极端场景', () => {
    it('单期（零息折价债）：面值100，发行90，到期还100', () => {
      const eir = solveEIR([100], 90)
      // 100 / (1+eir) = 90 → eir = 100/90 - 1 ≈ 0.1111
      expect(eir).toBeCloseTo(100 / 90 - 1, 4)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Part 3: useL4EquityLiabEngine 单元测试（P9）
// ═══════════════════════════════════════════════════════════════════════════════

describe('useL4EquityLiabEngine — calcLiabilityComponent', () => {
  it('基础NPV折现：5年期可转债，票面5%，面值100万，市场利率8%', () => {
    // 现金流：年付息5万×4 + 最后一期(5万+100万)
    const cashFlows = [50_000, 50_000, 50_000, 50_000, 1_050_000]
    const marketRate = 0.08

    const liability = calcLiabilityComponent(cashFlows, marketRate)

    // 手动验证：
    // PV = 50000/1.08 + 50000/1.08^2 + 50000/1.08^3 + 50000/1.08^4 + 1050000/1.08^5
    const expected =
      50_000 / 1.08 +
      50_000 / Math.pow(1.08, 2) +
      50_000 / Math.pow(1.08, 3) +
      50_000 / Math.pow(1.08, 4) +
      1_050_000 / Math.pow(1.08, 5)

    expect(liability).toBeCloseTo(expected, 2)
    // 预期约88万（低于面值100万，因为市场利率>票面利率）
    expect(liability).toBeLessThan(1_000_000)
  })

  it('marketRate=0 时不折现，负债成分=现金流总和', () => {
    const cashFlows = [100, 200, 300]
    expect(calcLiabilityComponent(cashFlows, 0)).toBe(600)
  })

  it('空现金流返回0', () => {
    expect(calcLiabilityComponent([], 0.05)).toBe(0)
  })

  it('单期折现：100/(1+0.1) ≈ 90.91', () => {
    expect(calcLiabilityComponent([100], 0.1)).toBeCloseTo(100 / 1.1, 2)
  })

  it('高市场利率：折现后负债成分大幅减少', () => {
    const cashFlows = [50_000, 50_000, 1_050_000]
    const lowRate = calcLiabilityComponent(cashFlows, 0.03)
    const highRate = calcLiabilityComponent(cashFlows, 0.15)
    expect(highRate).toBeLessThan(lowRate)
  })
})

describe('useL4EquityLiabEngine — calcEquityComponent (P9)', () => {
  it('正常分拆：发行总额120万 - 负债成分88万 = 权益成分32万', () => {
    expect(calcEquityComponent(1_200_000, 880_000)).toBe(320_000)
  })

  it('权益成分为0（全部为负债）：发行100万 - 负债100万 = 0', () => {
    expect(calcEquityComponent(1_000_000, 1_000_000)).toBe(0)
  })

  it('权益成分为负（分拆异常）：发行80万 - 负债90万 = -10万', () => {
    // 这种情况发生在市场利率极低时，调用方应显示红色警告
    expect(calcEquityComponent(800_000, 900_000)).toBe(-100_000)
  })

  it('完整分拆流程：calcLiabilityComponent + calcEquityComponent 联动', () => {
    // 可转债：面值100万，票面5%，3年，市场利率7%
    const cashFlows = [50_000, 50_000, 1_050_000]
    const totalProceeds = 1_000_000 // 平价发行

    const liabComponent = calcLiabilityComponent(cashFlows, 0.07)
    const equityComponent = calcEquityComponent(totalProceeds, liabComponent)

    // 负债成分 < 面值（市场利率>票面利率）
    expect(liabComponent).toBeLessThan(1_000_000)
    // 权益成分 > 0（正常分拆）
    expect(equityComponent).toBeGreaterThan(0)
    // 恒等式：负债成分 + 权益成分 = 发行总额
    expect(liabComponent + equityComponent).toBeCloseTo(totalProceeds, 2)
  })
})
