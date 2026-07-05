/**
 * Unit Tests — G7 长期股权投资(权益法组) 公式引擎
 *
 * Spec: .kiro/specs/g7-long-term-equity-method/ Task 1.2
 * 9个纯函数 + parseNum 的单元测试（具体实例+边界）
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcInvestmentCost,
  calcShareOfNetAssets,
  calcGoodwill,
  calcAdjustedNetProfit,
  calcEquityShare,
  calcEquityMethodBalance,
  calcUnrealizedProfit,
  calcEliminationAmount,
  calcImpairmentAmount,
} from '../useG7EquityMethodFormulaEngine'

// ═══════════════════════════════════════════════════════════════════
// parseNum 单元测试
// ═══════════════════════════════════════════════════════════════════

describe('useG7EquityMethodFormulaEngine — parseNum', () => {
  it('null/undefined/empty → 0', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
  })

  it('whitespace-only string → 0', () => {
    expect(parseNum('  ')).toBe(0)
    expect(parseNum('\t')).toBe(0)
  })

  it('NaN/Infinity → 0', () => {
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum(Infinity)).toBe(0)
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('non-numeric string → 0', () => {
    expect(parseNum('abc')).toBe(0)
    expect(parseNum('12.3.4')).toBe(0)
  })

  it('valid numbers pass through', () => {
    expect(parseNum(0)).toBe(0)
    expect(parseNum(123.45)).toBe(123.45)
    expect(parseNum(-99.9)).toBe(-99.9)
  })

  it('numeric strings parse correctly', () => {
    expect(parseNum('100')).toBe(100)
    expect(parseNum(' -50.5 ')).toBe(-50.5)
    expect(parseNum('0')).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcInvestmentCost 单元测试
// ═══════════════════════════════════════════════════════════════════

describe('useG7EquityMethodFormulaEngine — calcInvestmentCost', () => {
  it('基本: 支付对价 + 直接费用', () => {
    expect(calcInvestmentCost(1000000, 50000)).toBe(1050000)
  })

  it('保留2位小数', () => {
    expect(calcInvestmentCost(100.123, 200.456)).toBe(300.58)
  })

  it('零值', () => {
    expect(calcInvestmentCost(0, 0)).toBe(0)
  })

  it('处理 NaN 输入', () => {
    expect(calcInvestmentCost(NaN as any, 100)).toBe(100)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcShareOfNetAssets 单元测试
// ═══════════════════════════════════════════════════════════════════

describe('useG7EquityMethodFormulaEngine — calcShareOfNetAssets', () => {
  it('基本: 净资产FV × 持股比例', () => {
    expect(calcShareOfNetAssets(5000000, 0.3)).toBe(1500000)
  })

  it('保留2位小数', () => {
    expect(calcShareOfNetAssets(1000000, 0.333)).toBe(333000)
  })

  it('比例为0 → 0', () => {
    expect(calcShareOfNetAssets(5000000, 0)).toBe(0)
  })

  it('净资产为0 → 0', () => {
    expect(calcShareOfNetAssets(0, 0.5)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcGoodwill 单元测试
// ═══════════════════════════════════════════════════════════════════

describe('useG7EquityMethodFormulaEngine — calcGoodwill', () => {
  it('正值=商誉', () => {
    expect(calcGoodwill(2000000, 1500000)).toBe(500000)
  })

  it('负值=营业外收入', () => {
    expect(calcGoodwill(1000000, 1500000)).toBe(-500000)
  })

  it('相等=0（无差额）', () => {
    expect(calcGoodwill(1500000, 1500000)).toBe(0)
  })

  it('保留2位小数', () => {
    expect(calcGoodwill(100.567, 50.123)).toBe(50.44)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcAdjustedNetProfit 单元测试
// ═══════════════════════════════════════════════════════════════════

describe('useG7EquityMethodFormulaEngine — calcAdjustedNetProfit', () => {
  it('基本: 报告 - 内部交易 - FV折旧 + 政策 + 其他', () => {
    // 10000 - 1000 - 500 + 200 + 100 = 8800
    expect(calcAdjustedNetProfit(10000, 1000, 500, 200, 100)).toBe(8800)
  })

  it('全零输入 → 0', () => {
    expect(calcAdjustedNetProfit(0, 0, 0, 0, 0)).toBe(0)
  })

  it('负调整（负数表示反向）', () => {
    // 5000 - (-100) - (-200) + (-300) + (-50)
    // = 5000 + 100 + 200 - 300 - 50 = 4950
    expect(calcAdjustedNetProfit(5000, -100, -200, -300, -50)).toBe(4950)
  })

  it('保留2位小数', () => {
    expect(calcAdjustedNetProfit(100.111, 20.222, 10.333, 5.444, 3.555)).toBe(78.56)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcEquityShare 单元测试
// ═══════════════════════════════════════════════════════════════════

describe('useG7EquityMethodFormulaEngine — calcEquityShare', () => {
  it('基本: 值 × 持股比例', () => {
    expect(calcEquityShare(8800, 0.3)).toBe(2640)
  })

  it('零比例 → 0', () => {
    expect(calcEquityShare(100000, 0)).toBe(0)
  })

  it('零值 → 0', () => {
    expect(calcEquityShare(0, 0.5)).toBe(0)
  })

  it('保留2位小数', () => {
    expect(calcEquityShare(10000, 0.333)).toBe(3330)
  })

  it('负值（亏损情况）', () => {
    expect(calcEquityShare(-5000, 0.4)).toBe(-2000)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcEquityMethodBalance 单元测试
// ═══════════════════════════════════════════════════════════════════

describe('useG7EquityMethodFormulaEngine — calcEquityMethodBalance', () => {
  it('基本: 期初 + 收益 + OCI + 其他权益 - 股利', () => {
    // 1000000 + 264000 + 50000 + 30000 - 100000 = 1244000
    expect(calcEquityMethodBalance(1000000, 264000, 50000, 30000, 100000)).toBe(1244000)
  })

  it('全零 → 0', () => {
    expect(calcEquityMethodBalance(0, 0, 0, 0, 0)).toBe(0)
  })

  it('只有期初和股利', () => {
    expect(calcEquityMethodBalance(500000, 0, 0, 0, 100000)).toBe(400000)
  })

  it('保留2位小数', () => {
    expect(calcEquityMethodBalance(100.11, 50.22, 30.33, 20.44, 10.55)).toBe(190.55)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcUnrealizedProfit 单元测试
// ═══════════════════════════════════════════════════════════════════

describe('useG7EquityMethodFormulaEngine — calcUnrealizedProfit', () => {
  it('基本: 交易金额 × 毛利率', () => {
    expect(calcUnrealizedProfit(1000000, 0.2)).toBe(200000)
  })

  it('零毛利率 → 0', () => {
    expect(calcUnrealizedProfit(500000, 0)).toBe(0)
  })

  it('保留2位小数', () => {
    // 333333 × 0.15 = 49999.95
    expect(calcUnrealizedProfit(333333, 0.15)).toBe(49999.95)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcEliminationAmount 单元测试
// ═══════════════════════════════════════════════════════════════════

describe('useG7EquityMethodFormulaEngine — calcEliminationAmount', () => {
  it('顺流(downstream): 全额抵销', () => {
    expect(calcEliminationAmount('downstream', 200000, 0.3)).toBe(200000)
  })

  it('逆流(upstream): 按持股比例', () => {
    expect(calcEliminationAmount('upstream', 200000, 0.3)).toBe(60000)
  })

  it('顺流: 比例不影响结果', () => {
    expect(calcEliminationAmount('downstream', 100000, 0.5)).toBe(100000)
    expect(calcEliminationAmount('downstream', 100000, 0.9)).toBe(100000)
  })

  it('逆流: 保留2位小数', () => {
    expect(calcEliminationAmount('upstream', 100000, 0.333)).toBe(33300)
  })

  it('零利润 → 0', () => {
    expect(calcEliminationAmount('downstream', 0, 0.5)).toBe(0)
    expect(calcEliminationAmount('upstream', 0, 0.5)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════
// calcImpairmentAmount 单元测试
// ═══════════════════════════════════════════════════════════════════

describe('useG7EquityMethodFormulaEngine — calcImpairmentAmount', () => {
  it('账面 > 可收回 → 正值减值', () => {
    expect(calcImpairmentAmount(1000000, 800000)).toBe(200000)
  })

  it('账面 < 可收回 → 0（无减值）', () => {
    expect(calcImpairmentAmount(800000, 1000000)).toBe(0)
  })

  it('账面 = 可收回 → 0', () => {
    expect(calcImpairmentAmount(500000, 500000)).toBe(0)
  })

  it('结果永远 ≥ 0', () => {
    expect(calcImpairmentAmount(100, 999999)).toBe(0)
    expect(calcImpairmentAmount(0, 100)).toBe(0)
  })

  it('保留2位小数', () => {
    expect(calcImpairmentAmount(100.567, 50.123)).toBe(50.44)
  })
})
