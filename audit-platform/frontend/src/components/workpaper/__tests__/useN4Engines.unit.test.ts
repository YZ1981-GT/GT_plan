/**
 * Unit Tests — useN4FormulaEngine + useN4MultiTaxEngine
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/
 * Task: 7.1
 *
 * 确定性单元测试覆盖：
 * - 损益类方向（本期发生额）
 * - 各税种计税依据×税率
 * - 同比变动
 * - 边界（零值/大数/上期为0除零）
 *
 * Requirements: P1-P6
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAuditedAmount,
  calcPeriodAmount,
  calcSubtotal,
  calcYoyChange,
} from '../composables/useN4FormulaEngine'
import {
  calcSurtax,
  calcPropertyTaxByValue,
  calcPropertyTaxByRent,
  calcStampTax,
  calcLandUseTax,
  calcExpenseDiff,
} from '../composables/useN4MultiTaxEngine'

// ═══════════════════════════════════════════════════════════════
// useN4FormulaEngine
// ═══════════════════════════════════════════════════════════════

describe('useN4FormulaEngine', () => {
  // ─── parseNum ──────────────────────────────────────────────
  describe('parseNum', () => {
    it('null → 0', () => {
      expect(parseNum(null)).toBe(0)
    })

    it('undefined → 0', () => {
      expect(parseNum(undefined)).toBe(0)
    })

    it('NaN → 0', () => {
      expect(parseNum(NaN)).toBe(0)
    })

    it('Infinity → 0', () => {
      expect(parseNum(Infinity)).toBe(0)
      expect(parseNum(-Infinity)).toBe(0)
    })

    it('string "123" → 123', () => {
      expect(parseNum('123')).toBe(123)
    })

    it('empty string "" → 0', () => {
      expect(parseNum('')).toBe(0)
    })

    it('正常数值透传', () => {
      expect(parseNum(42.5)).toBe(42.5)
      expect(parseNum(-100)).toBe(-100)
      expect(parseNum(0)).toBe(0)
    })

    it('字符串小数 "3.14" → 3.14', () => {
      expect(parseNum('3.14')).toBe(3.14)
    })
  })

  // ─── calcAuditedAmount (P1) ────────────────────────────────
  describe('calcAuditedAmount (P1: 审定数=未审+AJE+RJE)', () => {
    it('正常情况: 1000 + 200 + 50 = 1250', () => {
      expect(calcAuditedAmount(1000, 200, 50)).toBe(1250)
    })

    it('全零: 0 + 0 + 0 = 0', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('负值: -500 + 100 + (-50) = -450', () => {
      expect(calcAuditedAmount(-500, 100, -50)).toBe(-450)
    })

    it('大数: 1e12 + 1e11 + 1e10', () => {
      expect(calcAuditedAmount(1e12, 1e11, 1e10)).toBe(1.11e12)
    })
  })

  // ─── calcPeriodAmount (P2) ─────────────────────────────────
  describe('calcPeriodAmount (P2: 损益类本期发生额=借方-贷方)', () => {
    it('正常: 借方>贷方 → 正 (费用净发生)', () => {
      expect(calcPeriodAmount(8000, 3000)).toBe(5000)
    })

    it('贷方>借方 → 负 (费用冲回)', () => {
      expect(calcPeriodAmount(2000, 5000)).toBe(-3000)
    })

    it('借=贷 → 0', () => {
      expect(calcPeriodAmount(4000, 4000)).toBe(0)
    })

    it('零值: 0 - 0 = 0', () => {
      expect(calcPeriodAmount(0, 0)).toBe(0)
    })

    it('大数不溢出', () => {
      expect(calcPeriodAmount(1e12, 3e11)).toBe(7e11)
    })
  })

  // ─── calcSubtotal (P3) ─────────────────────────────────────
  describe('calcSubtotal (P3: 合计=Σarr)', () => {
    it('正常数组求和', () => {
      expect(calcSubtotal([100, 200, 300, 400])).toBe(1000)
    })

    it('空数组 → 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('单元素', () => {
      expect(calcSubtotal([999])).toBe(999)
    })

    it('含负值', () => {
      expect(calcSubtotal([100, -50, 200, -30])).toBe(220)
    })

    it('全零', () => {
      expect(calcSubtotal([0, 0, 0])).toBe(0)
    })

    it('大数数组不溢出', () => {
      expect(calcSubtotal([1e12, 2e12, 3e12])).toBe(6e12)
    })
  })

  // ─── calcYoyChange (P1.5/P7.4) ────────────────────────────
  describe('calcYoyChange (同比变动)', () => {
    it('正增长: (200 - 100) / 100 = 1.0 (100%增长)', () => {
      expect(calcYoyChange(200, 100)).toBe(1.0)
    })

    it('下降: (50 - 100) / 100 = -0.5 (50%下降)', () => {
      expect(calcYoyChange(50, 100)).toBe(-0.5)
    })

    it('不变: (100 - 100) / 100 = 0', () => {
      expect(calcYoyChange(100, 100)).toBe(0)
    })

    it('上期为0 → null (除零保护)', () => {
      expect(calcYoyChange(500, 0)).toBeNull()
    })

    it('本期和上期都为0 → null', () => {
      expect(calcYoyChange(0, 0)).toBeNull()
    })

    it('本期为0、上期不为0: (0-100)/100 = -1.0', () => {
      expect(calcYoyChange(0, 100)).toBe(-1.0)
    })

    it('负值到正值: (100 - (-50)) / (-50) = -3.0', () => {
      expect(calcYoyChange(100, -50)).toBe(-3.0)
    })
  })
})

// ═══════════════════════════════════════════════════════════════
// useN4MultiTaxEngine
// ═══════════════════════════════════════════════════════════════

describe('useN4MultiTaxEngine', () => {
  // ─── calcSurtax (P4) ───────────────────────────────────────
  describe('calcSurtax (P4: 城建税及附加=(增值税+消费税)×税率)', () => {
    it('城建税7%: (100000 + 20000) × 0.07 = 8400', () => {
      expect(calcSurtax(100000, 20000, 0.07)).toBeCloseTo(8400, 2)
    })

    it('教育费附加3%: (100000 + 20000) × 0.03 = 3600', () => {
      expect(calcSurtax(100000, 20000, 0.03)).toBeCloseTo(3600, 2)
    })

    it('地方教育附加2%: (100000 + 20000) × 0.02 = 2400', () => {
      expect(calcSurtax(100000, 20000, 0.02)).toBeCloseTo(2400, 2)
    })

    it('消费税为0: (50000 + 0) × 0.07 = 3500', () => {
      expect(calcSurtax(50000, 0, 0.07)).toBeCloseTo(3500, 2)
    })

    it('两者都为0: (0 + 0) × 0.07 = 0', () => {
      expect(calcSurtax(0, 0, 0.07)).toBe(0)
    })

    it('大数: (1e12 + 5e11) × 0.07', () => {
      expect(calcSurtax(1e12, 5e11, 0.07)).toBeCloseTo(1.05e11, 0)
    })
  })

  // ─── calcPropertyTaxByValue (P5) ───────────────────────────
  describe('calcPropertyTaxByValue (P5: 房产税从价=原值×(1-扣除比例)×1.2%)', () => {
    it('标准: 原值1000万, 扣除20% → 1000万 × 0.8 × 0.012 = 96000', () => {
      expect(calcPropertyTaxByValue(10000000, 0.2)).toBeCloseTo(96000, 2)
    })

    it('扣除30%: 500万 × 0.7 × 0.012 = 42000', () => {
      expect(calcPropertyTaxByValue(5000000, 0.3)).toBeCloseTo(42000, 2)
    })

    it('原值为0 → 0', () => {
      expect(calcPropertyTaxByValue(0, 0.2)).toBe(0)
    })

    it('扣除比例为0: 100万 × 1.0 × 0.012 = 12000', () => {
      expect(calcPropertyTaxByValue(1000000, 0)).toBeCloseTo(12000, 2)
    })

    it('大数: 1e12 × 0.8 × 0.012', () => {
      expect(calcPropertyTaxByValue(1e12, 0.2)).toBeCloseTo(9.6e9, 0)
    })
  })

  // ─── calcPropertyTaxByRent ─────────────────────────────────
  describe('calcPropertyTaxByRent (房产税从租=租金×12%)', () => {
    it('标准: 年租金100万 × 0.12 = 12万', () => {
      expect(calcPropertyTaxByRent(1000000)).toBeCloseTo(120000, 2)
    })

    it('租金为0 → 0', () => {
      expect(calcPropertyTaxByRent(0)).toBe(0)
    })

    it('大数: 1e12 × 0.12', () => {
      expect(calcPropertyTaxByRent(1e12)).toBeCloseTo(1.2e11, 0)
    })
  })

  // ─── calcStampTax (P6) ─────────────────────────────────────
  describe('calcStampTax (P6: 印花税=计税金额×适用税率)', () => {
    it('购销合同0.3‰: 1000万 × 0.0003 = 3000', () => {
      expect(calcStampTax(10000000, 0.0003)).toBeCloseTo(3000, 2)
    })

    it('租赁合同1‰: 50万 × 0.001 = 500', () => {
      expect(calcStampTax(500000, 0.001)).toBeCloseTo(500, 2)
    })

    it('借款合同0.05‰: 2000万 × 0.00005 = 1000', () => {
      expect(calcStampTax(20000000, 0.00005)).toBeCloseTo(1000, 2)
    })

    it('金额为0 → 0', () => {
      expect(calcStampTax(0, 0.0003)).toBe(0)
    })

    it('大数: 1e12 × 0.0003 = 3e8', () => {
      expect(calcStampTax(1e12, 0.0003)).toBeCloseTo(3e8, 0)
    })
  })

  // ─── calcLandUseTax ────────────────────────────────────────
  describe('calcLandUseTax (土地使用税=占地面积×单位税额)', () => {
    it('标准: 5000㎡ × 12元/㎡ = 60000', () => {
      expect(calcLandUseTax(5000, 12)).toBe(60000)
    })

    it('面积为0 → 0', () => {
      expect(calcLandUseTax(0, 12)).toBe(0)
    })

    it('单位税额为0 → 0', () => {
      expect(calcLandUseTax(5000, 0)).toBe(0)
    })

    it('大面积大城市: 100000㎡ × 30元/㎡ = 3000000', () => {
      expect(calcLandUseTax(100000, 30)).toBe(3000000)
    })
  })

  // ─── calcExpenseDiff ───────────────────────────────────────
  describe('calcExpenseDiff (费用确认差异=N4费用-N2计提)', () => {
    it('正差异: 费用>计提 → 正数', () => {
      expect(calcExpenseDiff(50000, 48000)).toBe(2000)
    })

    it('负差异: 费用<计提 → 负数', () => {
      expect(calcExpenseDiff(45000, 48000)).toBe(-3000)
    })

    it('无差异: 费用=计提 → 0', () => {
      expect(calcExpenseDiff(50000, 50000)).toBe(0)
    })

    it('两者都为0 → 0', () => {
      expect(calcExpenseDiff(0, 0)).toBe(0)
    })

    it('大数不溢出', () => {
      expect(calcExpenseDiff(1e12, 9.99e11)).toBeCloseTo(1e9, 0)
    })
  })
})

// ═══════════════════════════════════════════════════════════════
// 边界与极端情况
// ═══════════════════════════════════════════════════════════════

describe('Edge cases', () => {
  describe('零值行为', () => {
    it('calcAuditedAmount 全零', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })
    it('calcPeriodAmount 全零', () => {
      expect(calcPeriodAmount(0, 0)).toBe(0)
    })
    it('calcSurtax 全零', () => {
      expect(calcSurtax(0, 0, 0.07)).toBe(0)
    })
    it('calcStampTax 金额零', () => {
      expect(calcStampTax(0, 0.0003)).toBe(0)
    })
  })

  describe('大数 (1e12) 无溢出', () => {
    it('calcAuditedAmount', () => {
      const result = calcAuditedAmount(1e12, 1e12, 1e12)
      expect(result).toBe(3e12)
      expect(Number.isFinite(result)).toBe(true)
    })
    it('calcPeriodAmount', () => {
      const result = calcPeriodAmount(1e12, 1e11)
      expect(result).toBe(9e11)
      expect(Number.isFinite(result)).toBe(true)
    })
    it('calcSubtotal', () => {
      const result = calcSubtotal([1e12, 1e12, 1e12, 1e12])
      expect(result).toBe(4e12)
      expect(Number.isFinite(result)).toBe(true)
    })
    it('calcSurtax', () => {
      const result = calcSurtax(1e12, 1e12, 0.07)
      expect(result).toBeCloseTo(1.4e11, 0)
      expect(Number.isFinite(result)).toBe(true)
    })
    it('calcPropertyTaxByValue', () => {
      const result = calcPropertyTaxByValue(1e12, 0.2)
      expect(result).toBeCloseTo(9.6e9, 0)
      expect(Number.isFinite(result)).toBe(true)
    })
  })

  describe('负数输入正确算术', () => {
    it('calcAuditedAmount 负未审数', () => {
      expect(calcAuditedAmount(-1000, 500, 200)).toBe(-300)
    })
    it('calcPeriodAmount 负借方', () => {
      expect(calcPeriodAmount(-100, 200)).toBe(-300)
    })
    it('calcSurtax 负增值税', () => {
      // 虽然业务上不应为负，但纯函数应正确计算
      expect(calcSurtax(-10000, 5000, 0.07)).toBeCloseTo(-350, 2)
    })
    it('calcExpenseDiff 负费用确认', () => {
      expect(calcExpenseDiff(-1000, 2000)).toBe(-3000)
    })
  })
})
