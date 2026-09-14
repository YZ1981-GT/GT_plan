/**
 * Unit Tests — S21 数据资产开发支出资本化公式引擎
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/
 * Task: 3.3
 *
 * 已知值验证，互补 PBT 测试。
 * 覆盖 Property P6（数据资产资本化归集正确性）+ Req 5.3（研发阶段合计）。
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  parseNum,
  calcCapitalization,
  calcResearchDevTotals,
  useS21FormulaEngine,
  type CapitalizationInput,
  type ResearchDevInput,
} from '../useS21FormulaEngine'

// ─── helper: 默认 CapitalizationInput ────────────────────────

function makeCapInput(overrides: Partial<CapitalizationInput> = {}): CapitalizationInput {
  return {
    monthly: {
      '采购成本': [100, 200, 150, 180, 220, 300, 250, 200, 180, 160, 140, 120],
      '人工成本': [50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160],
      '脱敏清洗标注整合分析支出': [30, 40, 50, 60, 70, 80, 90, 100, 80, 60, 40, 20],
    },
    ...overrides,
  }
}

function makeRdInput(overrides: Partial<ResearchDevInput> = {}): ResearchDevInput {
  return {
    researchItems: [100_000, 200_000, 50_000],
    developmentItems: [500_000, 300_000, 200_000, 150_000],
    ...overrides,
  }
}

describe('useS21FormulaEngine', () => {
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

  // ── calcCapitalization (Property P6) ──────────────────────

  describe('calcCapitalization', () => {
    it('标准场景：各类目合计、总额、占比正确', () => {
      const input = makeCapInput()
      const result = calcCapitalization(input)

      // 采购成本合计 = 100+200+150+180+220+300+250+200+180+160+140+120 = 2200
      expect(result.categoryTotals['采购成本']).toBe(2200)
      // 人工成本合计 = 50+60+70+80+90+100+110+120+130+140+150+160 = 1260
      expect(result.categoryTotals['人工成本']).toBe(1260)
      // 脱敏合计 = 30+40+50+60+70+80+90+100+80+60+40+20 = 720
      expect(result.categoryTotals['脱敏清洗标注整合分析支出']).toBe(720)

      // 总额 = 2200 + 1260 + 720 = 4180
      expect(result.total).toBe(4180)
      expect(result.unable).toBe(false)

      // 各类目占比
      expect(result.categoryRatios['采购成本']).toBeCloseTo(2200 / 4180, 10)
      expect(result.categoryRatios['人工成本']).toBeCloseTo(1260 / 4180, 10)
      expect(result.categoryRatios['脱敏清洗标注整合分析支出']).toBeCloseTo(720 / 4180, 10)
    })

    it('标准场景：月合计与月比例正确', () => {
      const input = makeCapInput()
      const result = calcCapitalization(input)

      // 1月合计 = 100 + 50 + 30 = 180
      expect(result.monthlyTotals[0]).toBe(180)
      // 2月合计 = 200 + 60 + 40 = 300
      expect(result.monthlyTotals[1]).toBe(300)
      // 6月合计 = 300 + 100 + 80 = 480
      expect(result.monthlyTotals[5]).toBe(480)

      // monthlyTotals 恰好 12 元素
      expect(result.monthlyTotals).toHaveLength(12)
      expect(result.monthlyRatios).toHaveLength(12)

      // 各月比例
      const total = result.total
      for (let m = 0; m < 12; m++) {
        expect(result.monthlyRatios[m]).toBeCloseTo(result.monthlyTotals[m] / total, 10)
      }
    })

    it('占比之和在浮点误差内为1（total≠0）', () => {
      const input = makeCapInput()
      const result = calcCapitalization(input)

      const ratioSum = Object.values(result.categoryRatios).reduce((s, v) => s + v, 0)
      expect(ratioSum).toBeCloseTo(1, 10)

      const monthlyRatioSum = result.monthlyRatios.reduce((s, v) => s + v, 0)
      expect(monthlyRatioSum).toBeCloseTo(1, 10)
    })

    it('total=0 时 unable=true，所有 ratios 为 0', () => {
      const input: CapitalizationInput = { monthly: {} }
      const result = calcCapitalization(input)

      expect(result.total).toBe(0)
      expect(result.unable).toBe(true)
      expect(Object.keys(result.categoryTotals)).toHaveLength(0)
      expect(Object.keys(result.categoryRatios)).toHaveLength(0)
      expect(result.monthlyTotals).toHaveLength(12)
      expect(result.monthlyRatios).toHaveLength(12)
      for (let m = 0; m < 12; m++) {
        expect(result.monthlyTotals[m]).toBe(0)
        expect(result.monthlyRatios[m]).toBe(0)
      }
    })

    it('所有类目全为0时 unable=true', () => {
      const input: CapitalizationInput = {
        monthly: {
          '采购成本': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
          '人工成本': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        },
      }
      const result = calcCapitalization(input)

      expect(result.total).toBe(0)
      expect(result.unable).toBe(true)
      expect(result.categoryRatios['采购成本']).toBe(0)
      expect(result.categoryRatios['人工成本']).toBe(0)
    })

    it('月数组不足12元素→补0', () => {
      const input: CapitalizationInput = {
        monthly: {
          '短数组': [100, 200, 300],  // 只有 3 个月
        },
      }
      const result = calcCapitalization(input)

      // 合计 = 100 + 200 + 300 + 0*9 = 600
      expect(result.categoryTotals['短数组']).toBe(600)
      expect(result.total).toBe(600)
      // monthlyTotals[0] = 100, [1] = 200, [2] = 300, [3..11] = 0
      expect(result.monthlyTotals[0]).toBe(100)
      expect(result.monthlyTotals[2]).toBe(300)
      expect(result.monthlyTotals[3]).toBe(0)
      expect(result.monthlyTotals[11]).toBe(0)
    })

    it('月数组超过12元素→截断', () => {
      const input: CapitalizationInput = {
        monthly: {
          '长数组': [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 999, 888],
        },
      }
      const result = calcCapitalization(input)

      // 合计 = 10+20+30+40+50+60+70+80+90+100+110+120 = 780（不含 999, 888）
      expect(result.categoryTotals['长数组']).toBe(780)
      expect(result.total).toBe(780)
      expect(result.monthlyTotals[11]).toBe(120)
    })

    it('单一类目时占比=1', () => {
      const input: CapitalizationInput = {
        monthly: {
          '唯一类目': [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
        },
      }
      const result = calcCapitalization(input)

      expect(result.categoryTotals['唯一类目']).toBe(1200)
      expect(result.total).toBe(1200)
      expect(result.categoryRatios['唯一类目']).toBe(1)
      // 各月比例均为 100/1200
      for (let m = 0; m < 12; m++) {
        expect(result.monthlyRatios[m]).toBeCloseTo(100 / 1200, 10)
      }
    })

    it('含NaN/Infinity值时降级为0', () => {
      const input: CapitalizationInput = {
        monthly: {
          '异常值': [100, NaN, Infinity, -Infinity, 200, 0, 0, 0, 0, 0, 0, 300],
        },
      }
      const result = calcCapitalization(input)

      // NaN/Infinity 被 parseNum 转为 0
      expect(result.categoryTotals['异常值']).toBe(600) // 100+200+300
      expect(result.total).toBe(600)
      expect(result.monthlyTotals[0]).toBe(100)
      expect(result.monthlyTotals[1]).toBe(0) // NaN → 0
      expect(result.monthlyTotals[2]).toBe(0) // Infinity → 0
      expect(result.monthlyTotals[11]).toBe(300)
    })

    it('不返回 NaN 或 Infinity', () => {
      const inputs: CapitalizationInput[] = [
        makeCapInput(),
        { monthly: {} },
        { monthly: { 'x': [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] } },
        { monthly: { 'a': [NaN as number, Infinity as number] } },
      ]
      for (const input of inputs) {
        const result = calcCapitalization(input)
        expect(Number.isFinite(result.total)).toBe(true)
        for (const v of Object.values(result.categoryTotals)) {
          expect(Number.isFinite(v)).toBe(true)
        }
        for (const v of Object.values(result.categoryRatios)) {
          expect(Number.isFinite(v)).toBe(true)
        }
        for (let m = 0; m < 12; m++) {
          expect(Number.isFinite(result.monthlyTotals[m])).toBe(true)
          expect(Number.isFinite(result.monthlyRatios[m])).toBe(true)
        }
      }
    })

    it('大额数值不溢出', () => {
      const input: CapitalizationInput = {
        monthly: {
          '大额': [9_999_999_999, 8_888_888_888, 7_777_777_777, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        },
      }
      const result = calcCapitalization(input)

      expect(result.categoryTotals['大额']).toBe(9_999_999_999 + 8_888_888_888 + 7_777_777_777)
      expect(Number.isFinite(result.total)).toBe(true)
      expect(result.unable).toBe(false)
    })
  })

  // ── calcResearchDevTotals (Req 5.3) ───────────────────────

  describe('calcResearchDevTotals', () => {
    it('标准场景计算正确', () => {
      const input = makeRdInput()
      const result = calcResearchDevTotals(input)

      // 研究阶段 = 100K + 200K + 50K = 350,000
      expect(result.researchTotal).toBe(350_000)
      // 开发阶段 = 500K + 300K + 200K + 150K = 1,150,000
      expect(result.developmentTotal).toBe(1_150_000)
    })

    it('空数组→合计=0', () => {
      const input = makeRdInput({
        researchItems: [],
        developmentItems: [],
      })
      const result = calcResearchDevTotals(input)

      expect(result.researchTotal).toBe(0)
      expect(result.developmentTotal).toBe(0)
    })

    it('单元素数组正确', () => {
      const input = makeRdInput({
        researchItems: [500_000],
        developmentItems: [1_000_000],
      })
      const result = calcResearchDevTotals(input)

      expect(result.researchTotal).toBe(500_000)
      expect(result.developmentTotal).toBe(1_000_000)
    })

    it('含非法值时parseNum降级为0', () => {
      const input: ResearchDevInput = {
        researchItems: [100, NaN, Infinity],
        developmentItems: [-Infinity, 200, undefined as unknown as number],
      }
      const result = calcResearchDevTotals(input)

      expect(result.researchTotal).toBe(100)
      expect(result.developmentTotal).toBe(200)
    })

    it('不返回 NaN 或 Infinity', () => {
      const inputs: ResearchDevInput[] = [
        makeRdInput(),
        { researchItems: [], developmentItems: [] },
        { researchItems: [NaN], developmentItems: [Infinity] },
      ]
      for (const input of inputs) {
        const result = calcResearchDevTotals(input)
        expect(Number.isFinite(result.researchTotal)).toBe(true)
        expect(Number.isFinite(result.developmentTotal)).toBe(true)
      }
    })
  })

  // ── useS21FormulaEngine composable ────────────────────────

  describe('useS21FormulaEngine composable', () => {
    it('无输入时返回默认值（unable=true）', () => {
      const { capitalization, researchDev } = useS21FormulaEngine()

      expect(capitalization.value.unable).toBe(true)
      expect(capitalization.value.total).toBe(0)
      expect(capitalization.value.monthlyTotals).toHaveLength(12)
      expect(capitalization.value.monthlyRatios).toHaveLength(12)
      expect(researchDev.value.researchTotal).toBe(0)
      expect(researchDev.value.developmentTotal).toBe(0)
    })

    it('reactive 输入变化时自动重算', () => {
      const capInput = ref<CapitalizationInput>(makeCapInput())
      const rdInput = ref<ResearchDevInput>(makeRdInput())
      const { capitalization, researchDev } = useS21FormulaEngine(capInput, rdInput)

      expect(capitalization.value.total).toBe(4180)
      expect(researchDev.value.researchTotal).toBe(350_000)

      // 修改输入
      capInput.value = {
        monthly: {
          '新类目': [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000],
        },
      }
      rdInput.value = {
        researchItems: [999],
        developmentItems: [888],
      }

      expect(capitalization.value.total).toBe(12000)
      expect(capitalization.value.categoryTotals['新类目']).toBe(12000)
      expect(capitalization.value.categoryRatios['新类目']).toBe(1)
      expect(researchDev.value.researchTotal).toBe(999)
      expect(researchDev.value.developmentTotal).toBe(888)
    })

    it('导出的纯函数可独立使用', () => {
      const { calcCapitalization: calc, calcResearchDevTotals: calcRd, parseNum: pn } = useS21FormulaEngine()

      expect(typeof calc).toBe('function')
      expect(typeof calcRd).toBe('function')
      expect(typeof pn).toBe('function')
      expect(pn('456')).toBe(456)
    })
  })
})
