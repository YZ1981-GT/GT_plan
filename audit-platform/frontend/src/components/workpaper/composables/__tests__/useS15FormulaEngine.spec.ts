/**
 * Unit Tests — S15 每股收益与净资产收益率公式引擎
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/
 * Task: 3.1
 *
 * 已知值验证，互补 PBT 测试。
 * 覆盖 Properties P2(加权平均股数), P3(基本EPS), P4(ROE) 的具体场景。
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcWeightedAvgShares,
  calcBasicEps,
  calcDilutedEps,
  calcDilutedRoe,
  calcDilutedRoeEx,
  calcRightsIssueAdjustedShares,
  type EpsInput,
  type DilutedEpsInput,
  type RoeInput,
} from '../useS15FormulaEngine'

// ─── helper: 默认 EpsInput ──────────────────────────────────

function makeEpsInput(overrides: Partial<EpsInput> = {}): EpsInput {
  return {
    npAttrParent: 100_000_000,     // 1亿
    npAttrParentEx: 90_000_000,    // 9000万
    shareOpening: 500_000_000,     // 5亿股
    shareCapitalized: 50_000_000,  // 5000万转增
    newIssue: { count: 100_000_000, monthsToEnd: 6 },
    debtToEquity: { count: 20_000_000, monthsToEnd: 3 },
    repurchase: { count: 10_000_000, monthsToEnd: 4 },
    merged: 0,
    periodMonths: 12,
    ...overrides,
  }
}

function makeRoeInput(overrides: Partial<RoeInput> = {}): RoeInput {
  return {
    np: 100_000_000,
    npEx: 90_000_000,
    e0: 2_000_000_000,
    eEnd: 2_200_000_000,
    minorityEquity: 200_000_000,
    ei: 300_000_000,
    mi: 6,
    ej: 100_000_000,
    mj: 3,
    ek: 50_000_000,
    mk: 2,
    m0: 12,
    ...overrides,
  }
}

describe('useS15FormulaEngine', () => {
  // ── parseNum ────────────────────────────────────────────────

  describe('parseNum', () => {
    it('正常数值直接返回', () => {
      expect(parseNum(100)).toBe(100)
    })

    it('null/undefined/空字符串→0', () => {
      expect(parseNum(null)).toBe(0)
      expect(parseNum(undefined)).toBe(0)
      expect(parseNum('')).toBe(0)
    })

    it('字符串数值解析', () => {
      expect(parseNum('123.45')).toBe(123.45)
    })

    it('NaN/Infinity→0', () => {
      expect(parseNum(NaN)).toBe(0)
      expect(parseNum(Infinity)).toBe(0)
      expect(parseNum(-Infinity)).toBe(0)
    })
  })

  // ── calcWeightedAvgShares (Property P2) ─────────────────────

  describe('calcWeightedAvgShares', () => {
    it('标准场景：b=b0+b1+(c1*c2/m0+d1*d2/m0)-(e1*e2/m0)-b4', () => {
      const input = makeEpsInput()
      // b = 500_000_000 + 50_000_000
      //   + (100_000_000*6/12 + 20_000_000*3/12)
      //   - (10_000_000*4/12) - 0
      // = 550_000_000 + (50_000_000 + 5_000_000) - 3_333_333.33...
      const expected = 500_000_000 + 50_000_000
        + (100_000_000 * 6 / 12 + 20_000_000 * 3 / 12)
        - (10_000_000 * 4 / 12) - 0
      expect(calcWeightedAvgShares(input)).toBeCloseTo(expected, 2)
    })

    it('m0=0时返回0（不可计算）', () => {
      const input = makeEpsInput({ periodMonths: 0 })
      expect(calcWeightedAvgShares(input)).toBe(0)
    })

    it('m0为负时返回0', () => {
      const input = makeEpsInput({ periodMonths: -1 })
      expect(calcWeightedAvgShares(input)).toBe(0)
    })

    it('无新发无回购无债转股：b=b0+b1-b4', () => {
      const input = makeEpsInput({
        newIssue: { count: 0, monthsToEnd: 0 },
        debtToEquity: { count: 0, monthsToEnd: 0 },
        repurchase: { count: 0, monthsToEnd: 0 },
        merged: 10_000_000,
      })
      expect(calcWeightedAvgShares(input)).toBe(500_000_000 + 50_000_000 - 10_000_000)
    })

    it('仅期初股份（所有其他为0）', () => {
      const input = makeEpsInput({
        shareCapitalized: 0,
        newIssue: { count: 0, monthsToEnd: 0 },
        debtToEquity: { count: 0, monthsToEnd: 0 },
        repurchase: { count: 0, monthsToEnd: 0 },
        merged: 0,
      })
      expect(calcWeightedAvgShares(input)).toBe(500_000_000)
    })

    it('半年报（m0=6）加权不同', () => {
      const input = makeEpsInput({
        periodMonths: 6,
        newIssue: { count: 100_000_000, monthsToEnd: 3 },
        debtToEquity: { count: 0, monthsToEnd: 0 },
        repurchase: { count: 0, monthsToEnd: 0 },
      })
      // b = 500M + 50M + (100M*3/6) - 0 - 0 = 600M
      expect(calcWeightedAvgShares(input)).toBe(600_000_000)
    })
  })

  // ── calcBasicEps (Property P3) ──────────────────────────────

  describe('calcBasicEps', () => {
    it('标准场景计算正确', () => {
      const input = makeEpsInput({
        shareCapitalized: 0,
        newIssue: { count: 0, monthsToEnd: 0 },
        debtToEquity: { count: 0, monthsToEnd: 0 },
        repurchase: { count: 0, monthsToEnd: 0 },
        merged: 0,
      })
      // b = 500_000_000
      // eps = 100_000_000 / 500_000_000 = 0.2
      // epsEx = 90_000_000 / 500_000_000 = 0.18
      const result = calcBasicEps(input)
      expect(result.eps).toBeCloseTo(0.2, 6)
      expect(result.epsEx).toBeCloseTo(0.18, 6)
      expect(result.unable).toBe(false)
    })

    it('加权平均股数为0时返回unable=true', () => {
      const input = makeEpsInput({
        shareOpening: 0,
        shareCapitalized: 0,
        newIssue: { count: 0, monthsToEnd: 0 },
        debtToEquity: { count: 0, monthsToEnd: 0 },
        repurchase: { count: 0, monthsToEnd: 0 },
        merged: 0,
      })
      const result = calcBasicEps(input)
      expect(result.unable).toBe(true)
      expect(result.eps).toBe(0)
      expect(result.epsEx).toBe(0)
    })

    it('m0=0时返回unable=true', () => {
      const input = makeEpsInput({ periodMonths: 0 })
      const result = calcBasicEps(input)
      expect(result.unable).toBe(true)
    })

    it('净利润为负时EPS为负', () => {
      const input = makeEpsInput({
        npAttrParent: -50_000_000,
        npAttrParentEx: -60_000_000,
        shareCapitalized: 0,
        newIssue: { count: 0, monthsToEnd: 0 },
        debtToEquity: { count: 0, monthsToEnd: 0 },
        repurchase: { count: 0, monthsToEnd: 0 },
        merged: 0,
      })
      const result = calcBasicEps(input)
      expect(result.eps).toBeCloseTo(-0.1, 6)
      expect(result.epsEx).toBeCloseTo(-0.12, 6)
      expect(result.unable).toBe(false)
    })
  })

  // ── calcDilutedEps ─────────────────────────────────────────

  describe('calcDilutedEps', () => {
    it('标准稀释EPS计算', () => {
      const input: DilutedEpsInput = {
        npAttrParent: 100_000_000,
        weightedAvgShares: 500_000_000,
        dilutionInterest: 5_000_000,
        conversionCost: 1_000_000,
        taxRate: 0.25,
        dilutionShares: 50_000_000,
        dilutionMonths: 6,
        periodMonths: 12,
      }
      // numerator = 100M + (5M - 1M)*(1-0.25) = 100M + 3M = 103M
      // denominator = 500M + 50M*6/12 = 500M + 25M = 525M
      // dilutedEps = 103M / 525M ≈ 0.1962
      const result = calcDilutedEps(input)
      expect(result.dilutedEps).toBeCloseTo(103_000_000 / 525_000_000, 6)
      expect(result.unable).toBe(false)
    })

    it('分母为0时unable=true', () => {
      const input: DilutedEpsInput = {
        npAttrParent: 100_000_000,
        weightedAvgShares: 0,
        dilutionInterest: 0,
        conversionCost: 0,
        taxRate: 0.25,
        dilutionShares: 0,
        dilutionMonths: 0,
        periodMonths: 12,
      }
      const result = calcDilutedEps(input)
      expect(result.unable).toBe(true)
    })

    it('m0=0时unable=true', () => {
      const input: DilutedEpsInput = {
        npAttrParent: 100_000_000,
        weightedAvgShares: 500_000_000,
        dilutionInterest: 0,
        conversionCost: 0,
        taxRate: 0.25,
        dilutionShares: 0,
        dilutionMonths: 0,
        periodMonths: 0,
      }
      const result = calcDilutedEps(input)
      expect(result.unable).toBe(true)
    })

    it('无稀释时等于基本EPS', () => {
      const input: DilutedEpsInput = {
        npAttrParent: 100_000_000,
        weightedAvgShares: 500_000_000,
        dilutionInterest: 0,
        conversionCost: 0,
        taxRate: 0.25,
        dilutionShares: 0,
        dilutionMonths: 0,
        periodMonths: 12,
      }
      const result = calcDilutedEps(input)
      expect(result.dilutedEps).toBeCloseTo(0.2, 6)
      expect(result.unable).toBe(false)
    })
  })

  // ── calcDilutedRoe (Property P4) ──────────────────────────

  describe('calcDilutedRoe', () => {
    it('标准场景全面摊薄与加权平均ROE', () => {
      const input = makeRoeInput()
      // E = eEnd - minority = 2.2B - 0.2B = 2B
      // fullyDiluted = 100M / 2B = 0.05
      // 加权平均净资产 = 2B + 100M/2 + 300M*6/12 - 100M*3/12 + 50M*2/12
      //               = 2B + 50M + 150M - 25M + 8.33M = 2_183_333_333.33
      // weightedAvg = 100M / 2_183_333_333.33
      const result = calcDilutedRoe(input)
      expect(result.fullyDiluted).toBeCloseTo(100_000_000 / 2_000_000_000, 8)
      const wna = 2_000_000_000 + 100_000_000 / 2
        + 300_000_000 * 6 / 12
        - 100_000_000 * 3 / 12
        + 50_000_000 * 2 / 12
      expect(result.weightedAvg).toBeCloseTo(100_000_000 / wna, 8)
      expect(result.unable).toBe(false)
    })

    it('期末净资产为0时unable=true', () => {
      const input = makeRoeInput({ eEnd: 200_000_000, minorityEquity: 200_000_000 })
      // E = 200M - 200M = 0
      const result = calcDilutedRoe(input)
      expect(result.unable).toBe(true)
    })

    it('m0=0时unable=true', () => {
      const input = makeRoeInput({ m0: 0 })
      const result = calcDilutedRoe(input)
      expect(result.unable).toBe(true)
    })

    it('加权平均净资产为0时unable=true（fullyDiluted仍可计算）', () => {
      // 构造使 E0+NP/2+Ei*Mi/M0-Ej*Mj/M0+Ek*Mk/M0 = 0 的输入
      // E0=0, NP=0, Ei=0, Ej=0, Ek=0
      const input = makeRoeInput({
        np: 100_000_000,
        e0: 0,
        ei: 0, mi: 0,
        ej: 0, mj: 0,
        ek: 0, mk: 0,
        eEnd: 2_000_000_000,
        minorityEquity: 0,
      })
      // 加权平均净资产 = 0 + 100M/2 + 0 - 0 + 0 = 50M ≠ 0
      // 实际需要 e0 + np/2 = 0，即 np = 0 且 e0 = 0
      const input2 = makeRoeInput({
        np: 0,
        e0: 0,
        ei: 0, mi: 0,
        ej: 0, mj: 0,
        ek: 0, mk: 0,
        eEnd: 2_000_000_000,
        minorityEquity: 0,
      })
      const result = calcDilutedRoe(input2)
      expect(result.weightedAvg).toBe(0)
      // fullyDiluted = 0 / 2B = 0
      expect(result.fullyDiluted).toBe(0)
      expect(result.unable).toBe(true)
    })

    it('净利润为负时ROE为负', () => {
      const input = makeRoeInput({ np: -50_000_000 })
      const result = calcDilutedRoe(input)
      expect(result.fullyDiluted).toBeLessThan(0)
      expect(result.unable).toBe(false)
    })
  })

  // ── calcDilutedRoeEx ──────────────────────────────────────

  describe('calcDilutedRoeEx', () => {
    it('扣非ROE使用npEx作为分子', () => {
      const input = makeRoeInput()
      const result = calcDilutedRoeEx(input)
      // fullyDilutedEx = npEx / E = 90M / 2B = 0.045
      expect(result.fullyDilutedEx).toBeCloseTo(90_000_000 / 2_000_000_000, 8)
      expect(result.unable).toBe(false)
    })

    it('加权平均净资产分母中NP/2用归母净利润（非扣非）', () => {
      const input = makeRoeInput({
        np: 100_000_000,
        npEx: 50_000_000,
        e0: 1_000_000_000,
        ei: 0, mi: 0,
        ej: 0, mj: 0,
        ek: 0, mk: 0,
        eEnd: 1_200_000_000,
        minorityEquity: 0,
      })
      const result = calcDilutedRoeEx(input)
      // 加权平均净资产 = 1B + 100M/2 = 1.05B
      // weightedAvgEx = 50M / 1.05B
      expect(result.weightedAvgEx).toBeCloseTo(50_000_000 / 1_050_000_000, 8)
    })
  })

  // ── calcRightsIssueAdjustedShares (Req 2.4) ──────────────

  describe('calcRightsIssueAdjustedShares', () => {
    it('标准配股调整', () => {
      const result = calcRightsIssueAdjustedShares({
        baseWeightedAvgShares: 500_000_000,
        rightsRatio: 0.3,
        exRightsPrice: 8,
        marketPriceBefore: 10,
      })
      // f = 10 / 8 = 1.25
      // adjusted = 500M * 1.25 = 625M
      expect(result.adjustedShares).toBe(625_000_000)
      expect(result.unable).toBe(false)
    })

    it('除权价为0时unable=true', () => {
      const result = calcRightsIssueAdjustedShares({
        baseWeightedAvgShares: 500_000_000,
        rightsRatio: 0.3,
        exRightsPrice: 0,
        marketPriceBefore: 10,
      })
      expect(result.unable).toBe(true)
    })

    it('配股前市价等于除权价时调整系数=1', () => {
      const result = calcRightsIssueAdjustedShares({
        baseWeightedAvgShares: 500_000_000,
        rightsRatio: 0.3,
        exRightsPrice: 10,
        marketPriceBefore: 10,
      })
      expect(result.adjustedShares).toBe(500_000_000)
    })
  })
})
