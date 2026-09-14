/**
 * Unit Tests — S4 非货币性资产交换公式引擎
 *
 * Spec: .kiro/specs/s-special-transaction-workpapers/
 * Task: 3.1
 *
 * 已知值验证，互补 PBT 测试。
 * 覆盖 Properties P2(交换损益), P3(商业实质判断) 的具体场景。
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcExchangeGainLoss,
  judgeApplicable,
  judgeCommercialSubstance,
  type S4ExchangeInput,
  type CommercialSubstanceInput,
} from '../useS4FormulaEngine'

// ─── parseNum ────────────────────────────────────────────────

describe('useS4FormulaEngine', () => {
  describe('parseNum', () => {
    it('正常数值直接返回', () => {
      expect(parseNum(100)).toBe(100)
      expect(parseNum(-50.5)).toBe(-50.5)
    })

    it('null/undefined/空字符串→0', () => {
      expect(parseNum(null)).toBe(0)
      expect(parseNum(undefined)).toBe(0)
      expect(parseNum('')).toBe(0)
    })

    it('字符串数值解析', () => {
      expect(parseNum('123.45')).toBe(123.45)
      expect(parseNum('-200')).toBe(-200)
    })

    it('NaN/Infinity→0', () => {
      expect(parseNum(NaN)).toBe(0)
      expect(parseNum(Infinity)).toBe(0)
      expect(parseNum(-Infinity)).toBe(0)
    })
  })

  // ─── calcExchangeGainLoss (Property P2) ────────────────────

  describe('calcExchangeGainLoss', () => {
    it('标准场景：换出公允>账面 → 正损益', () => {
      const input: S4ExchangeInput = {
        inFairValue: 1_000_000,
        outFairValue: 800_000,
        outBookValue: 600_000,
        taxes: 50_000,
      }
      const result = calcExchangeGainLoss(input)
      // gainLoss = 800_000 - 600_000 = 200_000
      expect(result.gainLoss).toBe(200_000)
      // inCost = 800_000 + 50_000 = 850_000
      expect(result.inCost).toBe(850_000)
    })

    it('换出公允<账面 → 负损益（损失）', () => {
      const input: S4ExchangeInput = {
        inFairValue: 500_000,
        outFairValue: 400_000,
        outBookValue: 600_000,
        taxes: 30_000,
      }
      const result = calcExchangeGainLoss(input)
      // gainLoss = 400_000 - 600_000 = -200_000
      expect(result.gainLoss).toBe(-200_000)
      // inCost = 400_000 + 30_000 = 430_000
      expect(result.inCost).toBe(430_000)
    })

    it('换出公允=账面 → 损益为0', () => {
      const input: S4ExchangeInput = {
        inFairValue: 1_000_000,
        outFairValue: 500_000,
        outBookValue: 500_000,
        taxes: 10_000,
      }
      const result = calcExchangeGainLoss(input)
      expect(result.gainLoss).toBe(0)
      expect(result.inCost).toBe(510_000)
    })

    it('税费为0时换入成本=换出公允', () => {
      const input: S4ExchangeInput = {
        inFairValue: 1_000_000,
        outFairValue: 800_000,
        outBookValue: 700_000,
        taxes: 0,
      }
      const result = calcExchangeGainLoss(input)
      expect(result.gainLoss).toBe(100_000)
      expect(result.inCost).toBe(800_000)
    })

    it('所有值为0', () => {
      const input: S4ExchangeInput = {
        inFairValue: 0,
        outFairValue: 0,
        outBookValue: 0,
        taxes: 0,
      }
      const result = calcExchangeGainLoss(input)
      expect(result.gainLoss).toBe(0)
      expect(result.inCost).toBe(0)
    })

    it('大金额场景（亿级）', () => {
      const input: S4ExchangeInput = {
        inFairValue: 500_000_000,
        outFairValue: 300_000_000,
        outBookValue: 250_000_000,
        taxes: 15_000_000,
      }
      const result = calcExchangeGainLoss(input)
      expect(result.gainLoss).toBe(50_000_000)
      expect(result.inCost).toBe(315_000_000)
    })
  })

  // ─── judgeApplicable (Property P3) ─────────────────────────

  describe('judgeApplicable', () => {
    it('6项排除全为false → 适用（true）', () => {
      const input: CommercialSubstanceInput = {
        exclusions: [false, false, false, false, false, false],
        cashflowDifferent: true,
      }
      expect(judgeApplicable(input)).toBe(true)
    })

    it('任一排除为true → 不适用（false）', () => {
      const input: CommercialSubstanceInput = {
        exclusions: [false, false, true, false, false, false],
        cashflowDifferent: true,
      }
      expect(judgeApplicable(input)).toBe(false)
    })

    it('所有排除为true → 不适用（false）', () => {
      const input: CommercialSubstanceInput = {
        exclusions: [true, true, true, true, true, true],
        cashflowDifferent: false,
      }
      expect(judgeApplicable(input)).toBe(false)
    })

    it('仅第一项排除为true → 不适用（false）', () => {
      const input: CommercialSubstanceInput = {
        exclusions: [true, false, false, false, false, false],
        cashflowDifferent: true,
      }
      expect(judgeApplicable(input)).toBe(false)
    })

    it('仅最后一项排除为true → 不适用（false）', () => {
      const input: CommercialSubstanceInput = {
        exclusions: [false, false, false, false, false, true],
        cashflowDifferent: true,
      }
      expect(judgeApplicable(input)).toBe(false)
    })

    it('排除数组长度不为6 → 不适用（false）', () => {
      const input: CommercialSubstanceInput = {
        exclusions: [false, false, false, false, false],
        cashflowDifferent: true,
      }
      expect(judgeApplicable(input)).toBe(false)
    })

    it('空排除数组 → 不适用（false）', () => {
      const input: CommercialSubstanceInput = {
        exclusions: [],
        cashflowDifferent: true,
      }
      expect(judgeApplicable(input)).toBe(false)
    })

    it('cashflowDifferent不影响适用性判断', () => {
      const input1: CommercialSubstanceInput = {
        exclusions: [false, false, false, false, false, false],
        cashflowDifferent: false,
      }
      const input2: CommercialSubstanceInput = {
        exclusions: [false, false, false, false, false, false],
        cashflowDifferent: true,
      }
      // 适用性判断只看exclusions
      expect(judgeApplicable(input1)).toBe(true)
      expect(judgeApplicable(input2)).toBe(true)
    })
  })

  // ─── judgeCommercialSubstance (Property P3) ────────────────

  describe('judgeCommercialSubstance', () => {
    it('cashflowDifferent=true → 具有商业实质', () => {
      const input: CommercialSubstanceInput = {
        exclusions: [false, false, false, false, false, false],
        cashflowDifferent: true,
      }
      expect(judgeCommercialSubstance(input)).toBe(true)
    })

    it('cashflowDifferent=false → 不具有商业实质', () => {
      const input: CommercialSubstanceInput = {
        exclusions: [false, false, false, false, false, false],
        cashflowDifferent: false,
      }
      expect(judgeCommercialSubstance(input)).toBe(false)
    })

    it('exclusions不影响商业实质判断', () => {
      const input: CommercialSubstanceInput = {
        exclusions: [true, true, true, true, true, true],
        cashflowDifferent: true,
      }
      // 商业实质只看cashflowDifferent
      expect(judgeCommercialSubstance(input)).toBe(true)
    })
  })
})
