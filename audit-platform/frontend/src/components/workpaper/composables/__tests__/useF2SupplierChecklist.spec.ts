import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  emptySupplierChecklistRow,
  enrichSupplierChecklistRow,
  migrateSupplierChecklistRows,
  pruneSupplierChecklistRows,
  supplierChecklistSummary,
} from '../useF2SupplierChecklistFormulas'
import { useF2SupplierChecklist } from '../useF2SupplierChecklist'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('F2-69 供应商核查公式', () => {
  it('多余空行裁剪为一行', () => {
    expect(pruneSupplierChecklistRows([
      emptySupplierChecklistRow(),
      emptySupplierChecklistRow(),
    ])).toHaveLength(1)
  })

  it('按五种核查方式计算完成度', () => {
    const row = emptySupplierChecklistRow()
    row.supplierName = '供应商A'
    row.registryChecked = true
    row.confirmationChecked = true
    const enriched = enrichSupplierChecklistRow(row)
    expect(enriched.completedMethodCount).toBe(2)
    expect(enriched.completionPct).toBeCloseTo(0.4)
  })

  it('反向核查与函证金额差异超过1%时预警', () => {
    const row = emptySupplierChecklistRow()
    row.supplierName = '供应商A'
    row.reverseEndingBalance = 100
    row.confirmationEndingBalance = 100
    row.reversePurchaseAmount = 1200
    row.confirmationPurchaseAmount = 1000
    const enriched = enrichSupplierChecklistRow(row)
    expect(enriched.reverseDifference).toBe(200)
    expect(enriched.confirmationDifference).toBe(0)
    expect(enriched.isAmountMismatch).toBe(true)
    expect(enriched.isRisk).toBe(true)
  })

  it('选取原因、核查方式或最终索引缺失时判定待完善', () => {
    const row = emptySupplierChecklistRow()
    row.supplierName = '供应商A'
    expect(enrichSupplierChecklistRow(row).isIncomplete).toBe(true)
    row.selectionReason = '重大供应商'
    row.registryChecked = true
    row.finalIndexRef = 'F2-69-1'
    expect(enrichSupplierChecklistRow(row).isIncomplete).toBe(false)
  })

  it('汇总供应商、已执行方式、待完善及金额差异', () => {
    const complete = emptySupplierChecklistRow()
    complete.supplierName = 'A'
    complete.selectionReason = '重大'
    complete.registryChecked = true
    complete.finalIndexRef = '1'
    const mismatch = emptySupplierChecklistRow()
    mismatch.supplierName = 'B'
    mismatch.reversePurchaseAmount = 200
    mismatch.confirmationPurchaseAmount = 100
    const summary = supplierChecklistSummary([complete, mismatch])
    expect(summary).toMatchObject({
      supplierCount: 2,
      completedMethods: 1,
      incompleteCount: 1,
      mismatchCount: 1,
    })
  })

  it('迁移旧十项进度模型', () => {
    const migrated = migrateSupplierChecklistRows([
      {
        id: 'old',
        supplierName: '供应商A',
        riskCategory: '新增供应商',
        overallEval: '已走访',
        completeDate: '2025-01-10',
        check1: '已完成',
        check3: '已完成',
        check6: '已完成',
        check8: '已完成',
        indexNo: 'F2-69-old',
        followUp: '无异常',
      },
      { id: 'blank', supplierName: '' },
    ])
    expect(migrated).toHaveLength(1)
    expect(migrated[0]).toMatchObject({
      supplierName: '供应商A',
      selectionReason: '新增供应商',
      visitConclusion: '已走访',
      registryChecked: true,
      internetChecked: true,
      confirmationChecked: true,
      siteVisitChecked: true,
      finalIndexRef: 'F2-69-old',
      remark: '无异常',
    })
  })
})

describe('F2-69 composable', () => {
  function setup(initial?: unknown) {
    const map = new Map<string, ChecklistResponse>()
    if (initial !== undefined) {
      map.set('F2-69-rows', {
        item_id: 'F2-69-rows',
        conclusion: null,
        remark: JSON.stringify(initial),
      })
    }
    const allResponses = ref(map)
    const sc = useF2SupplierChecklist({ allResponses, isReadonly: ref(false) })
    return { allResponses, sc }
  }

  it('旧数据迁移后立即回写', () => {
    const { allResponses, sc } = setup([
      { id: '1', supplierName: 'A', riskCategory: '重大', check1: '已完成' },
    ])
    expect(sc.enrichedRows.value[0].registryChecked).toBe(true)
    const saved = JSON.parse(allResponses.value.get('F2-69-rows')!.remark!)
    expect(saved[0].selectionReason).toBe('重大')
  })

  it('新增空行不被自身回显裁剪', () => {
    const { sc } = setup()
    sc.addRow()
    expect(sc.rows.value).toHaveLength(2)
  })

  it('更新核查方式和金额后统计实时联动', () => {
    const { sc } = setup()
    const id = sc.rows.value[0].id
    sc.updateRow(id, {
      supplierName: 'A',
      selectionReason: '新增',
      finalIndexRef: 'F2-69-1',
      reversePurchaseAmount: 120,
      confirmationPurchaseAmount: 100,
    })
    sc.toggleMethod(id, 'registryChecked', true)
    expect(sc.summary.value.completedMethods).toBe(1)
    expect(sc.summary.value.mismatchCount).toBe(1)
  })
})
