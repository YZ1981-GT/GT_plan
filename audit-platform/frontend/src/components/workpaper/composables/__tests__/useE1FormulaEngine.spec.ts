/**
 * useE1FormulaEngine — 单元测试
 *
 * 覆盖全部14个纯函数的核心逻辑和边界情况。
 * PBT 测试在 Task 1.2 的 useE1FormulaEngine.pbt.spec.ts 中。
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAudited,
  calcChange,
  calcChangeRate,
  calcCashBalance,
  calcReconciled,
  calcAccruedInterest,
  calcFxConvert,
  calcCountDiff,
  sumField,
  exceedsThreshold,
  isBalanced,
  serializeRows,
  deserializeRows,
} from '../useE1FormulaEngine'

describe('useE1FormulaEngine', () => {
  // ─── parseNum ───────────────────────────────────────────────────────────────

  describe('parseNum', () => {
    it('parses valid numbers', () => {
      expect(parseNum(42)).toBe(42)
      expect(parseNum('3.14')).toBe(3.14)
      expect(parseNum('-100')).toBe(-100)
      expect(parseNum(0)).toBe(0)
    })

    it('returns 0 for null/undefined/empty', () => {
      expect(parseNum(null)).toBe(0)
      expect(parseNum(undefined)).toBe(0)
      expect(parseNum('')).toBe(0)
    })

    it('returns 0 for NaN/Infinity', () => {
      expect(parseNum(NaN)).toBe(0)
      expect(parseNum(Infinity)).toBe(0)
      expect(parseNum(-Infinity)).toBe(0)
      expect(parseNum('abc')).toBe(0)
    })

    it('handles boolean and object gracefully', () => {
      expect(parseNum(true)).toBe(1)
      expect(parseNum(false)).toBe(0)
      expect(parseNum({})).toBe(0)
      expect(parseNum([])).toBe(0)
    })
  })

  // ─── calcAudited ────────────────────────────────────────────────────────────

  describe('calcAudited', () => {
    it('审定数 = 未审数 + 账项调整', () => {
      expect(calcAudited(1000, 200)).toBe(1200)
      expect(calcAudited(1000, -200)).toBe(800)
      expect(calcAudited(0, 0)).toBe(0)
    })
  })

  // ─── calcChange ─────────────────────────────────────────────────────────────

  describe('calcChange', () => {
    it('变动额 = 期末审定 - 期初审定', () => {
      expect(calcChange(1200, 1000)).toBe(200)
      expect(calcChange(800, 1000)).toBe(-200)
      expect(calcChange(0, 0)).toBe(0)
    })
  })

  // ─── calcChangeRate ─────────────────────────────────────────────────────────

  describe('calcChangeRate', () => {
    it('正常情况：变动额/期初', () => {
      expect(calcChangeRate(200, 1000)).toBe(0.2)
      expect(calcChangeRate(-500, 1000)).toBe(-0.5)
    })

    it('期初=0 且 期末=0 → 0', () => {
      // ending = opening + change = 0 + 0 = 0
      expect(calcChangeRate(0, 0)).toBe(0)
    })

    it('期初=0 且 期末>0 → 1', () => {
      // ending = 0 + 500 = 500 > 0
      expect(calcChangeRate(500, 0)).toBe(1)
    })

    it('期初=0 且 期末<0 → 空串', () => {
      // ending = 0 + (-500) = -500, opening=0 but ending<=0
      expect(calcChangeRate(-500, 0)).toBe('')
    })
  })

  // ─── calcCashBalance ────────────────────────────────────────────────────────

  describe('calcCashBalance', () => {
    it('期末 = 期初 + 增加 - 减少', () => {
      expect(calcCashBalance(10000, 5000, 3000)).toBe(12000)
      expect(calcCashBalance(0, 100, 100)).toBe(0)
      expect(calcCashBalance(1000, 0, 0)).toBe(1000)
    })
  })

  // ─── calcReconciled ─────────────────────────────────────────────────────────

  describe('calcReconciled', () => {
    it('调节后余额 = 基数 + 加项 - 减项', () => {
      expect(calcReconciled(50000, 2000, 1000)).toBe(51000)
      expect(calcReconciled(50000, 0, 0)).toBe(50000)
    })
  })

  // ─── calcAccruedInterest ────────────────────────────────────────────────────

  describe('calcAccruedInterest', () => {
    it('应计利息 = 金额 × 天数 × 日利率', () => {
      // 100万 × 30天 × 0.01% 日利率
      expect(calcAccruedInterest(1000000, 30, 0.0001)).toBeCloseTo(3000)
      expect(calcAccruedInterest(0, 30, 0.0001)).toBe(0)
      expect(calcAccruedInterest(1000000, 0, 0.0001)).toBe(0)
    })
  })

  // ─── calcFxConvert ──────────────────────────────────────────────────────────

  describe('calcFxConvert', () => {
    it('外币折算 = 原币 × 汇率', () => {
      expect(calcFxConvert(10000, 7.25)).toBeCloseTo(72500)
      expect(calcFxConvert(0, 7.25)).toBe(0)
      expect(calcFxConvert(10000, 0)).toBe(0)
    })
  })

  // ─── calcCountDiff ──────────────────────────────────────────────────────────

  describe('calcCountDiff', () => {
    it('盘点差异 = 实盘 - 账面', () => {
      expect(calcCountDiff(10000, 10000)).toBe(0)
      expect(calcCountDiff(10500, 10000)).toBe(500)
      expect(calcCountDiff(9800, 10000)).toBe(-200)
    })
  })

  // ─── sumField ───────────────────────────────────────────────────────────────

  describe('sumField', () => {
    it('对行数组按字段求和', () => {
      const rows = [
        { amount: 100, name: '人民币' },
        { amount: 200, name: '美元' },
        { amount: 300, name: '欧元' },
      ]
      expect(sumField(rows, 'amount')).toBe(600)
    })

    it('空数组返回 0', () => {
      expect(sumField([], 'amount')).toBe(0)
    })

    it('字段缺失或非数值按 0 处理', () => {
      const rows = [
        { amount: 100 },
        { amount: null },
        { other: 500 },
        { amount: 'abc' },
      ]
      expect(sumField(rows, 'amount')).toBe(100)
    })
  })

  // ─── exceedsThreshold ──────────────────────────────────────────────────────

  describe('exceedsThreshold', () => {
    it('绝对值超阈值返回 true', () => {
      expect(exceedsThreshold(0.35, 0.3)).toBe(true)
      expect(exceedsThreshold(-0.5, 0.3)).toBe(true)
    })

    it('绝对值不超阈值返回 false', () => {
      expect(exceedsThreshold(0.2, 0.3)).toBe(false)
      expect(exceedsThreshold(0.3, 0.3)).toBe(false)
    })

    it('空串返回 false', () => {
      expect(exceedsThreshold('', 0.3)).toBe(false)
    })
  })

  // ─── isBalanced ─────────────────────────────────────────────────────────────

  describe('isBalanced', () => {
    it('借贷相等返回 true', () => {
      const rows = [
        { debit: 1000, credit: 0 },
        { debit: 0, credit: 500 },
        { debit: 0, credit: 500 },
      ]
      expect(isBalanced(rows, 'debit', 'credit')).toBe(true)
    })

    it('借贷不等返回 false', () => {
      const rows = [
        { debit: 1000, credit: 0 },
        { debit: 0, credit: 800 },
      ]
      expect(isBalanced(rows, 'debit', 'credit')).toBe(false)
    })

    it('空数组视为平衡', () => {
      expect(isBalanced([], 'debit', 'credit')).toBe(true)
    })

    it('浮点精度容忍 < 0.001', () => {
      const rows = [
        { debit: 0.1 + 0.2, credit: 0.3 },
      ]
      expect(isBalanced(rows, 'debit', 'credit')).toBe(true)
    })
  })

  // ─── serializeRows / deserializeRows ───────────────────────────────────────

  describe('serializeRows / deserializeRows', () => {
    it('round-trip 保留用户字段', () => {
      const rows = [
        { id: '1', currency: '人民币', opening: 1000, computed_ending: 1500 },
        { id: '2', currency: '美元', opening: 500, computed_ending: 800 },
      ]
      const json = serializeRows(rows, ['id', 'currency', 'opening'])
      const result = deserializeRows(json, r => ({
        ...r,
        computed_ending: (r.opening as number || 0) + 100,
      }))
      expect(result).toHaveLength(2)
      expect(result[0]).toEqual({ id: '1', currency: '人民币', opening: 1000, computed_ending: 1100 })
      expect(result[1]).toEqual({ id: '2', currency: '美元', opening: 500, computed_ending: 600 })
    })

    it('serializeRows 只保留指定字段', () => {
      const rows = [{ a: 1, b: 2, c: 3 }]
      const json = serializeRows(rows, ['a', 'c'])
      expect(JSON.parse(json)).toEqual([{ a: 1, c: 3 }])
    })

    it('deserializeRows 解析失败返回空数组', () => {
      expect(deserializeRows('invalid json', r => r)).toEqual([])
      expect(deserializeRows('null', r => r)).toEqual([])
      expect(deserializeRows('"string"', r => r)).toEqual([])
    })
  })
})
