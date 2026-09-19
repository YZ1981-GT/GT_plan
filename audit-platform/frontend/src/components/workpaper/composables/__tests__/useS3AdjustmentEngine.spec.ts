/**
 * Unit Tests — S3 首次执行新准则调整 + 简化追溯调整法公式引擎
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/
 * Task: 3.4
 *
 * 已知值验证，覆盖 Requirement 6.1 的具体场景。
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcAdjustmentDiff,
  calcLeaseAdjust,
  calcSimplifiedRetro,
  type AdjustmentDiffInput,
  type LeaseAdjustInput,
  type SimplifiedRetroInput,
} from '../useS3AdjustmentEngine'

describe('useS3AdjustmentEngine', () => {
  // ── parseNum ────────────────────────────────────────────────

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
      expect(parseNum('-99')).toBe(-99)
    })

    it('NaN/Infinity→0', () => {
      expect(parseNum(NaN)).toBe(0)
      expect(parseNum(Infinity)).toBe(0)
      expect(parseNum(-Infinity)).toBe(0)
    })
  })

  // ── calcAdjustmentDiff (S3-4/6 首次执行新准则调整) ──────────

  describe('calcAdjustmentDiff', () => {
    it('标准场景：差异 = 新准则 - 原准则', () => {
      const input: AdjustmentDiffInput = {
        items: [
          { oldStandard: 1000, newStandard: 1200 },
          { oldStandard: 500, newStandard: 400 },
          { oldStandard: 800, newStandard: 800 },
        ],
      }
      const result = calcAdjustmentDiff(input)
      expect(result.diffs).toEqual([200, -100, 0])
      expect(result.totalDiff).toBe(100)
    })

    it('空数组→totalDiff=0', () => {
      const input: AdjustmentDiffInput = { items: [] }
      const result = calcAdjustmentDiff(input)
      expect(result.diffs).toEqual([])
      expect(result.totalDiff).toBe(0)
    })

    it('单项计算正确', () => {
      const input: AdjustmentDiffInput = {
        items: [{ oldStandard: 5000000, newStandard: 3500000 }],
      }
      const result = calcAdjustmentDiff(input)
      expect(result.diffs).toEqual([-1500000])
      expect(result.totalDiff).toBe(-1500000)
    })

    it('多项正负差异合计', () => {
      const input: AdjustmentDiffInput = {
        items: [
          { oldStandard: 100, newStandard: 150 },   // +50
          { oldStandard: 200, newStandard: 100 },   // -100
          { oldStandard: 300, newStandard: 500 },   // +200
          { oldStandard: 400, newStandard: 250 },   // -150
        ],
      }
      const result = calcAdjustmentDiff(input)
      expect(result.diffs).toEqual([50, -100, 200, -150])
      expect(result.totalDiff).toBe(0) // 正好抵消
    })

    it('原准则与新准则均为0时差异为0', () => {
      const input: AdjustmentDiffInput = {
        items: [{ oldStandard: 0, newStandard: 0 }],
      }
      const result = calcAdjustmentDiff(input)
      expect(result.diffs).toEqual([0])
      expect(result.totalDiff).toBe(0)
    })
  })

  // ── calcLeaseAdjust (S3-8 首次执行新租赁准则) ──────────────

  describe('calcLeaseAdjust', () => {
    it('使用权资产 = total - deduction', () => {
      const input: LeaseAdjustInput = {
        total: 1000000,
        deduction: 150000,
        components: [500000, 300000, 100000, -50000, -30000, -20000, -10000],
      }
      const result = calcLeaseAdjust(input)
      expect(result.rouAsset).toBe(850000)
    })

    it('租赁负债 = SUM(components)（正加负减）', () => {
      // F63 = F56+F57+F58-F59-F60-F61-F62
      const input: LeaseAdjustInput = {
        total: 1000000,
        deduction: 150000,
        components: [500000, 300000, 100000, -50000, -30000, -20000, -10000],
      }
      const result = calcLeaseAdjust(input)
      // 500000 + 300000 + 100000 - 50000 - 30000 - 20000 - 10000 = 790000
      expect(result.leaseLiability).toBe(790000)
    })

    it('空components→租赁负债=0', () => {
      const input: LeaseAdjustInput = {
        total: 500000,
        deduction: 100000,
        components: [],
      }
      const result = calcLeaseAdjust(input)
      expect(result.rouAsset).toBe(400000)
      expect(result.leaseLiability).toBe(0)
    })

    it('total=0且deduction=0时使用权资产=0', () => {
      const input: LeaseAdjustInput = {
        total: 0,
        deduction: 0,
        components: [100, -50],
      }
      const result = calcLeaseAdjust(input)
      expect(result.rouAsset).toBe(0)
      expect(result.leaseLiability).toBe(50)
    })

    it('deduction大于total时使用权资产为负', () => {
      const input: LeaseAdjustInput = {
        total: 100000,
        deduction: 200000,
        components: [],
      }
      const result = calcLeaseAdjust(input)
      expect(result.rouAsset).toBe(-100000)
    })
  })

  // ── calcSimplifiedRetro (S3-9/10 简化追溯调整法) ──────────

  describe('calcSimplifiedRetro', () => {
    it('标准折现计算：pvFactor = 1/(1+rate)^years', () => {
      const input: SimplifiedRetroInput = {
        items: [
          { amount: 1000000, years: 3, expired: false },
        ],
        discountRate: 0.05,
      }
      const result = calcSimplifiedRetro(input)
      // pvFactor = 1 / (1.05)^3 = 1 / 1.157625 ≈ 0.863838
      const expectedFactor = 1 / Math.pow(1.05, 3)
      expect(result.pvFactors[0]).toBeCloseTo(expectedFactor, 6)
      expect(result.pvAmounts[0]).toBeCloseTo(1000000 * expectedFactor, 2)
      expect(result.totalPV).toBeCloseTo(1000000 * expectedFactor, 2)
    })

    it('多项折现与到期混合', () => {
      const input: SimplifiedRetroInput = {
        items: [
          { amount: 1000000, years: 2, expired: false },
          { amount: 500000, years: 5, expired: false },
          { amount: 200000, years: 1, expired: true },  // 到期→0
        ],
        discountRate: 0.04,
      }
      const result = calcSimplifiedRetro(input)

      const pv1 = 1000000 / Math.pow(1.04, 2)
      const pv2 = 500000 / Math.pow(1.04, 5)

      expect(result.pvFactors[0]).toBeCloseTo(1 / Math.pow(1.04, 2), 6)
      expect(result.pvFactors[1]).toBeCloseTo(1 / Math.pow(1.04, 5), 6)
      expect(result.pvFactors[2]).toBe(0)  // expired

      expect(result.pvAmounts[0]).toBeCloseTo(pv1, 2)
      expect(result.pvAmounts[1]).toBeCloseTo(pv2, 2)
      expect(result.pvAmounts[2]).toBe(0)

      expect(result.totalPV).toBeCloseTo(pv1 + pv2, 2)
    })

    it('discountRate=0时pvFactor=1（无折现）', () => {
      const input: SimplifiedRetroInput = {
        items: [
          { amount: 500000, years: 10, expired: false },
          { amount: 300000, years: 5, expired: false },
        ],
        discountRate: 0,
      }
      const result = calcSimplifiedRetro(input)
      expect(result.pvFactors[0]).toBe(1)
      expect(result.pvFactors[1]).toBe(1)
      expect(result.pvAmounts[0]).toBe(500000)
      expect(result.pvAmounts[1]).toBe(300000)
      expect(result.totalPV).toBe(800000)
    })

    it('expired=true时pv=0', () => {
      const input: SimplifiedRetroInput = {
        items: [
          { amount: 1000000, years: 3, expired: true },
          { amount: 2000000, years: 5, expired: true },
        ],
        discountRate: 0.05,
      }
      const result = calcSimplifiedRetro(input)
      expect(result.pvFactors).toEqual([0, 0])
      expect(result.pvAmounts).toEqual([0, 0])
      expect(result.totalPV).toBe(0)
    })

    it('空数组→totalPV=0', () => {
      const input: SimplifiedRetroInput = {
        items: [],
        discountRate: 0.05,
      }
      const result = calcSimplifiedRetro(input)
      expect(result.pvFactors).toEqual([])
      expect(result.pvAmounts).toEqual([])
      expect(result.totalPV).toBe(0)
    })

    it('years=0时pvFactor=1（当期无折现）', () => {
      const input: SimplifiedRetroInput = {
        items: [{ amount: 100000, years: 0, expired: false }],
        discountRate: 0.05,
      }
      const result = calcSimplifiedRetro(input)
      // 1 / (1.05)^0 = 1
      expect(result.pvFactors[0]).toBe(1)
      expect(result.pvAmounts[0]).toBe(100000)
    })

    it('高折现率+长年份不产生NaN/Infinity', () => {
      const input: SimplifiedRetroInput = {
        items: [{ amount: 100000, years: 100, expired: false }],
        discountRate: 0.5,
      }
      const result = calcSimplifiedRetro(input)
      // (1.5)^100 极大，pvFactor 极小但有限
      expect(Number.isFinite(result.pvFactors[0])).toBe(true)
      expect(Number.isFinite(result.pvAmounts[0])).toBe(true)
      expect(Number.isFinite(result.totalPV)).toBe(true)
    })

    it('负金额正确折现', () => {
      const input: SimplifiedRetroInput = {
        items: [{ amount: -500000, years: 2, expired: false }],
        discountRate: 0.06,
      }
      const result = calcSimplifiedRetro(input)
      const expectedPV = -500000 / Math.pow(1.06, 2)
      expect(result.pvAmounts[0]).toBeCloseTo(expectedPV, 2)
      expect(result.totalPV).toBeCloseTo(expectedPV, 2)
    })

    it('小数年份（月份换算）正确折现', () => {
      // S3-9 剩余年限可能是小数：remainingYears = contractYears + months/12
      const input: SimplifiedRetroInput = {
        items: [{ amount: 1000000, years: 2.5, expired: false }],
        discountRate: 0.04,
      }
      const result = calcSimplifiedRetro(input)
      const expectedFactor = 1 / Math.pow(1.04, 2.5)
      expect(result.pvFactors[0]).toBeCloseTo(expectedFactor, 6)
      expect(result.pvAmounts[0]).toBeCloseTo(1000000 * expectedFactor, 2)
    })
  })
})
