/**
 * F5 营业成本 — 集成测试
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Task 10.1
 * 覆盖：sheetName分发 / 损益类审定链 / 成本倒轧全链+校验 / TB取数 / 数量核对 /
 *       月度2区段合计 / 毛利率+高亮 / EventBus(substantive:adjudicated)传递+F5-7消费
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import type { ChecklistResponse } from '../useF1FormData'
import { useF5Adjudication } from '../useF5Adjudication'
import { useF5CostRollforward } from '../useF5CostRollforward'
import { useF5QuantityRecon } from '../useF5QuantityRecon'
import { useF5MonthlyDetail } from '../useF5MonthlyDetail'
import { useF5Comparison } from '../useF5Comparison'
import {
  calcAdjustedAmount,
  calcCostRollforward,
  calcTotalProductionCost,
  calcFinishedGoodsCost,
  calcCOGS,
} from '../useF5CosOfFormulaEngine'

function mkResponses(seed?: Record<string, string>) {
  const map = new Map<string, ChecklistResponse>()
  if (seed) for (const [k, v] of Object.entries(seed)) map.set(k, { item_id: k, conclusion: null, remark: v })
  return ref(map)
}

describe('F5 集成 — sheetName 分发正则', () => {
  it('9个sheet编码均能被正则提取', () => {
    const codes = ['F5A', 'F5-1', 'F5-2', 'F5-3', 'F5-4', 'F5-5', 'F5-6', 'F5-7', 'F5-8']
    for (const code of codes) {
      const name = `${code} 营业成本`
      const m = name.match(/(F5A|F5-\d+)/)
      expect(m?.[1]).toBe(code)
    }
  })
})

describe('F5 集成 — 损益类审定公式链（本期/上期各自计算）', () => {
  it('审定=未审+AJE+RJE，总计=主营+其他，差异=审定-试算', () => {
    const allResponses = mkResponses({
      'F5-1-adj-main-rows': JSON.stringify([
        { rowKey: 'p1', label: 'A', isFixed: false, currentUnadjusted: 8000, currentAje: 200, currentRje: -100, priorUnadjusted: 7000, priorAje: 0, priorRje: 0, indexRef: '' },
      ]),
      'F5-1-adj-other-rows': JSON.stringify([
        { rowKey: 'o1', label: '材料', isFixed: false, currentUnadjusted: 1000, currentAje: 0, currentRje: 0, priorUnadjusted: 900, priorAje: 0, priorRje: 0, indexRef: '' },
      ]),
      'F5-1-adj-tb-6401': '9050',
    })
    const adj = useF5Adjudication({ wpId: ref('w'), projectId: ref('p'), allResponses, isReadonly: ref(false) })
    expect(adj.mainBusinessRows.value[0].currentAdjusted).toBe(8100)
    expect(adj.mainBusinessRows.value[0].priorAdjusted).toBe(7000)
    expect(adj.grandTotal.value.currentAdjusted).toBe(9100) // 8100 + 1000
    expect(adj.variance.value).toBe(50) // 9100 - 9050
  })
})

describe('F5 集成 — 成本倒轧全链路（4区公式 → 校验区差异）', () => {
  it('材料→成本构成→结转→营业成本 全链勾稽 + 校验区差异', () => {
    // 手工验证公式链
    const materialInput = calcCostRollforward(1000, 5000, 800, 200) // 5000
    expect(materialInput).toBe(5000)
    const totalCost = calcTotalProductionCost(materialInput, 2000, 1000) // 8000
    expect(totalCost).toBe(8000)
    const finished = calcFinishedGoodsCost(500, totalCost, 300) // 8200
    expect(finished).toBe(8200)
    const cogs = calcCOGS(400, finished, 600, 100) // 7900
    expect(cogs).toBe(7900)

    const allResponses = mkResponses({
      'F5-7-cost-rollforward': JSON.stringify({
        openingMaterial: 1000, purchase: 5000, closingMaterial: 800, otherIssue1: 200,
        directLabor: 2000, overhead: 1000,
        openingWIP: 500, closingWIP: 300,
        openingFG: 400, closingFG: 600, otherIssue2: 100,
      }),
    })
    const roll = useF5CostRollforward({
      allResponses,
      isReadonly: ref(false),
      materiality: ref(1000),
      adjudicatedCOGS: ref(7900),
    })
    expect(roll.data.value.materialInput).toBe(5000)
    expect(roll.data.value.totalProductionCost).toBe(8000)
    expect(roll.data.value.finishedGoodsCost).toBe(8200)
    expect(roll.data.value.cogs).toBe(7900)
    // 校验区：审定7900 - 倒轧7900 = 0 差异，不超重要性
    expect(roll.data.value.rollforwardVariance).toBe(0)
    expect(roll.varianceExceedsMateriality.value).toBe(false)
  })

  it('TB自动取数写入 1401/1404/1405 期初期末', () => {
    const allResponses = mkResponses()
    const roll = useF5CostRollforward({ allResponses, isReadonly: ref(false) })
    roll.setTbValues({ openingMaterial: 1000, closingMaterial: 800, openingWIP: 500, closingWIP: 300, openingFG: 400, closingFG: 600 })
    expect(roll.data.value.openingMaterial).toBe(1000)
    expect(roll.data.value.closingFG).toBe(600)
    expect(roll.isTbField('openingMaterial')).toBe(true)
    expect(roll.isEditable('purchase')).toBe(true)
    expect(roll.isEditable('openingMaterial')).toBe(false)
  })

  it('差异超重要性水平触发红色标记', () => {
    const allResponses = mkResponses({
      'F5-7-cost-rollforward': JSON.stringify({ openingMaterial: 0, purchase: 5000, closingMaterial: 0, otherIssue1: 0, directLabor: 0, overhead: 0, openingWIP: 0, closingWIP: 0, openingFG: 0, closingFG: 0, otherIssue2: 0 }),
    })
    const roll = useF5CostRollforward({ allResponses, isReadonly: ref(false), materiality: ref(100), adjudicatedCOGS: ref(9000) })
    // cogs = 5000; 审定9000 - 5000 = 4000 差异 > 100 重要性
    expect(roll.data.value.cogs).toBe(5000)
    expect(roll.data.value.rollforwardVariance).toBe(4000)
    expect(roll.varianceExceedsMateriality.value).toBe(true)
  })
})

describe('F5 集成 — 数量核对（分厂→产品×销售/结转/差异）', () => {
  it('差异=销售−结转；分厂与总计纵向汇总', () => {
    const sales = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10] // 120
    const cost = [8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8] // 96
    const allResponses = mkResponses({
      'F5-6-quantity-recon-plants': JSON.stringify([{
        id: 'p1', plantId: 'pl1', plant: '分厂1', product: 'A',
        sm1: 10, sm2: 10, sm3: 10, sm4: 10, sm5: 10, sm6: 10,
        sm7: 10, sm8: 10, sm9: 10, sm10: 10, sm11: 10, sm12: 10,
        cm1: 8, cm2: 8, cm3: 8, cm4: 8, cm5: 8, cm6: 8,
        cm7: 8, cm8: 8, cm9: 8, cm10: 8, cm11: 8, cm12: 8,
      }]),
    })
    const recon = useF5QuantityRecon({ allResponses, isReadonly: ref(false) })
    const prod = recon.plants.value[0].products[0]
    expect(prod.sales.total).toBe(120)
    expect(prod.cost.total).toBe(96)
    expect(prod.diff.total).toBe(24)
    expect(prod.diff.months[0]).toBe(2)
    expect(recon.grandTotal.value.diff.total).toBe(24)
    expect(recon.isDiffHighlighted(24)).toBe(true)
    void sales
    void cost
  })

  it('legacy 年累计 salesQty/costQty 迁移至12月', () => {
    const allResponses = mkResponses({
      'F5-6-quantity-recon-rows': JSON.stringify([
        { id: 'r1', product: 'A', salesQty: 100, costQty: 88 },
      ]),
    })
    const recon = useF5QuantityRecon({ allResponses, isReadonly: ref(false) })
    const prod = recon.plants.value[0].products[0]
    expect(prod.sales.months[11]).toBe(100)
    expect(prod.cost.months[11]).toBe(88)
    expect(prod.diff.total).toBe(12)
  })
})

describe('F5 集成 — 月度明细（源表：未审=Σ月、审定=未审+调整、变动≥30%高亮）', () => {
  it('本期未审=12月合计；审定=未审+AJE+RJE；变动比例≥30%高亮', () => {
    const months = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]
    const allResponses = mkResponses({
      'F5-2-monthly-rows': JSON.stringify([{
        id: 'm1', product: 'A', months,
        currentAje: 20, currentRje: 0,
        priorUnaudited: 600, priorAje: 0, priorRje: 0,
      }]),
    })
    const detail = useF5MonthlyDetail({ allResponses, isReadonly: ref(false) })
    const row = detail.rows.value[0]
    expect(row.currentUnaudited).toBe(780)
    expect(row.currentAudited).toBe(800)
    expect(row.priorAudited).toBe(600)
    // 未审变动 (780-600)/600 = 30%
    expect(row.unauditedChangeRate).toBeCloseTo(30, 5)
    expect(detail.isRowHighlighted(row)).toBe(true)
    expect(detail.totalRow.value.currentUnaudited).toBe(780)
    expect(detail.ratioRow.value.months[0]).toBeCloseTo((10 / 780) * 100, 5)
  })
})

describe('F5 集成 — 比较分析（数量×单价→总成本，变动≥30%高亮）', () => {
  it('总成本=数量×单价；变动率；≥30%高亮', () => {
    const allResponses = mkResponses({
      'F5-5-comparison-rows': JSON.stringify([{
        id: 'c1', product: 'A',
        currentQty: 100, currentUnitCost: 13,
        priorQty: 100, priorUnitCost: 10,
        changeReason: '', indexRef: '',
      }]),
    })
    const cmp = useF5Comparison({ allResponses, isReadonly: ref(false) })
    const row = cmp.rows.value[0]
    expect(row.currentTotalCost).toBe(1300)
    expect(row.priorTotalCost).toBe(1000)
    expect(row.totalCostChange).toBe(300)
    expect(row.totalCostChangeRate).toBeCloseTo(30, 5)
    expect(cmp.isRowHighlighted(row)).toBe(true)
    expect(cmp.totalRow.value.currentTotalCost).toBe(1300)
  })
})

describe('F5 集成 — EventBus substantive:adjudicated(6401) 传递', () => {
  it('F5-1 publishAdjudicated 触发 6401 事件，F5-7 校验区可消费', () => {
    const allResponses = mkResponses({
      'F5-1-adj-main-rows': JSON.stringify([
        { rowKey: 'p1', label: 'A', isFixed: false, currentUnadjusted: 5000, currentAje: 0, currentRje: 0, priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '' },
      ]),
    })
    const adj = useF5Adjudication({ wpId: ref('w'), projectId: ref('p'), allResponses, isReadonly: ref(false) })

    let received: any = null
    const handler = (e: Event) => { received = (e as CustomEvent).detail }
    window.addEventListener('substantive:adjudicated', handler)
    adj.publishAdjudicated()
    window.removeEventListener('substantive:adjudicated', handler)

    expect(received).toBeTruthy()
    expect(received.accountCode).toBe('6401')
    expect(received.auditedAmount).toBe(5000)

    // F5-7 消费该审定营业成本
    const roll = useF5CostRollforward({
      allResponses,
      isReadonly: ref(false),
      adjudicatedCOGS: ref(received.auditedAmount),
    })
    expect(roll.data.value.adjudicatedCOGS).toBe(5000)
  })
})
