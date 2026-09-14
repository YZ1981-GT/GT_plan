/**
 * useF5CostRollforward — F5-7 主营业务成本倒轧表 单元测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  useF5CostRollforward,
  F57_ROW_DEFS,
} from '../useF5CostRollforward'
import {
  calcF57DirectMaterial,
  calcF57ProductionCost,
  calcF57FinishedGoodsCost,
  calcF57MainBusinessCOGS,
} from '../useF5CosOfFormulaEngine'
import type { ChecklistResponse } from '../useF1FormData'

function mkResponses(seed?: Record<string, string>) {
  const map = ref(new Map<string, ChecklistResponse>())
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      map.value.set(k, { item_id: k, conclusion: null, remark: v })
    }
  }
  return map
}

describe('F5-7 公式引擎（源表 ⑹⑽⒀⒇）', () => {
  it('四段倒轧链', () => {
    const dm = calcF57DirectMaterial(1000, 5000, 100, 800, 200) // 5100
    expect(dm).toBe(5100)
    const pc = calcF57ProductionCost(dm, 2000, 1000, 50) // 8150
    expect(pc).toBe(8150)
    const fg = calcF57FinishedGoodsCost(pc, 500, 300) // 8350
    expect(fg).toBe(8350)
    const cogs = calcF57MainBusinessCOGS(fg, 400, 0, 600, 0, 0, 100) // 8050
    expect(cogs).toBe(8050)
  })
})

describe('useF5CostRollforward', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('源表 21 行；公式行只读轧差；悬停公式字段齐全', () => {
    const allResponses = mkResponses()
    const roll = useF5CostRollforward({ allResponses, isReadonly: ref(false) })
    expect(roll.rows.value).toHaveLength(F57_ROW_DEFS.length)
    expect(F57_ROW_DEFS.filter((d) => d.rowType === 'formula')).toHaveLength(4)
    for (const r of roll.rows.value) {
      expect(r.formulaExpr.length).toBeGreaterThan(0)
    }
    const dm = roll.rows.value.find((r) => r.rowKey === 'directMaterialCost')!
    expect(dm.rowType).toBe('formula')
    expect(dm.formulaLegend).toContain('⑹')
  })

  it('旧扁平存储迁移；兼容 data API', () => {
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
      adjudicatedCOGS: ref(7900),
    })
    // 无「其他增加/工模具」时与旧四区公式一致
    expect(roll.data.value.materialInput).toBe(5000)
    expect(roll.data.value.totalProductionCost).toBe(8000)
    expect(roll.data.value.finishedGoodsCost).toBe(8200)
    expect(roll.data.value.cogs).toBe(7900)
    expect(roll.data.value.purchase).toBe(5000)
  })

  it('未审+调整→审定；公式行审定=未审轧差+调整轧差', () => {
    const allResponses = mkResponses()
    const roll = useF5CostRollforward({ allResponses, isReadonly: ref(false) })
    roll.updateAmount('materialPurchaseNet', 'unadjusted', 1000)
    roll.updateAmount('materialPurchaseNet', 'aje', 100)
    const row = roll.rows.value.find((r) => r.rowKey === 'materialPurchaseNet')!
    expect(row.audited).toBe(1100)

    roll.updateAmount('openingMaterial', 'unadjusted', 0) // via setTb
    roll.setTbValues({ openingMaterial: 0, closingMaterial: 0, openingWIP: 0, closingWIP: 0, openingFG: 0, closingFG: 0 })
    const dm = roll.rows.value.find((r) => r.rowKey === 'directMaterialCost')!
    expect(dm.unadjusted).toBe(1000)
    expect(dm.aje).toBe(100)
    expect(dm.audited).toBe(1100)
  })

  it('与 F5-1 校验差异', () => {
    const allResponses = mkResponses({
      'F5-7-cost-rollforward': JSON.stringify({
        purchase: 5000,
      }),
    })
    const roll = useF5CostRollforward({
      allResponses,
      isReadonly: ref(false),
      materiality: ref(100),
      adjudicatedCOGS: ref(9000),
    })
    expect(roll.data.value.cogs).toBe(5000)
    expect(Math.abs(roll.data.value.rollforwardVariance)).toBe(4000)
    expect(roll.varianceExceedsMateriality.value).toBe(true)
  })
})
