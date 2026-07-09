/**
 * Unit tests: useH9AmortizationEngine — 摊销表引擎（实际利率法）
 * Requirements: 7.1-7.5
 */
import { describe, it, expect } from 'vitest'
import {
  calcInterest,
  calcPrincipal,
  calcEndBalance,
  generateSchedule,
  validateSchedule,
  type AmortizationRow,
} from '../useH9AmortizationEngine'

describe('useH9AmortizationEngine', () => {
  // ─── calcInterest ───
  describe('calcInterest', () => {
    it('计算利息 = 期初余额 × 利率', () => {
      expect(calcInterest(100000, 0.05)).toBe(5000)
    })

    it('利率为0时利息为0', () => {
      expect(calcInterest(500000, 0)).toBe(0)
    })

    it('余额为0时利息为0', () => {
      expect(calcInterest(0, 0.08)).toBe(0)
    })
  })

  // ─── calcPrincipal ───
  describe('calcPrincipal', () => {
    it('本金 = 付款 - 利息', () => {
      expect(calcPrincipal(10000, 3000)).toBe(7000)
    })

    it('付款等于利息时本金为0', () => {
      expect(calcPrincipal(5000, 5000)).toBe(0)
    })

    it('付款小于利息时本金为负（余额增长）', () => {
      expect(calcPrincipal(3000, 5000)).toBe(-2000)
    })
  })

  // ─── calcEndBalance ───
  describe('calcEndBalance', () => {
    it('期末 = 期初 - 本金', () => {
      expect(calcEndBalance(100000, 7000)).toBe(93000)
    })

    it('本金为负时期末>期初', () => {
      expect(calcEndBalance(100000, -2000)).toBe(102000)
    })
  })

  // ─── generateSchedule ───
  describe('generateSchedule', () => {
    it('periods=0返回空数组', () => {
      expect(generateSchedule(100000, 10000, 0.05, 0)).toEqual([])
    })

    it('rate=0时全部付款归本金', () => {
      const schedule = generateSchedule(30000, 10000, 0, 3)
      expect(schedule).toHaveLength(3)
      // 每期利息=0
      expect(schedule[0].interest).toBe(0)
      expect(schedule[1].interest).toBe(0)
      // 最后一期余额归零
      expect(schedule[2].endBalance).toBe(0)
    })

    it('正常摊销表最后一期归零', () => {
      // 100000元，每期付12000，利率5%，12期
      const schedule = generateSchedule(100000, 12000, 0.05, 12)
      expect(schedule).toHaveLength(12)
      // 第一期
      expect(schedule[0].beginBalance).toBe(100000)
      expect(schedule[0].interest).toBe(5000) // 100000 * 0.05
      expect(schedule[0].principal).toBe(7000) // 12000 - 5000
      expect(schedule[0].endBalance).toBe(93000) // 100000 - 7000
      // 最后一期精确归零
      expect(schedule[11].endBalance).toBe(0)
    })

    it('期间连续性：每期期初=上期期末', () => {
      const schedule = generateSchedule(50000, 6000, 0.03, 10)
      for (let i = 1; i < schedule.length; i++) {
        expect(schedule[i].beginBalance).toBeCloseTo(schedule[i - 1].endBalance, 10)
      }
    })

    it('单期摊销表也能归零', () => {
      const schedule = generateSchedule(10000, 999, 0.02, 1)
      // 单期=最后一期，付款调整为 10000 + 10000*0.02 = 10200
      expect(schedule[0].payment).toBe(10200)
      expect(schedule[0].endBalance).toBe(0)
    })
  })

  // ─── validateSchedule ───
  describe('validateSchedule', () => {
    it('空摊销表视为有效', () => {
      const result = validateSchedule([])
      expect(result.isValid).toBe(true)
      expect(result.tailDiff).toBe(0)
    })

    it('generateSchedule产生的摊销表通过验证', () => {
      const schedule = generateSchedule(200000, 25000, 0.04, 10)
      const result = validateSchedule(schedule)
      expect(result.isValid).toBe(true)
      expect(result.tailDiff).toBe(0)
    })

    it('尾差超过1元视为无效', () => {
      const badSchedule: AmortizationRow[] = [
        { period: 1, beginBalance: 10000, payment: 5000, interest: 500, principal: 4500, endBalance: 5500 },
        { period: 2, beginBalance: 5500, payment: 5000, interest: 275, principal: 4725, endBalance: 2.5 },
      ]
      // endBalance=2.5 > 1 → invalid
      const result = validateSchedule(badSchedule)
      expect(result.isValid).toBe(false)
      expect(result.tailDiff).toBe(2.5)
    })

    it('尾差在±1元内视为有效', () => {
      const okSchedule: AmortizationRow[] = [
        { period: 1, beginBalance: 10000, payment: 10500, interest: 500, principal: 10000, endBalance: 0.5 },
      ]
      const result = validateSchedule(okSchedule)
      expect(result.isValid).toBe(true)
      expect(result.tailDiff).toBe(0.5)
    })
  })
})
