import { describe, it, expect } from 'vitest'
import {
  calcInitialMeasurement,
  calcDepreciationPeriod,
  calcTerminationGainLoss,
  calcRemeasurement,
  isShortTermLease,
  isLowValueLease,
} from './useH8CAS21Engine'

describe('useH8CAS21Engine', () => {
  describe('calcInitialMeasurement', () => {
    it('CAS21初始计量：H8 = H9初始 + 直接费用 - 激励', () => {
      expect(calcInitialMeasurement(500000, 20000, 10000)).toBe(510000)
    })
    it('无激励时：H8 = H9 + 直接费用', () => {
      expect(calcInitialMeasurement(300000, 15000, 0)).toBe(315000)
    })
    it('handles NaN/undefined → treated as 0', () => {
      expect(calcInitialMeasurement(NaN, 100, 50)).toBe(50)
      expect(calcInitialMeasurement(1000, undefined as unknown as number, 0)).toBe(1000)
    })
    it('激励大于其他之和时结果为负', () => {
      expect(calcInitialMeasurement(100, 50, 200)).toBe(-50)
    })
  })

  describe('calcDepreciationPeriod', () => {
    it('折旧期 = min(租赁期, 使用寿命)', () => {
      expect(calcDepreciationPeriod(36, 60)).toBe(36)
      expect(calcDepreciationPeriod(120, 60)).toBe(60)
    })
    it('两者相等时返回该值', () => {
      expect(calcDepreciationPeriod(48, 48)).toBe(48)
    })
    it('handles zero → 0', () => {
      expect(calcDepreciationPeriod(0, 60)).toBe(0)
      expect(calcDepreciationPeriod(36, 0)).toBe(0)
    })
    it('handles NaN → treated as 0', () => {
      expect(calcDepreciationPeriod(NaN, 60)).toBe(0)
    })
  })

  describe('calcTerminationGainLoss', () => {
    it('终止收益：负债余额 > 使用权净值', () => {
      expect(calcTerminationGainLoss(100000, 80000)).toBe(20000)
    })
    it('终止损失：负债余额 < 使用权净值', () => {
      expect(calcTerminationGainLoss(80000, 100000)).toBe(-20000)
    })
    it('无损益：两者相等', () => {
      expect(calcTerminationGainLoss(50000, 50000)).toBe(0)
    })
    it('handles NaN → treated as 0', () => {
      expect(calcTerminationGainLoss(NaN, 5000)).toBe(-5000)
    })
  })

  describe('calcRemeasurement', () => {
    it('重新计量增加：旧值 + 正调整', () => {
      expect(calcRemeasurement(200000, 30000)).toBe(230000)
    })
    it('重新计量减少：旧值 + 负调整', () => {
      expect(calcRemeasurement(200000, -50000)).toBe(150000)
    })
    it('无调整时保持原值', () => {
      expect(calcRemeasurement(200000, 0)).toBe(200000)
    })
    it('handles NaN → treated as 0', () => {
      expect(calcRemeasurement(NaN, 10000)).toBe(10000)
    })
  })

  describe('isShortTermLease', () => {
    it('租赁期≤12个月 → 短期租赁', () => {
      expect(isShortTermLease(1)).toBe(true)
      expect(isShortTermLease(6)).toBe(true)
      expect(isShortTermLease(12)).toBe(true)
    })
    it('租赁期>12个月 → 非短期', () => {
      expect(isShortTermLease(13)).toBe(false)
      expect(isShortTermLease(24)).toBe(false)
      expect(isShortTermLease(36)).toBe(false)
    })
    it('边界：0或负值 → true（≤12）', () => {
      expect(isShortTermLease(0)).toBe(true)
      expect(isShortTermLease(-1)).toBe(true)
    })
    it('handles NaN → treated as 0 → true', () => {
      expect(isShortTermLease(NaN)).toBe(true)
    })
  })

  describe('isLowValueLease', () => {
    it('全新资产价值≤40000 → 低价值', () => {
      expect(isLowValueLease(30000)).toBe(true)
      expect(isLowValueLease(40000)).toBe(true)
    })
    it('全新资产价值>40000 → 非低价值', () => {
      expect(isLowValueLease(40001)).toBe(false)
      expect(isLowValueLease(100000)).toBe(false)
    })
    it('支持自定义阈值', () => {
      expect(isLowValueLease(50000, 60000)).toBe(true)
      expect(isLowValueLease(70000, 60000)).toBe(false)
    })
    it('threshold为0时只有0和负值通过', () => {
      expect(isLowValueLease(0, 0)).toBe(true)
      expect(isLowValueLease(1, 0)).toBe(false)
    })
    it('handles NaN → treated as 0 → true (0 ≤ 40000)', () => {
      expect(isLowValueLease(NaN)).toBe(true)
    })
  })
})
