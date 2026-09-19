import { describe, it, expect } from 'vitest'
import {
  calcInitialMeasurement,
  calcDepreciationPeriod,
  calcTerminationGainLoss,
  calcRemeasurement,
  calcDiscountFactor,
  calcLeasePaymentsPV,
  calcAnnuityPV,
  calcAnnuityDuePV,
  calcLiabilityAdjustment,
  calcScopeReduction,
  buildEqualPaymentSchedule,
  buildDiscountPeriods,
  deriveModificationType,
  isSeparateLease,
  suggestAccountingTreatment,
  estimateLiabilityAtDate,
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

  describe('H8-7 折现与变更重计量', () => {
    it('折现系数 1/(1+r)^n 对齐 xlsx H8-7', () => {
      expect(calcDiscountFactor(0.05, 0)).toBeCloseTo(1, 6)
      expect(calcDiscountFactor(0.05, 1)).toBeCloseTo(0.9524, 4)
      expect(calcDiscountFactor(0.05, 9)).toBeCloseTo(0.6446, 4)
    })

    it('租赁付款额现值 Σ(付款×折现系数) — 样例约 355,391', () => {
      const payments = Array.from({ length: 9 }, (_, i) => ({
        amount: 50_000,
        periods: i + 1,
      }))
      const pv = calcLeasePaymentsPV(payments, 0.05)
      expect(pv).toBeCloseTo(355_391.08, 0)
    })

    it('等额年金现值（期末 / 期初）', () => {
      expect(calcAnnuityPV(50_000, 0.05, 9)).toBeCloseTo(355_391.08, 0)
      expect(calcAnnuityPV(50_000, 0, 4)).toBe(200_000)
      const due = calcAnnuityDuePV(50_000, 0.05, 9)
      expect(due).toBeCloseTo(355_391.08 * 1.05, 0)
    })

    it('期初折现期 0..n-1，期末 1..n', () => {
      expect(buildDiscountPeriods(3, '期初')).toEqual([0, 1, 2])
      expect(buildDiscountPeriods(3, '期末')).toEqual([1, 2, 3])
    })

    it('等额折现表合计等于年金 PV', () => {
      const { rows, totalPV } = buildEqualPaymentSchedule(50_000, 0.05, 9, '期末')
      expect(rows).toHaveLength(9)
      expect(totalPV).toBeCloseTo(calcAnnuityPV(50_000, 0.05, 9), 4)
    })

    it('负债调整额 = 新PV − 账面负债；ROU 重计量 = 旧ROU + 调整额', () => {
      const adj = calcLiabilityAdjustment(378_173.6, 350_000)
      expect(adj).toBeCloseTo(28_173.6, 2)
      expect(calcRemeasurement(340_000, adj)).toBeCloseTo(368_173.6, 2)
    })

    it('范围减少按比例终止并计算损益', () => {
      const sr = calcScopeReduction(100_000, 80_000, 0.25)
      expect(sr.terminatedLiability).toBe(25_000)
      expect(sr.terminatedROU).toBe(20_000)
      expect(sr.gainLoss).toBe(5_000)
      expect(sr.remainingROU).toBe(60_000)
      expect(sr.rouAdjustment).toBe(-20_000)
    })

    it('H8-6 参数滚动估算变更日负债', () => {
      // 初始 100000，5%，年付 20000，过 1 年：100000*1.05-20000=85000
      const est = estimateLiabilityAtDate({
        leaseLiabilityInitial: 100_000,
        discountRatePct: 5,
        rentalPerPeriod: 20_000,
        leaseTermMonths: 60,
        yearsElapsed: 1.2,
      })
      expect(est).toBeCloseTo(85_000, 0)
    })
  })

  describe('H8-7 判定树 deriveModificationType', () => {
    it('扩大范围+对价相当 → 单独租赁', () => {
      expect(deriveModificationType('是', '是', '')).toBe('单独租赁')
      expect(isSeparateLease('是', '是')).toBe(true)
      // 即使误勾范围减少，单独租赁优先
      expect(deriveModificationType('是', '是', '是')).toBe('单独租赁')
    })

    it('非单独租赁 + 范围减少 → 范围减少', () => {
      expect(deriveModificationType('是', '否', '是')).toBe('范围减少')
      expect(deriveModificationType('否', '否', '是')).toBe('范围减少')
    })

    it('非单独租赁 + 非范围减少 → 其他变更', () => {
      expect(deriveModificationType('否', '是', '否')).toBe('其他变更')
      expect(deriveModificationType('是', '否', '否')).toBe('其他变更')
    })

    it('1.2 未答 → 待定空串（避免与 1.1 同时显示「是」）', () => {
      expect(deriveModificationType('否', '否', '')).toBe('')
      expect(isSeparateLease('是', '否')).toBe(false)
    })

    it('会计处理建议文案非空', () => {
      expect(suggestAccountingTreatment('单独租赁')).toContain('单独租赁')
      expect(suggestAccountingTreatment('范围减少')).toContain('损益')
      expect(suggestAccountingTreatment('其他变更')).toContain('重新计量')
      expect(suggestAccountingTreatment('')).toBe('')
    })
  })
})
