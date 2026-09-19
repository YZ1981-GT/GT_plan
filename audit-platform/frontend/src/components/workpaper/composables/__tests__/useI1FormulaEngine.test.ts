/**
 * useI1FormulaEngine — Vitest 单元测试
 *
 * 覆盖全部纯函数的核心逻辑和边界情况。
 * 每个函数 3-5 个测试用例，涵盖正常值、零值、负数、大数、除零保护。
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcTriangleReconciliation,
  calcNetValue,
  calcChangeRate,
  calcSubtotal,
  calcProportion,
  calcDisposalGainLoss,
  calcTitleDiff,
  isBalanced,
  calcAllocTotal,
} from '../useI1FormulaEngine'

describe('useI1FormulaEngine', () => {
  // ─── calcAuditedAmount ──────────────────────────────────────────────────────

  describe('calcAuditedAmount', () => {
    it('正常计算：未审+AJE+RJE', () => {
      expect(calcAuditedAmount(10000, 500, 200)).toBe(10700)
    })

    it('负数调整', () => {
      expect(calcAuditedAmount(10000, -300, -200)).toBe(9500)
    })

    it('全部为零', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('大数计算', () => {
      expect(calcAuditedAmount(1e12, 5e9, 3e9)).toBe(1.008e12)
    })

    it('混合正负数', () => {
      expect(calcAuditedAmount(-5000, 8000, -1000)).toBe(2000)
    })
  })

  // ─── calcAssetEndBalance ────────────────────────────────────────────────────

  describe('calcAssetEndBalance', () => {
    it('资产类1701：期末 = 期初 + 借方 - 贷方', () => {
      expect(calcAssetEndBalance(100000, 20000, 5000)).toBe(115000)
    })

    it('零输入', () => {
      expect(calcAssetEndBalance(0, 0, 0)).toBe(0)
    })

    it('贷方大于期初+借方 → 负值', () => {
      expect(calcAssetEndBalance(1000, 500, 3000)).toBe(-1500)
    })

    it('大数', () => {
      expect(calcAssetEndBalance(1e10, 5e9, 2e9)).toBe(1.3e10)
    })

    it('期初为负', () => {
      expect(calcAssetEndBalance(-1000, 3000, 500)).toBe(1500)
    })
  })

  // ─── calcContraEndBalance ───────────────────────────────────────────────────

  describe('calcContraEndBalance', () => {
    it('备抵类1702/1703：期末 = 期初 + 贷方 - 借方', () => {
      expect(calcContraEndBalance(50000, 2000, 10000)).toBe(58000)
    })

    it('零输入', () => {
      expect(calcContraEndBalance(0, 0, 0)).toBe(0)
    })

    it('借方大于期初+贷方 → 负值', () => {
      expect(calcContraEndBalance(1000, 5000, 2000)).toBe(-2000)
    })

    it('大数', () => {
      expect(calcContraEndBalance(1e10, 1e9, 3e9)).toBe(1.2e10)
    })

    it('全部为负', () => {
      // begin + credit - debit = -1000 + (-200) - (-500) = -700
      expect(calcContraEndBalance(-1000, -500, -200)).toBe(-700)
    })
  })

  // ─── calcTriangleReconciliation ─────────────────────────────────────────────

  describe('calcTriangleReconciliation', () => {
    it('平衡时差额为0', () => {
      // end = begin + increase - decrease = 100 + 30 - 10 = 120
      expect(calcTriangleReconciliation(100, 30, 10, 120)).toBe(0)
    })

    it('不平衡时返回差额', () => {
      // expected end = 100 + 30 - 10 = 120, actual = 125 → diff = 5
      expect(calcTriangleReconciliation(100, 30, 10, 125)).toBe(5)
    })

    it('全部为零 → 平衡', () => {
      expect(calcTriangleReconciliation(0, 0, 0, 0)).toBe(0)
    })

    it('负数输入', () => {
      // expected: -100 + (-50) - (-30) = -100 - 50 + 30 = -120
      expect(calcTriangleReconciliation(-100, -50, -30, -120)).toBe(0)
    })

    it('大数勾稽', () => {
      const begin = 1e12
      const increase = 5e10
      const decrease = 2e10
      const end = begin + increase - decrease
      expect(calcTriangleReconciliation(begin, increase, decrease, end)).toBe(0)
    })
  })

  // ─── calcNetValue ───────────────────────────────────────────────────────────

  describe('calcNetValue', () => {
    it('净值 = 原值 - 累计摊销 - 减值', () => {
      expect(calcNetValue(100000, 30000, 5000)).toBe(65000)
    })

    it('全部为零', () => {
      expect(calcNetValue(0, 0, 0)).toBe(0)
    })

    it('摊销+减值 > 原值 → 负值', () => {
      expect(calcNetValue(10000, 8000, 5000)).toBe(-3000)
    })

    it('无减值', () => {
      expect(calcNetValue(500000, 200000, 0)).toBe(300000)
    })

    it('大数', () => {
      expect(calcNetValue(1e10, 3e9, 1e9)).toBe(6e9)
    })
  })

  // ─── calcChangeRate ─────────────────────────────────────────────────────────

  describe('calcChangeRate', () => {
    it('正常变动率计算（百分比）', () => {
      // (1200 - 1000) / 1000 * 100 = 20%
      expect(calcChangeRate(1200, 1000)).toBe(20)
    })

    it('负变动率', () => {
      // (800 - 1000) / 1000 * 100 = -20%
      expect(calcChangeRate(800, 1000)).toBe(-20)
    })

    it('上期为0 → 返回null', () => {
      expect(calcChangeRate(500, 0)).toBeNull()
    })

    it('本期与上期相同 → 0%', () => {
      expect(calcChangeRate(1000, 1000)).toBe(0)
    })

    it('负数基数', () => {
      // (-500 - (-1000)) / (-1000) * 100 = 500 / -1000 * 100 = -50%
      expect(calcChangeRate(-500, -1000)).toBe(-50)
    })
  })

  // ─── calcSubtotal ───────────────────────────────────────────────────────────

  describe('calcSubtotal', () => {
    it('正常求和', () => {
      expect(calcSubtotal([100, 200, 300])).toBe(600)
    })

    it('空数组 → 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('含负数', () => {
      expect(calcSubtotal([100, -50, 200, -30])).toBe(220)
    })

    it('单元素', () => {
      expect(calcSubtotal([42])).toBe(42)
    })

    it('大数组', () => {
      const arr = Array.from({ length: 1000 }, (_, i) => i + 1)
      // sum = 1000 * 1001 / 2 = 500500
      expect(calcSubtotal(arr)).toBe(500500)
    })
  })

  // ─── calcProportion ─────────────────────────────────────────────────────────

  describe('calcProportion', () => {
    it('正常占比计算（百分比）', () => {
      // 250 / 1000 * 100 = 25%
      expect(calcProportion(250, 1000)).toBe(25)
    })

    it('合计为0 → 返回null', () => {
      expect(calcProportion(100, 0)).toBeNull()
    })

    it('项目为0 → 0%', () => {
      expect(calcProportion(0, 1000)).toBe(0)
    })

    it('项目等于合计 → 100%', () => {
      expect(calcProportion(500, 500)).toBe(100)
    })

    it('负数项目', () => {
      // -200 / 1000 * 100 = -20%
      expect(calcProportion(-200, 1000)).toBe(-20)
    })
  })

  // ─── calcDisposalGainLoss ───────────────────────────────────────────────────

  describe('calcDisposalGainLoss', () => {
    it('正收益（收入 > 净值）', () => {
      expect(calcDisposalGainLoss(80000, 50000)).toBe(30000)
    })

    it('负收益/亏损（收入 < 净值）', () => {
      expect(calcDisposalGainLoss(30000, 50000)).toBe(-20000)
    })

    it('零收入', () => {
      expect(calcDisposalGainLoss(0, 10000)).toBe(-10000)
    })

    it('收入等于净值 → 0', () => {
      expect(calcDisposalGainLoss(10000, 10000)).toBe(0)
    })

    it('大数', () => {
      expect(calcDisposalGainLoss(1e9, 8e8)).toBe(2e8)
    })
  })

  // ─── calcTitleDiff ──────────────────────────────────────────────────────────

  describe('calcTitleDiff', () => {
    it('账面 > 权证 → 正差异', () => {
      expect(calcTitleDiff(100000, 95000)).toBe(5000)
    })

    it('账面 < 权证 → 负差异', () => {
      expect(calcTitleDiff(90000, 100000)).toBe(-10000)
    })

    it('一致 → 0', () => {
      expect(calcTitleDiff(50000, 50000)).toBe(0)
    })

    it('零值', () => {
      expect(calcTitleDiff(0, 0)).toBe(0)
    })

    it('负值权证（异常场景）', () => {
      expect(calcTitleDiff(10000, -5000)).toBe(15000)
    })
  })

  // ─── isBalanced ─────────────────────────────────────────────────────────────

  describe('isBalanced', () => {
    it('借贷平衡', () => {
      const entries = [
        { debit: 1000, credit: 0 },
        { debit: 0, credit: 500 },
        { debit: 0, credit: 500 },
      ]
      expect(isBalanced(entries)).toBe(true)
    })

    it('借贷不平衡', () => {
      const entries = [
        { debit: 1000, credit: 0 },
        { debit: 0, credit: 800 },
      ]
      expect(isBalanced(entries)).toBe(false)
    })

    it('空数组视为平衡', () => {
      expect(isBalanced([])).toBe(true)
    })

    it('浮点精度容忍 < 0.01', () => {
      const entries = [
        { debit: 0.1 + 0.2, credit: 0.3 },
      ]
      expect(isBalanced(entries)).toBe(true)
    })
  })

  // ─── calcAllocTotal ─────────────────────────────────────────────────────────

  describe('calcAllocTotal', () => {
    it('分配合计', () => {
      expect(calcAllocTotal([100, 200, 300, 50])).toBe(650)
    })

    it('空数组 → 0', () => {
      expect(calcAllocTotal([])).toBe(0)
    })

    it('含负数', () => {
      expect(calcAllocTotal([500, -100, 200])).toBe(600)
    })
  })
})
