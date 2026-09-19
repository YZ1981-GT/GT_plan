/**
 * 单元测试 — useM3FormulaEngine + useM3FxEngine + useM3TreasuryEngine
 *
 * 覆盖 edge cases 与特定审计业务场景（PBT 无法覆盖的非随机边界）：
 * - NaN/null/undefined 安全处理（safe helper）
 * - 零金额
 * - 大数运算
 * - 负值场景
 * - 权益备抵借方方向验证
 * - cancelDiff > 0 需进一步冲减 M5/M6
 *
 * Spec: .kiro/specs/m3-treasury-stock/ Task 7.1
 * Requirements: P1-P6
 *
 * 科目：4002 库存股（**借方/权益备抵类！期末=期初+借方-贷方**）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcContraEquityEndBalance,
  calcSubtotal,
} from '../composables/useM3FormulaEngine'
import { calcFxConverted, calcFxDiff } from '../composables/useM3FxEngine'
import { calcRepurchaseAmount, calcCancelDiff } from '../composables/useM3TreasuryEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: useM3FormulaEngine — 审定数 (P1)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useM3FormulaEngine — calcAuditedAmount (P1)', () => {
  it('标准场景: 100 + 20 + (-5) = 115', () => {
    expect(calcAuditedAmount(100, 20, -5)).toBe(115)
  })

  it('全零: 0 + 0 + 0 = 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('AJE 负值调减: 1000000 + (-200000) + 0 = 800000', () => {
    expect(calcAuditedAmount(1_000_000, -200_000, 0)).toBe(800_000)
  })

  it('大数: 9999999999 + 1 + 0 = 10000000000', () => {
    expect(calcAuditedAmount(9_999_999_999, 1, 0)).toBe(10_000_000_000)
  })

  it('NaN 输入视为 0', () => {
    expect(calcAuditedAmount(NaN as any, 100, 50)).toBe(150)
  })

  it('undefined 输入视为 0', () => {
    expect(calcAuditedAmount(undefined as any, undefined as any, undefined as any)).toBe(0)
  })

  it('null 输入视为 0', () => {
    expect(calcAuditedAmount(null as any, 300, null as any)).toBe(300)
  })

  it('Infinity 输入视为 0', () => {
    expect(calcAuditedAmount(Infinity as any, 100, 50)).toBe(150)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: useM3FormulaEngine — 权益备抵类期末 (P2)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useM3FormulaEngine — calcContraEquityEndBalance (P2, 备抵借方！)', () => {
  it('标准回购场景: 期初500万+借方(回购)200万-贷方(注销)100万=600万', () => {
    expect(calcContraEquityEndBalance(5_000_000, 2_000_000, 1_000_000)).toBe(6_000_000)
  })

  it('仅回购无注销: 期初300万+借方100万-贷方0=400万(备抵借方增加)', () => {
    expect(calcContraEquityEndBalance(3_000_000, 1_000_000, 0)).toBe(4_000_000)
  })

  it('仅注销无回购: 期初500万+借方0-贷方200万=300万(备抵借方减少)', () => {
    expect(calcContraEquityEndBalance(5_000_000, 0, 2_000_000)).toBe(3_000_000)
  })

  it('注销大于期初+回购: 结果为负(异常但公式允许)', () => {
    // 期初100万+回购50万-注销200万=-50万
    expect(calcContraEquityEndBalance(1_000_000, 500_000, 2_000_000)).toBe(-500_000)
  })

  it('全零: 期末=0', () => {
    expect(calcContraEquityEndBalance(0, 0, 0)).toBe(0)
  })

  it('大数运算: 10亿级别', () => {
    expect(calcContraEquityEndBalance(1_000_000_000, 500_000_000, 200_000_000)).toBe(1_300_000_000)
  })

  it('null/undefined/NaN 安全处理', () => {
    expect(calcContraEquityEndBalance(null as any, 100, 50)).toBe(50) // 0+100-50
    expect(calcContraEquityEndBalance(1000, undefined as any, 500)).toBe(500) // 1000+0-500
    expect(calcContraEquityEndBalance(1000, NaN as any, NaN as any)).toBe(1000) // 1000+0-0
  })

  it('⚠️ 方向验证: 备抵借方 ≠ 权益贷方', () => {
    // 权益贷方(M2): 期末=期初+贷方-借方 → 1000+200-100=1100
    // 备抵借方(M3): 期末=期初+借方-贷方 → 1000+200-100=1100
    // 但语义完全不同！M2 的贷方是增资，M3 的借方是回购
    const begin = 1000, debit = 200, credit = 100
    const contraEnd = calcContraEquityEndBalance(begin, debit, credit)
    expect(contraEnd).toBe(1100)
    // 对比: 如果错误用贷方公式 begin+credit-debit = 1000+100-200=900
    const wrongEnd = begin + credit - debit
    expect(wrongEnd).toBe(900)
    expect(contraEnd).not.toBe(wrongEnd) // 证明方向差异
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: useM3FormulaEngine — 分类小计 (P6)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useM3FormulaEngine — calcSubtotal (P6)', () => {
  it('标准数组求和', () => {
    expect(calcSubtotal([100, 200, 300])).toBe(600)
  })

  it('空数组 → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('单元素', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('含负值', () => {
    expect(calcSubtotal([1000, -200, 500, -100])).toBe(1200)
  })

  it('含 NaN/undefined → 视为 0', () => {
    expect(calcSubtotal([100, NaN as any, 200, undefined as any])).toBe(300)
  })

  it('大数组(100元素)', () => {
    const arr = Array.from({ length: 100 }, (_, i) => i + 1) // 1+2+...+100=5050
    expect(calcSubtotal(arr)).toBe(5050)
  })

  it('非数组输入 → 0', () => {
    expect(calcSubtotal(null as any)).toBe(0)
    expect(calcSubtotal(undefined as any)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: useM3FxEngine — 外币折算 (P5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useM3FxEngine — calcFxConverted (P5)', () => {
  it('USD 10000 × 7.25 = 72500', () => {
    expect(calcFxConverted(10_000, 7.25)).toBe(72_500)
  })

  it('HKD 5000000 × 0.92 = 4600000', () => {
    expect(calcFxConverted(5_000_000, 0.92)).toBe(4_600_000)
  })

  it('原币为 0 → 折算 = 0', () => {
    expect(calcFxConverted(0, 7.25)).toBe(0)
  })

  it('汇率为 0 → 折算 = 0', () => {
    expect(calcFxConverted(10_000, 0)).toBe(0)
  })

  it('null 输入 → 0', () => {
    expect(calcFxConverted(null as any, 7.25)).toBe(0)
    expect(calcFxConverted(10_000, null as any)).toBe(0)
  })

  it('大额外币: 1亿 × 7.25 = 7.25亿', () => {
    expect(calcFxConverted(100_000_000, 7.25)).toBe(725_000_000)
  })
})

describe('useM3FxEngine — calcFxDiff', () => {
  it('折算>账面 → 正差异(审计关注)', () => {
    expect(calcFxDiff(72_500, 71_000)).toBe(1_500)
  })

  it('折算<账面 → 负差异', () => {
    expect(calcFxDiff(71_000, 72_500)).toBe(-1_500)
  })

  it('折算=账面 → 差异=0', () => {
    expect(calcFxDiff(72_500, 72_500)).toBe(0)
  })

  it('两者均为 0 → 差异=0', () => {
    expect(calcFxDiff(0, 0)).toBe(0)
  })

  it('null 安全', () => {
    expect(calcFxDiff(null as any, 1000)).toBe(-1000)
    expect(calcFxDiff(1000, null as any)).toBe(1000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: useM3TreasuryEngine — 回购金额 (P3)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useM3TreasuryEngine — calcRepurchaseAmount (P3)', () => {
  it('标准回购: 10万股 × 25元 = 250万', () => {
    expect(calcRepurchaseAmount(100_000, 25)).toBe(2_500_000)
  })

  it('大宗回购: 1亿股 × 10元 = 10亿', () => {
    expect(calcRepurchaseAmount(100_000_000, 10)).toBe(1_000_000_000)
  })

  it('零股数 → 0', () => {
    expect(calcRepurchaseAmount(0, 25)).toBe(0)
  })

  it('零单价 → 0', () => {
    expect(calcRepurchaseAmount(100_000, 0)).toBe(0)
  })

  it('小数单价(精确到分): 1000股 × 15.67元 = 15670', () => {
    expect(calcRepurchaseAmount(1000, 15.67)).toBeCloseTo(15_670, 2)
  })

  it('null/undefined → 0', () => {
    expect(calcRepurchaseAmount(null as any, 25)).toBe(0)
    expect(calcRepurchaseAmount(100_000, undefined as any)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 6: useM3TreasuryEngine — 注销冲减差额 (P4)
// ═══════════════════════════════════════════════════════════════════════════════

describe('useM3TreasuryEngine — calcCancelDiff (P4)', () => {
  it('完全冲减: 注销250万-冲减M2(100万)-冲减M4(150万) = 0', () => {
    expect(calcCancelDiff(2_500_000, 1_000_000, 1_500_000)).toBe(0)
  })

  it('差额>0: 资本公积不足→需进一步冲减M5/M6', () => {
    // 注销250万, 冲减实收资本100万, 冲减资本公积120万, 差额30万→M5/M6
    const diff = calcCancelDiff(2_500_000, 1_000_000, 1_200_000)
    expect(diff).toBe(300_000)
    expect(diff).toBeGreaterThan(0) // 需进一步冲减盈余公积/未分配利润
  })

  it('差额<0: 冲减过多(异常但公式允许计算)', () => {
    // 注销200万, 冲减M2(150万)+M4(100万)=250万 > 注销200万
    const diff = calcCancelDiff(2_000_000, 1_500_000, 1_000_000)
    expect(diff).toBe(-500_000)
    expect(diff).toBeLessThan(0)
  })

  it('全零 → 0', () => {
    expect(calcCancelDiff(0, 0, 0)).toBe(0)
  })

  it('仅注销无冲减: 差额=注销金额全额', () => {
    expect(calcCancelDiff(1_000_000, 0, 0)).toBe(1_000_000)
  })

  it('大数: 10亿级别注销', () => {
    expect(calcCancelDiff(1_000_000_000, 500_000_000, 400_000_000)).toBe(100_000_000)
  })

  it('null/undefined 安全', () => {
    expect(calcCancelDiff(null as any, 100, 50)).toBe(-150) // 0-100-50
    expect(calcCancelDiff(1000, null as any, null as any)).toBe(1000) // 1000-0-0
  })

  it('审计场景: 资本公积不足冲减的典型案例', () => {
    // 回购成本30元/股 × 10万股 = 300万
    // 面值1元/股 × 10万股 = 10万 → 冲减实收资本(M2)
    // 资本溢价15元/股 × 10万股 = 150万 → 冲减资本公积(M4)
    // 差额 = 300万 - 10万 - 150万 = 140万 → 冲减盈余公积(M5)/未分配利润(M6)
    const cancelAmount = 3_000_000  // 回购成本
    const deductCapital = 100_000   // 冲减实收资本(面值)
    const deductReserve = 1_500_000 // 冲减资本公积(溢价)
    const diff = calcCancelDiff(cancelAmount, deductCapital, deductReserve)
    expect(diff).toBe(1_400_000) // 需进一步冲减M5/M6
    expect(diff).toBeGreaterThan(0)
  })
})
