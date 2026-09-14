/**
 * 单元测试 — L5 长期应付款 双引擎综合验证
 *
 * 覆盖：
 * 1. useL5FormulaEngine — 审定数 + 负债类期末(贷方!) + 备抵类期末(借方!) + 净额 + 小计
 * 2. useL5AmortizationEngine — 实际利率法摊销 + 期末摊余成本 + 摊销表生成 + 末期验证
 *
 * Spec: .kiro/specs/l5-long-term-payables/ Task 7.1
 * Requirements: P1-P7
 *
 * 科目：2701 长期应付款（贷方/负债类！期末=期初+贷方-借方）
 *       未确认融资费用（借方/负债备抵类！期末=期初+借方-贷方）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcContraLiabilityEndBalance,
  calcNetPayable,
  calcSubtotal,
} from '../composables/useL5FormulaEngine'
import {
  calcAmortization,
  calcEndCost,
  generateSchedule,
  validateSchedule,
} from '../composables/useL5AmortizationEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// Part 1: useL5FormulaEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useL5FormulaEngine — calcAuditedAmount (P1)', () => {
  it('审定数 = 未审 + AJE + RJE：100万+5万-2万=103万', () => {
    expect(calcAuditedAmount(1_000_000, 50_000, -20_000)).toBe(1_030_000)
  })

  it('全零输入：0+0+0=0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负数未审数场景', () => {
    expect(calcAuditedAmount(-500_000, 100_000, 50_000)).toBe(-350_000)
  })

  it('只有AJE调增', () => {
    expect(calcAuditedAmount(2_000_000, 200_000, 0)).toBe(2_200_000)
  })

  it('只有RJE重分类', () => {
    expect(calcAuditedAmount(2_000_000, 0, -500_000)).toBe(1_500_000)
  })
})

describe('useL5FormulaEngine — calcLiabilityEndBalance (P2)', () => {
  it('负债类贷方：期末 = 期初+贷方-借方', () => {
    // 期初500万 + 贷方(新增)300万 - 借方(偿还)100万 = 700万
    expect(calcLiabilityEndBalance(5_000_000, 3_000_000, 1_000_000)).toBe(7_000_000)
  })

  it('全额偿还后期末为0', () => {
    expect(calcLiabilityEndBalance(2_000_000, 0, 2_000_000)).toBe(0)
  })

  it('仅有新增贷方时期末增加', () => {
    expect(calcLiabilityEndBalance(1_000_000, 5_000_000, 0)).toBe(6_000_000)
  })

  it('偿还大于余额时期末为负（公式正确）', () => {
    expect(calcLiabilityEndBalance(100_000, 50_000, 300_000)).toBe(-150_000)
  })

  it('期初为0、仅有新增', () => {
    expect(calcLiabilityEndBalance(0, 10_000_000, 0)).toBe(10_000_000)
  })
})

describe('useL5FormulaEngine — calcContraLiabilityEndBalance (P3)', () => {
  it('备抵类借方：期末 = 期初+借方-贷方', () => {
    // 期初100万 + 借方(新增未确认)50万 - 贷方(摊销)30万 = 120万
    expect(calcContraLiabilityEndBalance(1_000_000, 500_000, 300_000)).toBe(1_200_000)
  })

  it('全部摊销完毕后期末为0', () => {
    expect(calcContraLiabilityEndBalance(500_000, 0, 500_000)).toBe(0)
  })

  it('仅有新增借方', () => {
    expect(calcContraLiabilityEndBalance(200_000, 800_000, 0)).toBe(1_000_000)
  })

  it('仅有摊销冲减', () => {
    expect(calcContraLiabilityEndBalance(1_000_000, 0, 200_000)).toBe(800_000)
  })

  it('期初为0、首次确认', () => {
    expect(calcContraLiabilityEndBalance(0, 3_000_000, 0)).toBe(3_000_000)
  })
})

describe('useL5FormulaEngine — calcNetPayable (P4)', () => {
  it('净额 = 长期应付款 - 未确认融资费用', () => {
    // 面值1000万 - 未确认200万 = 净额800万
    expect(calcNetPayable(10_000_000, 2_000_000)).toBe(8_000_000)
  })

  it('未确认为0时净额等于应付款', () => {
    expect(calcNetPayable(5_000_000, 0)).toBe(5_000_000)
  })

  it('双方均为0', () => {
    expect(calcNetPayable(0, 0)).toBe(0)
  })

  it('未确认大于应付款（异常但公式正确）', () => {
    expect(calcNetPayable(1_000_000, 3_000_000)).toBe(-2_000_000)
  })
})

describe('useL5FormulaEngine — calcSubtotal', () => {
  it('空数组返回0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素返回自身', () => {
    expect(calcSubtotal([7_777_000])).toBe(7_777_000)
  })

  it('多元素求和', () => {
    expect(calcSubtotal([1_000_000, 2_000_000, 3_000_000, 500_000])).toBe(6_500_000)
  })

  it('含负数正确求和', () => {
    expect(calcSubtotal([1_000, -500, 200])).toBe(700)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Part 2: useL5AmortizationEngine 单元测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('useL5AmortizationEngine — calcAmortization (P5)', () => {
  it('正常摊销：100万 × 5% = 5万', () => {
    expect(calcAmortization(1_000_000, 0.05)).toBeCloseTo(50_000, 2)
  })

  it('大额：1亿 × 8% = 800万', () => {
    expect(calcAmortization(100_000_000, 0.08)).toBeCloseTo(8_000_000, 2)
  })

  it('小额：1万 × 3% = 300', () => {
    expect(calcAmortization(10_000, 0.03)).toBeCloseTo(300, 2)
  })
})

describe('useL5AmortizationEngine — calcAmortization EIR=0 (P6)', () => {
  it('EIR=0 时摊销为0', () => {
    expect(calcAmortization(1_000_000, 0)).toBe(0)
  })

  it('EIR=0 + 大额期初摊余成本仍为0', () => {
    expect(calcAmortization(999_999_999, 0)).toBe(0)
  })

  it('EIR=0 + 期初为0也为0', () => {
    expect(calcAmortization(0, 0)).toBe(0)
  })
})

describe('useL5AmortizationEngine — calcEndCost', () => {
  it('期末 = 期初 - 还款 + 摊销', () => {
    // 期初100万, 摊销5万, 还款20万 → 期末=100-20+5=85万
    expect(calcEndCost(1_000_000, 50_000, 200_000)).toBe(850_000)
  })

  it('还款等于期初+摊销时期末为0', () => {
    // 100 + 5 - 105 = 0
    expect(calcEndCost(100, 5, 105)).toBe(0)
  })

  it('无还款时期末=期初+摊销', () => {
    expect(calcEndCost(1_000_000, 50_000, 0)).toBe(1_050_000)
  })
})

describe('useL5AmortizationEngine — generateSchedule', () => {
  it('正常案例：初始100万，等额还款，5%利率，5期', () => {
    // 等额还款230,975（PMT公式近似）
    const repayment = 230_975
    const schedule = generateSchedule(1_000_000, Array(5).fill(repayment), 0.05, 5)

    expect(schedule).toHaveLength(5)
    // 第一期
    expect(schedule[0].period).toBe(1)
    expect(schedule[0].beginCost).toBe(1_000_000)
    expect(schedule[0].amortization).toBeCloseTo(50_000, 0) // 100万×5%
    // 最后一期强制endCost=0（尾差调整）
    expect(schedule[4].endCost).toBe(0)
  })

  it('单期：初始50万，还款50万，5%利率，1期', () => {
    const schedule = generateSchedule(500_000, [500_000], 0.05, 1)

    expect(schedule).toHaveLength(1)
    expect(schedule[0].period).toBe(1)
    expect(schedule[0].beginCost).toBe(500_000)
    // 最后一期（也是唯一一期）尾差调整：amortization = repayment - begin = 500000 - 500000 = 0
    expect(schedule[0].endCost).toBe(0)
  })

  it('空case：periods=0 返回空数组', () => {
    expect(generateSchedule(1_000_000, [100_000], 0.05, 0)).toEqual([])
  })

  it('空case：initialCost=0 返回空数组', () => {
    expect(generateSchedule(0, [100_000], 0.05, 5)).toEqual([])
  })

  it('空case：repayments为空数组 返回空数组', () => {
    expect(generateSchedule(1_000_000, [], 0.05, 5)).toEqual([])
  })

  it('最后一期尾差调整保证endCost=0', () => {
    // 故意给不精确的还款值，验证尾差调整
    const schedule = generateSchedule(1_000_000, [220_000, 220_000, 220_000, 220_000, 220_000], 0.05, 5)

    expect(schedule).toHaveLength(5)
    // 不管中间计算如何，最后一期endCost必须=0
    expect(schedule[4].endCost).toBe(0)
  })

  it('EIR=0：全部还款归还本金，无融资费用', () => {
    const schedule = generateSchedule(1_000_000, [250_000, 250_000, 250_000, 250_000], 0.0, 4)

    expect(schedule).toHaveLength(4)
    // 非最后一期：摊销=0（EIR=0）
    expect(schedule[0].amortization).toBe(0)
    expect(schedule[1].amortization).toBe(0)
    expect(schedule[2].amortization).toBe(0)
    // 最后一期尾差调整
    expect(schedule[3].endCost).toBe(0)
  })
})

describe('useL5AmortizationEngine — validateSchedule', () => {
  it('valid：最后一期endCost=0', () => {
    const schedule = generateSchedule(1_000_000, Array(5).fill(230_975), 0.05, 5)
    const result = validateSchedule(schedule)

    expect(result.isValid).toBe(true)
    expect(result.tailDiff).toBe(0) // 尾差调整后强制=0
  })

  it('invalid：空摊销表', () => {
    const result = validateSchedule([])

    expect(result.isValid).toBe(false)
    expect(result.tailDiff).toBe(0)
  })

  it('valid after 尾差调整：不精确还款仍通过', () => {
    const schedule = generateSchedule(500_000, [120_000, 120_000, 120_000, 120_000, 120_000], 0.06, 5)
    const result = validateSchedule(schedule)

    expect(result.isValid).toBe(true)
    expect(Math.abs(result.tailDiff)).toBeLessThan(1)
  })
})
