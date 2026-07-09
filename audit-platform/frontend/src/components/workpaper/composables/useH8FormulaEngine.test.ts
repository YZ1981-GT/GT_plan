import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcNetValue,
  calcSubtotal,
} from './useH8FormulaEngine'

describe('useH8FormulaEngine', () => {
  describe('calcAuditedAmount', () => {
    it('审定数 = 未审数 + AJE + RJE', () => {
      expect(calcAuditedAmount(1000, 50, -30)).toBe(1020)
    })
    it('handles NaN/undefined gracefully', () => {
      expect(calcAuditedAmount(NaN, 100, 200)).toBe(300)
      expect(calcAuditedAmount(100, undefined as unknown as number, 50)).toBe(150)
    })
  })

  describe('calcAssetEndBalance', () => {
    it('资产类期末 = 期初 + 借 - 贷', () => {
      expect(calcAssetEndBalance(5000, 1000, 200)).toBe(5800)
    })
    it('handles zero inputs', () => {
      expect(calcAssetEndBalance(0, 0, 0)).toBe(0)
    })
  })

  describe('calcContraEndBalance', () => {
    it('备抵类期末 = 期初 + 贷 - 借', () => {
      expect(calcContraEndBalance(3000, 100, 500)).toBe(3400)
    })
  })

  describe('calcNetValue', () => {
    it('净值 = 原值 - 累计折旧 - 减值准备', () => {
      expect(calcNetValue(10000, 3000, 500)).toBe(6500)
    })
    it('handles NaN input → treated as 0', () => {
      expect(calcNetValue(10000, NaN, 0)).toBe(10000)
    })
  })

  describe('calcSubtotal', () => {
    it('合计 = 数组元素之和', () => {
      expect(calcSubtotal([100, 200, 300])).toBe(600)
    })
    it('empty array → 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })
    it('handles NaN in array → treated as 0', () => {
      expect(calcSubtotal([100, NaN, 200])).toBe(300)
    })
  })
})
