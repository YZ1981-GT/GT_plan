/**
 * useI1AmortizationEngine — Vitest 单元测试
 *
 * 覆盖全部纯函数的核心逻辑和边界情况。
 * 每个函数 3-5 个测试用例，涵盖正常值、零值、负数、除零保护、会计场景。
 */
import { describe, it, expect } from 'vitest'
import {
  calcStraightLineAmort,
  calcRemainingLifeAmort,
  calcAmortWithImpairment,
  calcDcfPresentValue,
  calcTerminalValue,
  calcRecoverableAmount,
  calcImpairmentAmount,
} from '../useI1AmortizationEngine'

describe('useI1AmortizationEngine', () => {
  // ─── calcStraightLineAmort ──────────────────────────────────────────────────

  describe('calcStraightLineAmort', () => {
    it('正常直线法月摊销', () => {
      // (100000 - 5000) / 120 = 791.6667
      expect(calcStraightLineAmort(100000, 5000, 120)).toBeCloseTo(791.6667, 2)
    })

    it('残值为0', () => {
      // 60000 / 60 = 1000
      expect(calcStraightLineAmort(60000, 0, 60)).toBe(1000)
    })

    it('使用寿命月数为0 → 返回0（除零保护）', () => {
      expect(calcStraightLineAmort(100000, 5000, 0)).toBe(0)
    })

    it('使用寿命月数为负数 → 返回0', () => {
      expect(calcStraightLineAmort(100000, 5000, -12)).toBe(0)
    })

    it('原值等于残值 → 月摊销为0', () => {
      expect(calcStraightLineAmort(50000, 50000, 60)).toBe(0)
    })
  })

  // ─── calcRemainingLifeAmort ─────────────────────────────────────────────────

  describe('calcRemainingLifeAmort', () => {
    it('正常剩余年限法（不含减值 impairment=0）', () => {
      // (100000 - 5000 - 30000 - 0) / 48 = 1354.1667
      expect(calcRemainingLifeAmort(100000, 5000, 30000, 0, 48)).toBeCloseTo(1354.1667, 2)
    })

    it('含累计摊销和减值', () => {
      // (200000 - 10000 - 60000 - 20000) / 36 = 3055.5556
      expect(calcRemainingLifeAmort(200000, 10000, 60000, 20000, 36)).toBeCloseTo(3055.5556, 2)
    })

    it('剩余月数为0 → 返回0（已摊销完毕）', () => {
      expect(calcRemainingLifeAmort(100000, 5000, 30000, 0, 0)).toBe(0)
    })

    it('剩余月数为负数 → 返回0', () => {
      expect(calcRemainingLifeAmort(100000, 5000, 30000, 0, -5)).toBe(0)
    })

    it('摊销基数为负（累计摊销+减值>原值-残值）→ 返回负数', () => {
      // (100000 - 5000 - 80000 - 20000) / 12 = -5000/12 = -416.6667
      const result = calcRemainingLifeAmort(100000, 5000, 80000, 20000, 12)
      expect(result).toBeCloseTo(-416.6667, 2)
    })
  })

  // ─── calcAmortWithImpairment ────────────────────────────────────────────────

  describe('calcAmortWithImpairment', () => {
    it('减值后重算摊销基数', () => {
      // (500000 - 25000 - 150000 - 50000) / 60 = 4583.3333
      expect(calcAmortWithImpairment(500000, 25000, 150000, 50000, 60)).toBeCloseTo(4583.3333, 2)
    })

    it('与calcRemainingLifeAmort同参数结果一致', () => {
      const params: [number, number, number, number, number] = [200000, 10000, 60000, 20000, 36]
      expect(calcAmortWithImpairment(...params)).toBe(calcRemainingLifeAmort(...params))
    })

    it('剩余月数为0 → 返回0', () => {
      expect(calcAmortWithImpairment(100000, 0, 50000, 10000, 0)).toBe(0)
    })

    it('减值准备较大时基数变小', () => {
      // (100000 - 0 - 20000 - 60000) / 24 = 20000/24 = 833.3333
      expect(calcAmortWithImpairment(100000, 0, 20000, 60000, 24)).toBeCloseTo(833.3333, 2)
    })

    it('全部已摊销完（基数=0）', () => {
      // (100000 - 0 - 80000 - 20000) / 12 = 0
      expect(calcAmortWithImpairment(100000, 0, 80000, 20000, 12)).toBe(0)
    })
  })

  // ─── calcDcfPresentValue ────────────────────────────────────────────────────

  describe('calcDcfPresentValue', () => {
    it('单期现金流折现', () => {
      // 10000 / (1+0.1)^1 = 9090.9091
      expect(calcDcfPresentValue([10000], 0.1)).toBeCloseTo(9090.9091, 2)
    })

    it('多期现金流折现（5年）', () => {
      // PV = 10000/(1.08)^1 + 12000/(1.08)^2 + 14000/(1.08)^3 + 16000/(1.08)^4 + 18000/(1.08)^5
      const cfs = [10000, 12000, 14000, 16000, 18000]
      const rate = 0.08
      let expected = 0
      for (let i = 0; i < cfs.length; i++) {
        expected += cfs[i] / Math.pow(1 + rate, i + 1)
      }
      expect(calcDcfPresentValue(cfs, rate)).toBeCloseTo(expected, 2)
    })

    it('空数组 → 返回0', () => {
      expect(calcDcfPresentValue([], 0.1)).toBe(0)
    })

    it('折现率为0 → 返回0（无效折现率）', () => {
      expect(calcDcfPresentValue([10000, 20000], 0)).toBe(0)
    })

    it('折现率为负 → 返回0（无效折现率）', () => {
      expect(calcDcfPresentValue([10000, 20000], -0.05)).toBe(0)
    })

    it('高折现率使远期现金流价值极低', () => {
      // 折现率50%: 10000/(1.5)^1 + 10000/(1.5)^2 = 6666.67 + 4444.44 = 11111.11
      expect(calcDcfPresentValue([10000, 10000], 0.5)).toBeCloseTo(11111.1111, 2)
    })
  })

  // ─── calcTerminalValue ──────────────────────────────────────────────────────

  describe('calcTerminalValue', () => {
    it('正常Gordon模型终值', () => {
      // 10000 / (0.10 - 0.03) = 142857.1429
      expect(calcTerminalValue(10000, 0.10, 0.03)).toBeCloseTo(142857.1429, 2)
    })

    it('增长率为0（无增长永续年金）', () => {
      // 5000 / (0.08 - 0) = 62500
      expect(calcTerminalValue(5000, 0.08, 0)).toBe(62500)
    })

    it('增长率接近折现率 → 终值极大', () => {
      // 10000 / (0.10 - 0.099) = 10000 / 0.001 = 10000000
      expect(calcTerminalValue(10000, 0.10, 0.099)).toBeCloseTo(10000000, 0)
    })

    it('增长率等于折现率 → 返回0（Gordon模型无效）', () => {
      expect(calcTerminalValue(10000, 0.08, 0.08)).toBe(0)
    })

    it('增长率大于折现率 → 返回0（Gordon模型无效）', () => {
      expect(calcTerminalValue(10000, 0.05, 0.08)).toBe(0)
    })
  })

  // ─── calcRecoverableAmount ──────────────────────────────────────────────────

  describe('calcRecoverableAmount', () => {
    it('公允价值 > 使用价值 → 取公允价值', () => {
      expect(calcRecoverableAmount(80000, 70000)).toBe(80000)
    })

    it('使用价值 > 公允价值 → 取使用价值', () => {
      expect(calcRecoverableAmount(50000, 65000)).toBe(65000)
    })

    it('两者相等 → 返回该值', () => {
      expect(calcRecoverableAmount(100000, 100000)).toBe(100000)
    })

    it('两者均为0', () => {
      expect(calcRecoverableAmount(0, 0)).toBe(0)
    })

    it('负值场景（处置费用超过公允价值）', () => {
      // fairValueLessDisposal可能为负（处置费高于公允价值）
      expect(calcRecoverableAmount(-5000, 30000)).toBe(30000)
    })
  })

  // ─── calcImpairmentAmount ───────────────────────────────────────────────────

  describe('calcImpairmentAmount', () => {
    it('需计提减值（账面 > 可收回）', () => {
      // 100000 - 70000 = 30000
      expect(calcImpairmentAmount(100000, 70000)).toBe(30000)
    })

    it('不需计提减值（可收回 >= 账面）', () => {
      expect(calcImpairmentAmount(50000, 60000)).toBe(0)
    })

    it('账面等于可收回 → 不计提', () => {
      expect(calcImpairmentAmount(80000, 80000)).toBe(0)
    })

    it('减值金额上限为账面净值', () => {
      // bookValue=50000, recoverable=0 → raw=50000, min(50000, 50000)=50000
      expect(calcImpairmentAmount(50000, 0)).toBe(50000)
    })

    it('可收回为负值 → 减值上限为bookValue', () => {
      // bookValue=30000, recoverable=-10000 → raw=40000, min(40000, 30000)=30000
      expect(calcImpairmentAmount(30000, -10000)).toBe(30000)
    })
  })
})
