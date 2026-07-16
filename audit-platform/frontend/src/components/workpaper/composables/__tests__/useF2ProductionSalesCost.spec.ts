/**
 * F2-19 / F2-20 rebuild unit tests
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useF2ProductionSales } from '../useF2ProductionSales'
import { useF2CostComparison } from '../useF2CostComparison'
import type { ChecklistResponse } from '../useF2FormData'

describe('useF2ProductionSales F2-19', () => {
  it('computes monthly totals, sales/prod ratio and YoY change', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const ps = useF2ProductionSales({ allResponses: map, isReadonly: ref(false) })
    const id = ps.productViews.value[0].rowId
    ps.updateProduct(id, 'name', '产品A')
    for (let i = 0; i < 12; i++) {
      ps.updateProductMonth(id, 'prod', i, 10)
      ps.updateProductMonth(id, 'sales', i, 8)
    }
    ps.updateProduct(id, 'prodPrior', 100)
    ps.updateProduct(id, 'salesPrior', 80)
    const row = ps.productViews.value[0]
    expect(row.prodTotal).toBe(120)
    expect(row.salesTotal).toBe(96)
    expect(row.ratioTotal).toBe(80)
    expect(row.prodChange).toBe(20)
  })

  it('computes material purchase/output and yield ratios via linked product', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const ps = useF2ProductionSales({ allResponses: map, isReadonly: ref(false) })
    const pid = ps.productViews.value[0].rowId
    ps.updateProduct(pid, 'name', '产品A')
    for (let i = 0; i < 12; i++) ps.updateProductMonth(pid, 'prod', i, 10)

    const mid = ps.materialViews.value[0].rowId
    ps.updateMaterial(mid, 'name', '材料X')
    ps.updateMaterial(mid, 'linkedProduct', '产品A')
    for (let i = 0; i < 12; i++) {
      ps.updateMaterialMonth(mid, 'purchase', i, 20)
      ps.updateMaterialMonth(mid, 'consume', i, 10)
    }
    const m = ps.materialViews.value[0]
    expect(m.purchaseOutRatioTotal).toBe(200) // 240/120
    expect(m.yieldRatioTotal).toBe(100) // 120/120
  })

  it('persists version 2 pack', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const ps = useF2ProductionSales({ allResponses: map, isReadonly: ref(false) })
    ps.updateQuestion('q1', '产量季节性波动')
    ps.conclusion.value = 'A、未见异常。'
    const raw = map.value.get('F2-19-pack')?.remark
    expect(raw).toBeTruthy()
    const parsed = JSON.parse(raw!)
    expect(parsed.version).toBe(2)
    expect(parsed.questions.q1).toContain('季节性')
  })
})

describe('useF2CostComparison F2-20', () => {
  it('computes totals and fluctuation ratios; flags anomaly >20%', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const c = useF2CostComparison({ allResponses: map, isReadonly: ref(false) })
    const id = c.enrichedRows.value[0].rowId
    c.updateCell(id, 'productName', '产品A')
    c.updateCell(id, 'currentMaterial', 60)
    c.updateCell(id, 'currentLabor', 20)
    c.updateCell(id, 'currentOverhead', 20)
    c.updateCell(id, 'priorMaterial', 40)
    c.updateCell(id, 'priorLabor', 20)
    c.updateCell(id, 'priorOverhead', 20)
    const row = c.enrichedRows.value[0]
    expect(row.currentTotal).toBe(100)
    expect(row.priorTotal).toBe(80)
    expect(row.totalRate).toBe(25)
    expect(row.isAnomaly).toBe(true)
    expect(c.anomalyCount.value).toBe(1)
  })

  it('persists version 2 pack with note/conclusion', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const c = useF2CostComparison({ allResponses: map, isReadonly: ref(false) })
    c.auditNote.value = '见 F2-64'
    c.conclusion.value = 'A、未见异常。'
    const parsed = JSON.parse(map.value.get('F2-20-pack')!.remark)
    expect(parsed.version).toBe(2)
    expect(parsed.auditNote).toContain('F2-64')
  })
})
