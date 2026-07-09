/**
 * Unit Tests — S20 营业收入扣除情况核查公式引擎
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/
 * Task: 3.2
 *
 * 已知值验证，互补 PBT 测试。
 * 覆盖 Property P5（营业收入扣除计算正确性）的具体场景。
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  parseNum,
  calcRevenueDeduction,
  useS20FormulaEngine,
  type RevenueDeductionInput,
} from '../useS20FormulaEngine'

// ─── helper: 默认 RevenueDeductionInput ─────────────────────

function makeInput(overrides: Partial<RevenueDeductionInput> = {}): RevenueDeductionInput {
  return {
    mainBusiness: [800_000, 500_000, 200_000, 100_000],  // 主营明细 4 项
    otherBusiness: [50_000, 30_000, 20_000, 10_000],      // 其他明细 4 项
    unrelatedRevenue: 80_000,       // 与主营无关
    noSubstanceRevenue: 20_000,     // 不具备商业实质
    ...overrides,
  }
}

describe('useS20FormulaEngine', () => {
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

  // ── calcRevenueDeduction (Property P5) ────────────────────

  describe('calcRevenueDeduction', () => {
    it('标准场景计算正确', () => {
      const input = makeInput()
      const result = calcRevenueDeduction(input)

      // mainBusinessTotal = 800K + 500K + 200K + 100K = 1,600,000
      expect(result.mainBusinessTotal).toBe(1_600_000)
      // otherBusinessTotal = 50K + 30K + 20K + 10K = 110,000
      expect(result.otherBusinessTotal).toBe(110_000)
      // revenue = 1,600,000 + 110,000 = 1,710,000
      expect(result.revenue).toBe(1_710_000)
      // deductionTotal = 80,000 + 20,000 = 100,000
      expect(result.deductionTotal).toBe(100_000)
      // deductionRatio = 100,000 / 1,710,000
      expect(result.deductionRatio).toBeCloseTo(100_000 / 1_710_000, 10)
      // revenueAfterDeduction = 1,710,000 - 100,000 = 1,610,000
      expect(result.revenueAfterDeduction).toBe(1_610_000)
      expect(result.unable).toBe(false)
    })

    it('revenue=0 时 unable=true，ratio=0', () => {
      const input = makeInput({
        mainBusiness: [],
        otherBusiness: [],
      })
      const result = calcRevenueDeduction(input)

      expect(result.revenue).toBe(0)
      expect(result.mainBusinessTotal).toBe(0)
      expect(result.otherBusinessTotal).toBe(0)
      expect(result.deductionRatio).toBe(0)
      expect(result.unable).toBe(true)
      // 扣除后金额 = 0 - 100,000 = -100,000（合法，只是表示超扣）
      expect(result.revenueAfterDeduction).toBe(-100_000)
    })

    it('空数组→SUM=0', () => {
      const input = makeInput({
        mainBusiness: [],
        otherBusiness: [],
        unrelatedRevenue: 0,
        noSubstanceRevenue: 0,
      })
      const result = calcRevenueDeduction(input)

      expect(result.revenue).toBe(0)
      expect(result.deductionTotal).toBe(0)
      expect(result.revenueAfterDeduction).toBe(0)
      expect(result.unable).toBe(true)
    })

    it('仅有主营业务（无其他业务）', () => {
      const input = makeInput({
        mainBusiness: [1_000_000],
        otherBusiness: [],
        unrelatedRevenue: 50_000,
        noSubstanceRevenue: 30_000,
      })
      const result = calcRevenueDeduction(input)

      expect(result.mainBusinessTotal).toBe(1_000_000)
      expect(result.otherBusinessTotal).toBe(0)
      expect(result.revenue).toBe(1_000_000)
      expect(result.deductionTotal).toBe(80_000)
      expect(result.deductionRatio).toBeCloseTo(80_000 / 1_000_000, 10)
      expect(result.revenueAfterDeduction).toBe(920_000)
      expect(result.unable).toBe(false)
    })

    it('仅有其他业务（无主营业务）', () => {
      const input = makeInput({
        mainBusiness: [],
        otherBusiness: [200_000, 300_000],
        unrelatedRevenue: 10_000,
        noSubstanceRevenue: 5_000,
      })
      const result = calcRevenueDeduction(input)

      expect(result.mainBusinessTotal).toBe(0)
      expect(result.otherBusinessTotal).toBe(500_000)
      expect(result.revenue).toBe(500_000)
      expect(result.deductionTotal).toBe(15_000)
      expect(result.deductionRatio).toBeCloseTo(15_000 / 500_000, 10)
      expect(result.revenueAfterDeduction).toBe(485_000)
      expect(result.unable).toBe(false)
    })

    it('扣除合计为0时 ratio=0', () => {
      const input = makeInput({
        unrelatedRevenue: 0,
        noSubstanceRevenue: 0,
      })
      const result = calcRevenueDeduction(input)

      expect(result.deductionTotal).toBe(0)
      expect(result.deductionRatio).toBe(0)
      expect(result.revenueAfterDeduction).toBe(result.revenue)
      expect(result.unable).toBe(false)
    })

    it('扣除后金额可以为负（扣除>收入）', () => {
      const input = makeInput({
        mainBusiness: [100_000],
        otherBusiness: [],
        unrelatedRevenue: 80_000,
        noSubstanceRevenue: 50_000,
      })
      const result = calcRevenueDeduction(input)

      expect(result.revenue).toBe(100_000)
      expect(result.deductionTotal).toBe(130_000)
      expect(result.revenueAfterDeduction).toBe(-30_000)
      expect(result.deductionRatio).toBeCloseTo(130_000 / 100_000, 10)
      expect(result.unable).toBe(false)
    })

    it('大额数值不溢出', () => {
      const input = makeInput({
        mainBusiness: [9_999_999_999, 8_888_888_888],
        otherBusiness: [7_777_777_777],
        unrelatedRevenue: 1_000_000_000,
        noSubstanceRevenue: 2_000_000_000,
      })
      const result = calcRevenueDeduction(input)

      expect(result.mainBusinessTotal).toBe(9_999_999_999 + 8_888_888_888)
      expect(result.otherBusinessTotal).toBe(7_777_777_777)
      expect(result.revenue).toBe(9_999_999_999 + 8_888_888_888 + 7_777_777_777)
      expect(result.deductionTotal).toBe(3_000_000_000)
      expect(Number.isFinite(result.deductionRatio)).toBe(true)
      expect(result.unable).toBe(false)
    })

    it('数组含非法值时parseNum降级为0', () => {
      const input: RevenueDeductionInput = {
        mainBusiness: [100_000, NaN, Infinity, -Infinity],
        otherBusiness: [50_000],
        unrelatedRevenue: NaN as unknown as number,
        noSubstanceRevenue: 0,
      }
      const result = calcRevenueDeduction(input)

      // NaN/Infinity 全降级为0
      expect(result.mainBusinessTotal).toBe(100_000)
      expect(result.otherBusinessTotal).toBe(50_000)
      expect(result.revenue).toBe(150_000)
      expect(result.deductionTotal).toBe(0)
      expect(result.unable).toBe(false)
    })

    it('不返回NaN或Infinity', () => {
      // 任何输入都不应该产出 NaN/Infinity
      const inputs: RevenueDeductionInput[] = [
        makeInput(),
        makeInput({ mainBusiness: [], otherBusiness: [] }),
        makeInput({ unrelatedRevenue: -999, noSubstanceRevenue: -999 }),
      ]
      for (const input of inputs) {
        const result = calcRevenueDeduction(input)
        expect(Number.isFinite(result.revenue)).toBe(true)
        expect(Number.isFinite(result.mainBusinessTotal)).toBe(true)
        expect(Number.isFinite(result.otherBusinessTotal)).toBe(true)
        expect(Number.isFinite(result.deductionTotal)).toBe(true)
        expect(Number.isFinite(result.deductionRatio)).toBe(true)
        expect(Number.isFinite(result.revenueAfterDeduction)).toBe(true)
      }
    })
  })

  // ── useS20FormulaEngine composable ────────────────────────

  describe('useS20FormulaEngine composable', () => {
    it('无输入时返回默认值（unable=true）', () => {
      const { result } = useS20FormulaEngine()
      expect(result.value.unable).toBe(true)
      expect(result.value.revenue).toBe(0)
      expect(result.value.deductionRatio).toBe(0)
    })

    it('reactive 输入变化时自动重算', () => {
      const input = ref<RevenueDeductionInput>(makeInput())
      const { result } = useS20FormulaEngine(input)

      expect(result.value.revenue).toBe(1_710_000)

      // 修改输入
      input.value = makeInput({
        mainBusiness: [2_000_000],
        otherBusiness: [500_000],
      })

      expect(result.value.revenue).toBe(2_500_000)
      expect(result.value.mainBusinessTotal).toBe(2_000_000)
      expect(result.value.otherBusinessTotal).toBe(500_000)
    })

    it('导出的纯函数可独立使用', () => {
      const { calcRevenueDeduction: calc, parseNum: pn } = useS20FormulaEngine()
      expect(typeof calc).toBe('function')
      expect(typeof pn).toBe('function')
      expect(pn('123')).toBe(123)
    })
  })
})
