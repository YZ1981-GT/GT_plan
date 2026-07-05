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

describe('F5 集成 — 数量核对（销售vs结转 + 理论结转）', () => {
  it('数量差异/可供销售/理论结转/高亮等级', () => {
    const allResponses = mkResponses({
      'F5-6-quantity-recon-rows': JSON.stringify([
        { id: 'r1', product: 'A', spec: '', unit: '件', salesQty: 100, costQty: 88, varianceReason: '', openingInventory: 20, currentProduction: 100, currentPurchase: 0, closingInventory: 30 },
      ]),
    })
    const recon = useF5QuantityRecon({ allResponses, isReadonly: ref(false) })
    const row = recon.rows.value[0]
    expect(row.qtyVariance).toBe(12) // 100 - 88
    expect(row.availableForSale).toBe(120) // 20 + 100 + 0
    expect(row.theoreticalCostQty).toBe(90) // 120 - 30
    expect(row.theoreticalVariance).toBe(2) // 90 - 88
    // 差异率 12/100 = 12% > 10% → red
    expect(recon.highlightLevel(row)).toBe('red')
    expect(recon.summary.value.redCount).toBe(1)
  })

  it('OCR识别数量 merge 进销售数量', () => {
    const allResponses = mkResponses({
      'F5-6-quantity-recon-rows': JSON.stringify([
        { id: 'r1', product: 'A', spec: '', unit: '件', salesQty: 0, costQty: 0, varianceReason: '', openingInventory: 0, currentProduction: 0, currentPurchase: 0, closingInventory: 0 },
      ]),
    })
    const recon = useF5QuantityRecon({ allResponses, isReadonly: ref(false) })
    recon.mergeOcrQuantity('r1', 555)
    expect(recon.rows.value[0].salesQty).toBe(555)
  })
})

describe('F5 集成 — 月度明细 2区段合计（上半年+下半年=全年）', () => {
  it('全年合计 = 上半年合计 + 下半年合计', () => {
    const months = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120]
    const allResponses = mkResponses({
      'F5-2-monthly-rows': JSON.stringify([{ id: 'm1', product: 'A', months, priorYearTotal: 600 }]),
    })
    const detail = useF5MonthlyDetail({ allResponses, isReadonly: ref(false) })
    const row = detail.rows.value[0]
    expect(row.halfYear1Total).toBe(210) // 10..60
    expect(row.halfYear2Total).toBe(570) // 70..120
    expect(row.yearTotal).toBe(780)
    expect(row.halfYear1Total + row.halfYear2Total).toBe(row.yearTotal)
    // 变动率 = (780-600)/600 = 30% > 20% → highlighted
    expect(detail.isRowHighlighted(row)).toBe(true)
  })
})

describe('F5 集成 — 毛利率计算 + 变动高亮', () => {
  it('毛利率与毛利率变动>5pp高亮', () => {
    const allResponses = mkResponses({
      'F5-5-comparison-rows': JSON.stringify([
        { id: 'c1', product: 'A', currentRevenue: 1000, currentCost: 700, priorRevenue: 1000, priorCost: 850, changeReason: '', auditEvaluation: '', remark: '' },
      ]),
    })
    const cmp = useF5Comparison({ allResponses, isReadonly: ref(false) })
    const row = cmp.rows.value[0]
    expect(row.currentGrossMargin).toBeCloseTo(30, 5) // (1000-700)/1000*100
    expect(row.priorGrossMargin).toBeCloseTo(15, 5) // (1000-850)/1000*100
    expect(row.marginChange).toBeCloseTo(15, 5) // 30 - 15 = 15pp > 5
    expect(cmp.isMarginChangeHigh(row)).toBe(true)
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
