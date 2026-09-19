/**
 * n2VatSourceEngine.spec.ts — N2-6 增值税测算表纯函数引擎守卫
 *
 * Task 5.1: 逐公式定值断言 + 跨段 F30/F39 源模板算例 + PBT 恒等式
 * Requirements: 8.2
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  parseNum,
  calcDeclarationDiff,
  calcTaxableRevenue,
  calcOutputTax,
  calcInputTax,
  calcOutputVariance,
  calcInputVariance,
  calcVatPayableFromDeclaration,
  N2_VAT_RATE_OPTIONS,
  N2_VAT_DECLARATION_ITEMS,
  N2_VAT_SPECIAL_ITEMS,
  N2_VAT_BOOK_OUTPUT_KEY,
  N2_VAT_BOOK_INPUT_KEY,
} from '../useN2VatSourceEngine'

// ─── 金额域生成器（收敛，禁无界 float） ─────────────────────────────────────

const amountArb = fc.float({ min: Math.fround(-1e12), max: Math.fround(1e12), noNaN: true }).filter(Number.isFinite)

// ─── parseNum 边界测试 ──────────────────────────────────────────────────────

describe('parseNum 边界', () => {
  it('NaN → 0', () => {
    expect(parseNum(NaN)).toBe(0)
  })

  it('Infinity → 0', () => {
    expect(parseNum(Infinity)).toBe(0)
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('undefined → 0', () => {
    expect(parseNum(undefined)).toBe(0)
  })

  it('null → 0', () => {
    expect(parseNum(null)).toBe(0)
  })

  it('空字符串 → 0', () => {
    expect(parseNum('')).toBe(0)
  })

  it('非数字字符串 → 0', () => {
    expect(parseNum('abc')).toBe(0)
    expect(parseNum('hello world')).toBe(0)
  })

  it('"Infinity" 字符串 → 0（Number.isFinite 守卫）', () => {
    expect(parseNum('Infinity')).toBe(0)
    expect(parseNum('-Infinity')).toBe(0)
  })

  it('"1e400" 溢出字面量 → 0', () => {
    expect(parseNum('1e400')).toBe(0)
  })

  it('JSON 数字字符串 → 正确值', () => {
    expect(parseNum('123.45')).toBe(123.45)
    expect(parseNum('-678.9')).toBe(-678.9)
    expect(parseNum('0')).toBe(0)
  })

  it('数字直传 → 原值', () => {
    expect(parseNum(42)).toBe(42)
    expect(parseNum(-3.14)).toBe(-3.14)
    expect(parseNum(0)).toBe(0)
  })
})

// ─── 逐公式定值断言 ─────────────────────────────────────────────────────────

describe('逐公式定值断言', () => {
  describe('calcDeclarationDiff（E = C − D）', () => {
    it('正常差异', () => {
      expect(calcDeclarationDiff(1000, 800)).toBe(200)
    })

    it('无差异', () => {
      expect(calcDeclarationDiff(500, 500)).toBe(0)
    })

    it('负差异', () => {
      expect(calcDeclarationDiff(300, 700)).toBe(-400)
    })
  })

  describe('calcTaxableRevenue（D = B − C）', () => {
    it('计税收入 = 销售额 − 免税销售额', () => {
      expect(calcTaxableRevenue(10000, 2000)).toBe(8000)
    })

    it('免税 = 0', () => {
      expect(calcTaxableRevenue(5000, 0)).toBe(5000)
    })

    it('全免税', () => {
      expect(calcTaxableRevenue(3000, 3000)).toBe(0)
    })
  })

  describe('calcOutputTax（F = D × E）', () => {
    it('应计销项税 = 计税收入 × 税率', () => {
      expect(calcOutputTax(8000, 0.13)).toBeCloseTo(1040, 2)
    })

    it('税率为 0', () => {
      expect(calcOutputTax(10000, 0)).toBe(0)
    })
  })

  describe('calcInputTax（F = D × E）', () => {
    it('测算数 = 发生额 × 税率', () => {
      expect(calcInputTax(50000, 0.13)).toBeCloseTo(6500, 2)
    })

    it('发生额为 0', () => {
      expect(calcInputTax(0, 0.13)).toBe(0)
    })
  })

  describe('calcOutputVariance（F30 = C17 − F28 − F29）', () => {
    it('源模板算例：C17=10000, F28=8000, F29=500 → 1500', () => {
      expect(calcOutputVariance(10000, 8000, 500)).toBe(1500)
    })

    it('无差异：C17 = F28 + F29', () => {
      expect(calcOutputVariance(5000, 3000, 2000)).toBe(0)
    })

    it('差异为负', () => {
      expect(calcOutputVariance(1000, 2000, 500)).toBe(-1500)
    })
  })

  describe('calcInputVariance（F39 = F35 − F36 − F37 − F38 − C18）', () => {
    it('源模板算例：F35=6500, F36=200, F37=100, F38=300, C18=5000 → 900', () => {
      expect(calcInputVariance(6500, { deductible: 200, uncertified: 100, retained: 300 }, 5000)).toBe(900)
    })

    it('无差异', () => {
      expect(calcInputVariance(1000, { deductible: 200, uncertified: 100, retained: 200 }, 500)).toBe(0)
    })

    it('adjust 为 null', () => {
      expect(calcInputVariance(1000, null, 800)).toBe(200)
    })

    it('adjust 为 undefined', () => {
      expect(calcInputVariance(1000, undefined, 600)).toBe(400)
    })
  })

  describe('calcVatPayableFromDeclaration（R6 = C17 − C18）', () => {
    it('应交增值税 = 销项税账面 − 进项税账面', () => {
      expect(calcVatPayableFromDeclaration(10000, 8000)).toBe(2000)
    })

    it('两侧相等 → 0', () => {
      expect(calcVatPayableFromDeclaration(5000, 5000)).toBe(0)
    })

    it('进项 > 销项 → 负（留抵）', () => {
      expect(calcVatPayableFromDeclaration(3000, 7000)).toBe(-4000)
    })
  })
})

// ─── 跨段 F30/F39 源模板综合算例 ────────────────────────────────────────────

describe('跨段综合算例', () => {
  it('（二）差异 F30 = C17 − F28 − F29，C17 取自（一）第6项销项税额账面', () => {
    // 模拟：（一）第6项「6.销项税额」账面=12000（即 C17）
    // （二）合计应计销项税 F28=9000，待转销项税额 F29=1000
    // F30 = 12000 − 9000 − 1000 = 2000
    const C17 = 12000
    const F28 = 9000
    const F29 = 1000
    expect(calcOutputVariance(C17, F28, F29)).toBe(2000)
  })

  it('（三）差异 F39 = F35 − F36 − F37 − F38 − C18，C18 取自（一）第7项进项税额账面', () => {
    // 模拟：（一）第7项「7.进项税额」账面=8000（即 C18）
    // （三）测算数合计 F35=10000，待抵扣 F36=500，待认证 F37=300，留抵 F38=200
    // F39 = 10000 − 500 − 300 − 200 − 8000 = 1000
    const C18 = 8000
    const F35 = 10000
    const adjust = { deductible: 500, uncertified: 300, retained: 200 }
    expect(calcInputVariance(F35, adjust, C18)).toBe(1000)
  })
})

// ─── PBT 恒等式（至少 3 条） ────────────────────────────────────────────────

describe('PBT 恒等式', () => {
  it('calcDeclarationDiff(a, b) === a - b（精度容差）', () => {
    fc.assert(
      fc.property(amountArb, amountArb, (a, b) => {
        const result = calcDeclarationDiff(a, b)
        const expected = a - b
        return Math.abs(result - expected) <= 1e-6
      }),
      { numRuns: 200 },
    )
  })

  it('calcTaxableRevenue(a, b) === parseNum(a) - parseNum(b)（直接减法恒等式）', () => {
    fc.assert(
      fc.property(amountArb, amountArb, (a, b) => {
        const result = calcTaxableRevenue(a, b)
        const expected = a - b
        // 两者完全相等（同一操作，无精度差）
        return result === expected
      }),
      { numRuns: 200 },
    )
  })

  it('calcVatPayableFromDeclaration(a, b) === a - b（精度容差）', () => {
    fc.assert(
      fc.property(amountArb, amountArb, (a, b) => {
        const result = calcVatPayableFromDeclaration(a, b)
        const expected = a - b
        return Math.abs(result - expected) <= 1e-6
      }),
      { numRuns: 200 },
    )
  })
})

// ─── 常量完整性 ─────────────────────────────────────────────────────────────

describe('常量完整性', () => {
  it('N2_VAT_DECLARATION_ITEMS 有 10 项', () => {
    expect(N2_VAT_DECLARATION_ITEMS).toHaveLength(10)
  })

  it('N2_VAT_SPECIAL_ITEMS 有 4 项', () => {
    expect(N2_VAT_SPECIAL_ITEMS).toHaveLength(4)
  })

  it('N2_VAT_BOOK_OUTPUT_KEY 指向第6项', () => {
    const item = N2_VAT_DECLARATION_ITEMS.find(i => i.key === N2_VAT_BOOK_OUTPUT_KEY)
    expect(item).toBeDefined()
    expect(item!.label).toBe('6.销项税额')
  })

  it('N2_VAT_BOOK_INPUT_KEY 指向第7项', () => {
    const item = N2_VAT_DECLARATION_ITEMS.find(i => i.key === N2_VAT_BOOK_INPUT_KEY)
    expect(item).toBeDefined()
    expect(item!.label).toBe('7.进项税额')
  })

  it('N2_VAT_RATE_OPTIONS 至少有 6 个预置档', () => {
    expect(N2_VAT_RATE_OPTIONS.length).toBeGreaterThanOrEqual(6)
  })
})
