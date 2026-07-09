/**
 * Unit Tests — H9 租赁负债公式引擎 + 摊销引擎 + 现值引擎
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 7.1
 *
 * 已知值验证，互补 PBT 测试（h9LeaseLiabilities.pbt.spec.ts）
 * 和摊销引擎专属测试（useH9AmortizationEngine.spec.ts）。
 * 覆盖 Properties P1~P8 的具体场景 + 边界/跨引擎验证。
 *
 * **Validates: Requirements P1-P8**
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcContraLiabilityEndBalance,
  calcNetLiability,
  calcSubtotal,
  calcPriceDiffRate,
} from '../useH9FormulaEngine'
import {
  calcInterest,
  calcPrincipal,
  calcEndBalance,
  generateSchedule,
  validateSchedule,
} from '../useH9AmortizationEngine'
import {
  calcPresentValue,
  calcAnnuityPV,
  calcIBR,
} from '../useH9PVEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// useH9FormulaEngine — 负债类公式引擎
// ═══════════════════════════════════════════════════════════════════════════════

describe('useH9FormulaEngine', () => {
  // ── calcAuditedAmount (P1) ──────────────────────────────────────────────

  describe('calcAuditedAmount', () => {
    it('已知值: 50000 + 3000 + (-1000) = 52000', () => {
      expect(calcAuditedAmount(50000, 3000, -1000)).toBe(52000)
    })

    it('全零: 0 + 0 + 0 = 0', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('负AJE+负RJE: 100000 + (-5000) + (-2000) = 93000', () => {
      expect(calcAuditedAmount(100000, -5000, -2000)).toBe(93000)
    })

    it('大金额: 999999999 + 1 + 0 = 1000000000', () => {
      expect(calcAuditedAmount(999999999, 1, 0)).toBe(1000000000)
    })
  })

  // ── calcLiabilityEndBalance (P2) ────────────────────────────────────────

  describe('calcLiabilityEndBalance', () => {
    it('负债类方向: 期末=期初+贷方-借方: 500000 + 100000 - 80000 = 520000', () => {
      expect(calcLiabilityEndBalance(500000, 100000, 80000)).toBe(520000)
    })

    it('全零: 0 + 0 - 0 = 0', () => {
      expect(calcLiabilityEndBalance(0, 0, 0)).toBe(0)
    })

    it('贷方增加大于借方减少（负债增长）: 200000 + 300000 - 50000 = 450000', () => {
      expect(calcLiabilityEndBalance(200000, 300000, 50000)).toBe(450000)
    })

    it('借方减少大于贷方增加（负债减少）: 200000 + 50000 - 300000 = -50000', () => {
      expect(calcLiabilityEndBalance(200000, 50000, 300000)).toBe(-50000)
    })

    it('无贷方发生（仅偿还）: 1000000 + 0 - 120000 = 880000', () => {
      expect(calcLiabilityEndBalance(1000000, 0, 120000)).toBe(880000)
    })
  })

  // ── calcContraLiabilityEndBalance ───────────────────────────────────────

  describe('calcContraLiabilityEndBalance', () => {
    it('备抵类方向: 期末=期初+借方-贷方: 80000 + 5000 - 20000 = 65000', () => {
      expect(calcContraLiabilityEndBalance(80000, 5000, 20000)).toBe(65000)
    })

    it('全零: 0 + 0 - 0 = 0', () => {
      expect(calcContraLiabilityEndBalance(0, 0, 0)).toBe(0)
    })

    it('仅贷方摊销（未确认融资费用减少）: 100000 + 0 - 15000 = 85000', () => {
      expect(calcContraLiabilityEndBalance(100000, 0, 15000)).toBe(85000)
    })

    it('贷方大于借方+期初（结果为负）: 10000 + 0 - 50000 = -40000', () => {
      expect(calcContraLiabilityEndBalance(10000, 0, 50000)).toBe(-40000)
    })
  })

  // ── calcNetLiability ────────────────────────────────────────────────────

  describe('calcNetLiability', () => {
    it('净额 = 负债原值 - 未确认融资费用: 500000 - 80000 = 420000', () => {
      expect(calcNetLiability(500000, 80000)).toBe(420000)
    })

    it('无未确认融资费用: 300000 - 0 = 300000', () => {
      expect(calcNetLiability(300000, 0)).toBe(300000)
    })

    it('全零: 0 - 0 = 0', () => {
      expect(calcNetLiability(0, 0)).toBe(0)
    })

    it('融资费用大于负债（异常但数学允许）: 100000 - 150000 = -50000', () => {
      expect(calcNetLiability(100000, 150000)).toBe(-50000)
    })
  })

  // ── calcSubtotal ────────────────────────────────────────────────────────

  describe('calcSubtotal', () => {
    it('已知值: [100000, 200000, 50000] = 350000', () => {
      expect(calcSubtotal([100000, 200000, 50000])).toBe(350000)
    })

    it('空数组: [] = 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('含负数: [500000, -100000, 200000, -50000] = 550000', () => {
      expect(calcSubtotal([500000, -100000, 200000, -50000])).toBe(550000)
    })

    it('单元素: [12345] = 12345', () => {
      expect(calcSubtotal([12345])).toBe(12345)
    })

    it('全零: [0, 0, 0] = 0', () => {
      expect(calcSubtotal([0, 0, 0])).toBe(0)
    })
  })

  // ── calcPriceDiffRate ───────────────────────────────────────────────────

  describe('calcPriceDiffRate', () => {
    it('正价差: (120000 - 100000) / 100000 × 100 = 20%', () => {
      expect(calcPriceDiffRate(120000, 100000)).toBe(20)
    })

    it('负价差（低于市场）: (80000 - 100000) / 100000 × 100 = -20%', () => {
      expect(calcPriceDiffRate(80000, 100000)).toBe(-20)
    })

    it('价格相同: (100000 - 100000) / 100000 × 100 = 0%', () => {
      expect(calcPriceDiffRate(100000, 100000)).toBe(0)
    })

    it('市场价为0时避免除零返回0', () => {
      expect(calcPriceDiffRate(50000, 0)).toBe(0)
    })

    it('实际租金为0: (0 - 100000) / 100000 × 100 = -100%', () => {
      expect(calcPriceDiffRate(0, 100000)).toBe(-100)
    })

    it('负值输入: (-50000 - 100000) / 100000 × 100 = -150%', () => {
      expect(calcPriceDiffRate(-50000, 100000)).toBe(-150)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useH9PVEngine — 现值计算引擎
// ═══════════════════════════════════════════════════════════════════════════════

describe('useH9PVEngine', () => {
  // ── calcPresentValue (P7, P8) ───────────────────────────────────────────

  describe('calcPresentValue', () => {
    it('空数组返回0', () => {
      expect(calcPresentValue([], 0.05)).toBe(0)
    })

    it('rate=0时PV=Σpayments (P8)', () => {
      expect(calcPresentValue([10000, 20000, 30000], 0)).toBe(60000)
    })

    it('单期折现: 10000/(1+0.05)^1 = 9523.81...', () => {
      const pv = calcPresentValue([10000], 0.05)
      expect(pv).toBeCloseTo(10000 / 1.05, 10)
    })

    it('已知两期折现: [10000, 10000] @ 10%', () => {
      // PV = 10000/1.1 + 10000/1.21 = 9090.909... + 8264.462... = 17355.37...
      const pv = calcPresentValue([10000, 10000], 0.10)
      const expected = 10000 / 1.1 + 10000 / 1.21
      expect(pv).toBeCloseTo(expected, 8)
    })

    it('不等额: [50000, 50000, 100000] @ 5%', () => {
      const pv = calcPresentValue([50000, 50000, 100000], 0.05)
      const expected = 50000 / 1.05 + 50000 / Math.pow(1.05, 2) + 100000 / Math.pow(1.05, 3)
      expect(pv).toBeCloseTo(expected, 8)
    })

    it('高利率折现效果显著: [100000] @ 50%', () => {
      const pv = calcPresentValue([100000], 0.50)
      expect(pv).toBeCloseTo(100000 / 1.5, 10)
    })

    it('多期等额验证与calcAnnuityPV一致: 12期×10000 @ 4%', () => {
      const payments = Array(12).fill(10000)
      const pvFromArray = calcPresentValue(payments, 0.04)
      const pvFromAnnuity = calcAnnuityPV(10000, 0.04, 12)
      expect(pvFromArray).toBeCloseTo(pvFromAnnuity, 6)
    })
  })

  // ── calcAnnuityPV (P7) ──────────────────────────────────────────────────

  describe('calcAnnuityPV', () => {
    it('periods=0返回0', () => {
      expect(calcAnnuityPV(10000, 0.05, 0)).toBe(0)
    })

    it('payment=0返回0', () => {
      expect(calcAnnuityPV(0, 0.05, 12)).toBe(0)
    })

    it('rate=0时退化为payment×periods', () => {
      expect(calcAnnuityPV(10000, 0, 12)).toBe(120000)
    })

    it('已知值: 10000/期 × 5% × 12期 = 88632.76...', () => {
      // PV = 10000 × (1 - 1.05^-12) / 0.05 = 10000 × 8.863252... = 88632.52...
      const pv = calcAnnuityPV(10000, 0.05, 12)
      const expected = 10000 * (1 - Math.pow(1.05, -12)) / 0.05
      expect(pv).toBeCloseTo(expected, 6)
    })

    it('月付款换算: 50000/月 × (4.35%/12)/期 × 36期', () => {
      const monthlyRate = 0.0435 / 12
      const pv = calcAnnuityPV(50000, monthlyRate, 36)
      const expected = 50000 * (1 - Math.pow(1 + monthlyRate, -36)) / monthlyRate
      expect(pv).toBeCloseTo(expected, 4)
    })

    it('单期年金=单期折现: payment/(1+rate)', () => {
      const pv = calcAnnuityPV(100000, 0.08, 1)
      expect(pv).toBeCloseTo(100000 / 1.08, 8)
    })

    it('负periods返回0', () => {
      expect(calcAnnuityPV(10000, 0.05, -1)).toBe(0)
    })
  })

  // ── calcIBR ─────────────────────────────────────────────────────────────

  describe('calcIBR', () => {
    it('IBR = 市场基准 + 信用利差 + 期限调整: 0.035 + 0.01 + 0.005 = 0.05', () => {
      expect(calcIBR(0.035, 0.01, 0.005)).toBeCloseTo(0.05, 10)
    })

    it('全零: 0 + 0 + 0 = 0', () => {
      expect(calcIBR(0, 0, 0)).toBe(0)
    })

    it('仅市场基准: 0.04 + 0 + 0 = 0.04', () => {
      expect(calcIBR(0.04, 0, 0)).toBe(0.04)
    })

    it('负期限调整（短期折让）: 0.04 + 0.015 + (-0.005) = 0.05', () => {
      expect(calcIBR(0.04, 0.015, -0.005)).toBeCloseTo(0.05, 10)
    })

    it('高信用利差: 0.035 + 0.05 + 0.01 = 0.095', () => {
      expect(calcIBR(0.035, 0.05, 0.01)).toBeCloseTo(0.095, 10)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 跨引擎组合验证 — PV → generateSchedule → validate
// ═══════════════════════════════════════════════════════════════════════════════

describe('Cross-Engine Validation', () => {
  it('PV计算初始确认 → 摊销表 → 验证末期归零', () => {
    // 场景：年付120000，利率5%，3年租赁
    const payment = 120000
    const rate = 0.05
    const periods = 3

    // 1. 计算初始确认（现值）
    const initialBalance = calcAnnuityPV(payment, rate, periods)
    expect(initialBalance).toBeGreaterThan(0)

    // 2. 生成摊销表
    const schedule = generateSchedule(initialBalance, payment, rate, periods)
    expect(schedule).toHaveLength(3)

    // 3. 验证第一期: 利息=初始×利率
    expect(schedule[0].interest).toBeCloseTo(initialBalance * rate, 8)

    // 4. 验证最后一期归零
    const validation = validateSchedule(schedule)
    expect(validation.isValid).toBe(true)
    expect(Math.abs(validation.tailDiff)).toBeLessThan(1)
  })

  it('IBR确定 → PV → 摊销表完整流程', () => {
    // 场景：LPR 3.85% + 信用利差1.5% + 期限调整0.15% = 5.5%
    const ibr = calcIBR(0.0385, 0.015, 0.0015)
    expect(ibr).toBeCloseTo(0.055, 10)

    // 月化
    const monthlyRate = ibr / 12
    const monthlyPayment = 8000
    const months = 24

    // PV
    const pv = calcAnnuityPV(monthlyPayment, monthlyRate, months)
    expect(pv).toBeGreaterThan(0)
    expect(pv).toBeLessThan(monthlyPayment * months) // 折现后 < 名义总额

    // 摊销表
    const schedule = generateSchedule(pv, monthlyPayment, monthlyRate, months)
    expect(schedule).toHaveLength(24)
    expect(validateSchedule(schedule).isValid).toBe(true)
  })

  it('负债净额 = 审定表负债 - 未确认融资费用', () => {
    // 模拟审定表数据
    const liabilityEnd = calcLiabilityEndBalance(500000, 0, 120000) // 期初50万-偿还12万
    const financeCostEnd = calcContraLiabilityEndBalance(80000, 0, 20000) // 期初8万-摊销2万
    const netLiability = calcNetLiability(liabilityEnd, financeCostEnd)

    expect(liabilityEnd).toBe(380000)
    expect(financeCostEnd).toBe(60000)
    expect(netLiability).toBe(320000)
  })

  it('摊销表利息合计 = 总付款 - 初始余额（无尾差时）', () => {
    // 利率为0时：总利息=0, 总付款=初始余额
    const schedule = generateSchedule(30000, 10000, 0, 3)
    const totalInterest = schedule.reduce((s, r) => s + r.interest, 0)
    expect(totalInterest).toBe(0)

    // 正常利率: 利息合计 ≈ 总实际付款 - 初始余额
    const schedule2 = generateSchedule(100000, 12000, 0.05, 12)
    const totalPaid = schedule2.reduce((s, r) => s + r.payment, 0)
    const totalInt = schedule2.reduce((s, r) => s + r.interest, 0)
    // 总付款 - 初始余额 ≈ 总利息（尾差调整导致最后一期付款不同）
    expect(totalInt).toBeCloseTo(totalPaid - 100000, 6)
  })

  it('calcSubtotal与摊销表结合：利息汇总', () => {
    const schedule = generateSchedule(200000, 25000, 0.04, 10)
    const interests = schedule.map(r => r.interest)
    const totalInterest = calcSubtotal(interests)
    expect(totalInterest).toBeGreaterThan(0)
    // 逐行求和应等于reduce
    expect(totalInterest).toBe(interests.reduce((a, b) => a + b, 0))
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 边界条件测试
// ═══════════════════════════════════════════════════════════════════════════════

describe('Edge Cases', () => {
  describe('rate=0', () => {
    it('calcInterest(any, 0) = 0', () => {
      expect(calcInterest(1000000, 0)).toBe(0)
    })

    it('calcAnnuityPV退化为简单乘法', () => {
      expect(calcAnnuityPV(10000, 0, 5)).toBe(50000)
    })

    it('calcPresentValue无折现', () => {
      expect(calcPresentValue([100, 200, 300], 0)).toBe(600)
    })

    it('generateSchedule: 全部付款归本金', () => {
      const schedule = generateSchedule(50000, 10000, 0, 5)
      schedule.forEach(row => {
        expect(row.interest).toBe(0)
      })
      expect(schedule[schedule.length - 1].endBalance).toBe(0)
    })
  })

  describe('periods=0', () => {
    it('generateSchedule返回空数组', () => {
      expect(generateSchedule(100000, 10000, 0.05, 0)).toEqual([])
    })

    it('calcAnnuityPV返回0', () => {
      expect(calcAnnuityPV(10000, 0.05, 0)).toBe(0)
    })

    it('validateSchedule空数组有效', () => {
      expect(validateSchedule([]).isValid).toBe(true)
    })
  })

  describe('空数组', () => {
    it('calcSubtotal([]) = 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('calcPresentValue([], rate) = 0', () => {
      expect(calcPresentValue([], 0.05)).toBe(0)
    })
  })

  describe('零值', () => {
    it('calcLiabilityEndBalance全零', () => {
      expect(calcLiabilityEndBalance(0, 0, 0)).toBe(0)
    })

    it('calcContraLiabilityEndBalance全零', () => {
      expect(calcContraLiabilityEndBalance(0, 0, 0)).toBe(0)
    })

    it('calcNetLiability(0, 0) = 0', () => {
      expect(calcNetLiability(0, 0)).toBe(0)
    })

    it('calcPriceDiffRate(0, 0) = 0 (除零保护)', () => {
      expect(calcPriceDiffRate(0, 0)).toBe(0)
    })

    it('calcIBR(0, 0, 0) = 0', () => {
      expect(calcIBR(0, 0, 0)).toBe(0)
    })
  })

  describe('负数输入', () => {
    it('calcAuditedAmount允许负AJE/RJE', () => {
      expect(calcAuditedAmount(100000, -30000, -20000)).toBe(50000)
    })

    it('calcLiabilityEndBalance负期初', () => {
      expect(calcLiabilityEndBalance(-10000, 5000, 3000)).toBe(-8000)
    })

    it('calcPriceDiffRate负实际租金', () => {
      expect(calcPriceDiffRate(-10000, 100000)).toBeCloseTo(-110, 10)
    })

    it('calcPresentValue负付款', () => {
      // 负付款代表退款/激励
      const pv = calcPresentValue([-10000], 0.05)
      expect(pv).toBeCloseTo(-10000 / 1.05, 10)
    })
  })

  describe('除零保护', () => {
    it('calcPriceDiffRate市场价=0时返回0', () => {
      expect(calcPriceDiffRate(999999, 0)).toBe(0)
    })
  })
})
