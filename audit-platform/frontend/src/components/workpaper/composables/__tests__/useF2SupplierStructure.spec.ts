import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  defaultSupplierStructureSheet,
  emptySupplierStructureRow,
  enrichSupplierStructureRows,
  migrateSupplierStructureSheet,
  pruneSupplierStructureRows,
  supplierStructureSummary,
  type SupplierStructureRow,
} from '../useF2SupplierStructureFormulas'
import { useF2SupplierStructure } from '../useF2SupplierStructure'
import type { ChecklistResponse } from '../useF2SpecialFormData'

function row(overrides: Partial<SupplierStructureRow>): SupplierStructureRow {
  return { ...emptySupplierStructureRow(), ...overrides }
}

describe('F2-68 重要供应商结构公式', () => {
  it('默认本年、上年各仅预留一行', () => {
    const sheet = defaultSupplierStructureSheet()
    expect(sheet.currentRows).toHaveLength(1)
    expect(sheet.priorRows).toHaveLength(1)
  })

  it('裁剪多余空行但至少保留一行', () => {
    expect(pruneSupplierStructureRows([
      emptySupplierStructureRow(),
      emptySupplierStructureRow(),
    ])).toHaveLength(1)
  })

  it('自动计算占比和排名', () => {
    const enriched = enrichSupplierStructureRows([
      row({ id: 'a', supplierName: 'A', purchaseAmount: 600 }),
      row({ id: 'b', supplierName: 'B', purchaseAmount: 300 }),
      row({ id: 'c', supplierName: 'C', purchaseAmount: 100 }),
    ])
    expect(enriched[0].ratio).toBeCloseTo(0.6)
    expect(enriched[0].rank).toBe(1)
    expect(enriched[2].rank).toBe(3)
  })

  it('数量×单价与采购额偏差超过1%时标记', () => {
    const [matched] = enrichSupplierStructureRows([
      row({ supplierName: 'A', purchaseAmount: 1000, purchaseQuantity: 10, unitPrice: 100 }),
    ])
    expect(matched.impliedAmount).toBe(1000)
    expect(matched.isAmountMismatch).toBe(false)

    const [mismatch] = enrichSupplierStructureRows([
      row({ supplierName: 'A', purchaseAmount: 1200, purchaseQuantity: 10, unitPrice: 100 }),
    ])
    expect(mismatch.isAmountMismatch).toBe(true)
    expect(mismatch.isRisk).toBe(true)
  })

  it('关联方、规模或经营范围不匹配均为风险', () => {
    const enriched = enrichSupplierStructureRows([
      row({ supplierName: 'A', isRelatedParty: '是' }),
      row({ supplierName: 'B', scaleMatches: '否' }),
      row({ supplierName: 'C', scopeMatches: '否' }),
    ])
    expect(enriched.every((item) => item.isRisk)).toBe(true)
  })

  it('汇总前五、前十大集中度', () => {
    const rows = Array.from({ length: 12 }, (_, index) =>
      row({ supplierName: `S${index + 1}`, purchaseAmount: 120 - index * 5 }),
    )
    const summary = supplierStructureSummary(rows)
    const total = rows.reduce((sum, item) => sum + item.purchaseAmount, 0)
    const top5 = rows.slice(0, 5).reduce((sum, item) => sum + item.purchaseAmount, 0)
    expect(summary.total).toBe(total)
    expect(summary.top5Ratio).toBeCloseTo(top5 / total)
    expect(summary.top10Ratio).toBeLessThanOrEqual(1)
  })

  it('旧 T/T-1 行迁为本年、上年双区模型', () => {
    const migrated = migrateSupplierStructureSheet([
      {
        id: 'old',
        supplierName: '供应商A',
        category: '原材料',
        amountT: 800,
        amountT1: 600,
        isRelated: '否',
        concentrationEval: '持续合作',
      },
      { id: 'blank', supplierName: '', amountT: 0, amountT1: 0 },
    ])
    expect(migrated.currentRows).toHaveLength(1)
    expect(migrated.priorRows).toHaveLength(1)
    expect(migrated.currentRows[0]).toMatchObject({
      supplierName: '供应商A',
      purchaseAmount: 800,
      relatedProduct: '原材料',
      otherTerms: '持续合作',
    })
    expect(migrated.priorRows[0].purchaseAmount).toBe(600)
  })
})

describe('F2-68 composable', () => {
  function setup(initial?: unknown) {
    const map = new Map<string, ChecklistResponse>()
    if (initial !== undefined) {
      map.set('F2-68-rows', {
        item_id: 'F2-68-rows',
        conclusion: null,
        remark: JSON.stringify(initial),
      })
    }
    const allResponses = ref(map)
    const ss = useF2SupplierStructure({ allResponses, isReadonly: ref(false) })
    return { allResponses, ss }
  }

  it('旧数据迁移后立即回写', () => {
    const { allResponses, ss } = setup([
      { id: '1', supplierName: 'A', amountT: 100, amountT1: 80 },
    ])
    expect(ss.currentRows.value[0].purchaseAmount).toBe(100)
    const saved = JSON.parse(allResponses.value.get('F2-68-rows')!.remark!)
    expect(saved.currentRows).toHaveLength(1)
    expect(saved.priorRows).toHaveLength(1)
  })

  it('新增空行不被自身回显裁剪', () => {
    const { ss } = setup()
    ss.addRow('current')
    ss.addRow('prior')
    expect(ss.sheet.value.currentRows).toHaveLength(2)
    expect(ss.sheet.value.priorRows).toHaveLength(2)
  })

  it('更新本年数据后统计实时联动', () => {
    const { ss } = setup()
    const id = ss.sheet.value.currentRows[0].id
    ss.updateRow('current', id, {
      supplierName: 'A',
      purchaseAmount: 500,
      scaleMatches: '否',
    })
    expect(ss.currentSummary.value.total).toBe(500)
    expect(ss.currentSummary.value.supplierCount).toBe(1)
    expect(ss.currentSummary.value.riskCount).toBe(1)
  })
})
