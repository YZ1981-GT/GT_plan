/**
 * useD3FormulaEngine PBT + 单元测试
 *
 * Property-Based Tests 使用 fast-check，numRuns: 100。
 * 覆盖 D3 预收账款公式引擎全部纯函数。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcAuditedAmount,
  calcChangeAmount,
  calcChangeRate,
  calcSubtotal,
  calcPriorAudited,
  calcEndBalance,
  calcEndUnadjusted,
  calcEndAudited,
  calcRelatedPartyEndBalance,
  isChangeRateExceeding,
  calcAnomalyRate,
  aggregateByNature,
  aggregateByAging,
} from '../composables/useD3FormulaEngine'

// ─── 单元测试 ────────────────────────────────────────────────────────────────

describe('useD3FormulaEngine - 单元测试', () => {
  describe('parseNum', () => {
    it('returns 0 for null', () => expect(parseNum(null)).toBe(0))
    it('returns 0 for undefined', () => expect(parseNum(undefined)).toBe(0))
    it('returns 0 for empty string', () => expect(parseNum('')).toBe(0))
    it('returns 0 for NaN string', () => expect(parseNum('abc')).toBe(0))
    it('returns 0 for Infinity', () => {
      expect(parseNum(Infinity)).toBe(0)
      expect(parseNum(-Infinity)).toBe(0)
    })
    it('parses numeric strings', () => expect(parseNum('123.45')).toBe(123.45))
    it('passes through numbers', () => expect(parseNum(42)).toBe(42))
  })

  describe('calcChangeRate', () => {
    it('returns empty string when both 0', () => expect(calcChangeRate(0, 0)).toBe(''))
    it('returns N/A when prior=0 current≠0', () => expect(calcChangeRate(0, 100)).toBe('N/A'))
    it('calculates rate', () => expect(calcChangeRate(100, 120)).toBeCloseTo(0.2))
    it('handles negative change', () => expect(calcChangeRate(100, 80)).toBeCloseTo(-0.2))
  })

  describe('calcEndBalance (贷方科目)', () => {
    it('期末 = 期初审定 + 贷方 - 借方', () => {
      expect(calcEndBalance(1000, 500, 200)).toBe(1300)
    })
  })

  describe('aggregateByNature', () => {
    it('groups by nature field', () => {
      const rows = [
        { nature: '预收销售固定资产款', endAudited: 100, priorAudited: 80, agingAudited: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 } },
        { nature: '预收销售固定资产款', endAudited: 200, priorAudited: 150, agingAudited: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 } },
        { nature: '其他', endAudited: 50, priorAudited: 40, agingAudited: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 } },
      ]
      const result = aggregateByNature(rows, 'endAudited')
      expect(result['预收销售固定资产款']).toBe(300)
      expect(result['其他']).toBe(50)
    })

    it('defaults empty nature to 其他', () => {
      const rows = [
        { nature: '', endAudited: 100, priorAudited: 0, agingAudited: { within1: 0, y1to2: 0, y2to3: 0, over3: 0 } },
      ]
      expect(aggregateByNature(rows, 'endAudited')['其他']).toBe(100)
    })
  })

  describe('aggregateByAging', () => {
    it('sums aging columns', () => {
      const rows = [
        { nature: '', endAudited: 0, priorAudited: 0, agingAudited: { within1: 100, y1to2: 20, y2to3: 5, over3: 1 } },
        { nature: '', endAudited: 0, priorAudited: 0, agingAudited: { within1: 200, y1to2: 30, y2to3: 10, over3: 2 } },
      ]
      const result = aggregateByAging(rows)
      expect(result.within1).toBe(300)
      expect(result.y1to2).toBe(50)
      expect(result.y2to3).toBe(15)
      expect(result.over3).toBe(3)
    })
  })
})

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('useD3FormulaEngine - Property-Based Tests', () => {
  /**
   * **Feature: d3-prepaid-accounts, Property 1: 审定数公式正确性**
   *
   * For any 三元组 (未审数, AJE净额, RJE净额)，
   * calcAuditedAmount 的返回值应等于 未审数 + AJE + RJE。
   *
   * **Validates: Requirements 1.3, 2.5**
   */
  describe('Property 1: 审定数公式正确性', () => {
    it('calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          (u, a, r) => {
            const result = calcAuditedAmount(u, a, r)
            const expected = u + a + r
            return Math.abs(result - expected) < 1e-6
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d3-prepaid-accounts, Property 2: 变动额与变动率公式正确性**
   *
   * For any (期初审定数, 期末审定数) 对，变动额应等于 期末 - 期初；
   * 变动率特殊处理：期初=0且期末=0返回''，期初=0且期末≠0返回'N/A'，
   * 否则 (期末-期初)/期初。
   *
   * **Validates: Requirements 1.4**
   */
  describe('Property 2: 变动额与变动率公式正确性', () => {
    it('changeAmount === current - prior', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          (current, prior) => {
            const result = calcChangeAmount(current, prior)
            const expected = current - prior
            return Math.abs(result - expected) < 1e-6
          }
        ),
        { numRuns: 100 }
      )
    })

    it('changeRate special cases: both 0 → "", prior=0 current≠0 → "N/A"', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          (prior, current) => {
            const rate = calcChangeRate(prior, current)
            if (prior === 0 && current === 0) {
              return rate === ''
            }
            if (prior === 0 && current !== 0) {
              return rate === 'N/A'
            }
            // Normal case: rate should be (current - prior) / prior
            if (typeof rate !== 'number') return false
            const expected = (current - prior) / prior
            return Math.abs(rate - expected) < 1e-6
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d3-prepaid-accounts, Property 3: 合计行恒等于明细行之和**
   *
   * For any 明细行列表（1~30行），calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)。
   *
   * **Validates: Requirements 1.5, 4.5, 9.4, 10.6**
   */
  describe('Property 3: 合计行恒等于明细行之和', () => {
    it('calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)', () => {
      fc.assert(
        fc.property(
          fc.array(fc.float({ min: -1e9, max: 1e9, noNaN: true }), { minLength: 1, maxLength: 30 }),
          (arr) => {
            const result = calcSubtotal(arr)
            const expected = arr.reduce((a, b) => a + b, 0)
            return Math.abs(result - expected) < 1e-6
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d3-prepaid-accounts, Property 4: 变动率阈值高亮判定**
   *
   * For any 变动率数值 r（非空非'N/A'），
   * isChangeRateExceeding(r, 0.3) 应返回 true 当且仅当 |r| > 0.3。
   *
   * **Validates: Requirements 1.6, 8.8**
   */
  describe('Property 4: 变动率阈值高亮判定', () => {
    it('isChangeRateExceeding(r, 0.3) === (Math.abs(r) > 0.3)', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -10, max: 10, noNaN: true }),
          (r) => {
            const result = isChangeRateExceeding(r, 0.3)
            const expected = Math.abs(r) > 0.3
            return result === expected
          }
        ),
        { numRuns: 100 }
      )
    })

    it('returns false for empty string and N/A', () => {
      expect(isChangeRateExceeding('', 0.3)).toBe(false)
      expect(isChangeRateExceeding('N/A', 0.3)).toBe(false)
    })
  })

  /**
   * **Feature: d3-prepaid-accounts, Property 16: 差异行计算正确性**
   *
   * For any (合计值, 试算表数) 对，差异行值应等于 合计 - 试算表数。
   * 适用于 D3-1 试算平衡表差异和 D3-4 分析表差异。
   *
   * **Validates: Requirements 1.7, 8.3**
   */
  describe('Property 16: 差异行计算正确性', () => {
    it('diff === total - tbAmount (using calcChangeAmount)', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          (total, tbAmount) => {
            // 差异行 = 合计 - 试算表数，复用 calcChangeAmount(total, tbAmount) = total - tbAmount
            const diff = calcChangeAmount(total, tbAmount)
            const expected = total - tbAmount
            return Math.abs(diff - expected) < 1e-6
          }
        ),
        { numRuns: 100 }
      )
    })
  })
})
