/**
 * useD3VoucherCheck PBT 测试
 *
 * Property-Based Tests 使用 fast-check，numRuns: 100。
 * 覆盖 D3-7 凭证检查核心逻辑：异常率计算 + 跨期自动标记。
 *
 * 测试纯函数逻辑（computeAnomalyRate, shouldMarkCrossPeriod），不依赖 Vue 响应式。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { computeAnomalyRate, shouldMarkCrossPeriod } from '../composables/useD3VoucherCheck'

// ─── Generators ──────────────────────────────────────────────────────────────

/** isAbnormal 随机赋值（空字符串或非空字符串） */
const isAbnormalArb = fc.oneof(
  fc.constant(''),
  fc.constantFrom('跨期疑点', '金额异常', '凭证缺失', '对方科目异常'),
)

/** VoucherRow（仅异常率相关字段）生成器 */
const voucherRowArb = fc.record({
  isAbnormal: isAbnormalArb,
})

/** 日期生成器：合理范围内的日期 */
const dateArb = fc.date({
  min: new Date('2020-01-01'),
  max: new Date('2030-12-31'),
})

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('useD3VoucherCheck - Property-Based Tests', () => {
  /**
   * **Feature: d3-prepaid-accounts, Property 19: 凭证检查异常率计算正确性**
   *
   * For any 凭证检查行列表，anomalyRate应等于（isAbnormal非空行数 / 总行数 × 100%）。
   *
   * **Validates: Requirements 11.5**
   */
  describe('Property 19: 凭证检查异常率计算正确性', () => {
    it('anomalyRate === 非空异常行数/总行数×100', () => {
      fc.assert(
        fc.property(
          fc.array(voucherRowArb, { minLength: 1, maxLength: 50 }),
          (rows) => {
            const result = computeAnomalyRate(rows)

            // Manual calculation
            const anomalyCount = rows.filter(r => r.isAbnormal !== '').length
            const expectedRate = (anomalyCount / rows.length) * 100

            expect(result).toBeCloseTo(expectedRate, 10)
          }
        ),
        { numRuns: 100 }
      )
    })

    it('空数组时 anomalyRate = 0', () => {
      expect(computeAnomalyRate([])).toBe(0)
    })

    it('全部为空异常时 anomalyRate = 0', () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 1, max: 50 }),
          (n) => {
            const rows = Array.from({ length: n }, () => ({ isAbnormal: '' }))
            expect(computeAnomalyRate(rows)).toBe(0)
          }
        ),
        { numRuns: 100 }
      )
    })

    it('全部非空异常时 anomalyRate = 100', () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 1, max: 50 }),
          (n) => {
            const rows = Array.from({ length: n }, () => ({ isAbnormal: '异常' }))
            expect(computeAnomalyRate(rows)).toBeCloseTo(100, 10)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: d3-prepaid-accounts, Property 20: 期后结转跨期自动标记**
   *
   * For any 期后结转检查行，当凭证日期早于对应收入确认日期时，
   * shouldMarkCrossPeriod 应返回 true。
   *
   * **Validates: Requirements 11.7**
   */
  describe('Property 20: 期后结转跨期自动标记', () => {
    it('voucherDate < revenueDate → 返回true', () => {
      fc.assert(
        fc.property(
          dateArb,
          dateArb,
          (voucherDate, revenueDate) => {
            const result = shouldMarkCrossPeriod(voucherDate, revenueDate)

            if (voucherDate < revenueDate) {
              expect(result).toBe(true)
            } else {
              expect(result).toBe(false)
            }
          }
        ),
        { numRuns: 100 }
      )
    })

    it('相同日期时返回false', () => {
      fc.assert(
        fc.property(
          dateArb,
          (date) => {
            const sameDateCopy = new Date(date.getTime())
            expect(shouldMarkCrossPeriod(date, sameDateCopy)).toBe(false)
          }
        ),
        { numRuns: 100 }
      )
    })

    it('voucherDate > revenueDate → 返回false', () => {
      fc.assert(
        fc.property(
          dateArb,
          fc.integer({ min: 1, max: 365 }),
          (revenueDate, daysAfter) => {
            const voucherDate = new Date(revenueDate.getTime() + daysAfter * 86400000)
            expect(shouldMarkCrossPeriod(voucherDate, revenueDate)).toBe(false)
          }
        ),
        { numRuns: 100 }
      )
    })
  })
})
