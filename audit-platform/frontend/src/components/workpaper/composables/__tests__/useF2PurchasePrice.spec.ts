import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import { useF2PurchasePrice } from '../useF2PurchasePrice'
import {
  emptyPurchaseMaterial,
  type PurchasePriceSheet,
} from '../useF2PurchasePriceFormulas'
import type { ChecklistResponse } from '../useF2SpecialFormData'

function makeResponses(sheet?: PurchasePriceSheet | unknown) {
  const map = new Map<string, ChecklistResponse>()
  if (sheet !== undefined) {
    map.set('F2-61-rows', {
      item_id: 'F2-61-rows',
      conclusion: null,
      remark: JSON.stringify(sheet),
    })
  }
  return ref(map)
}

describe('useF2PurchasePrice（composable 回归）', () => {
  it('迁移旧扁平数组并裁剪预留空行', () => {
    const legacy = [
      { id: 'a', materialName: '钢材', months: Array.from({ length: 12 }, () => ({ amount: 1, qty: 1 })), priorAvgPrice: 0 },
      { id: 'b', materialName: '', months: Array.from({ length: 12 }, () => ({ amount: 0, qty: 0 })), priorAvgPrice: 0 },
    ]
    const pp = useF2PurchasePrice({ allResponses: makeResponses(legacy) })
    expect(pp.sheet.value.materials).toHaveLength(1)
    expect(pp.sheet.value.materials[0].materialName).toBe('钢材')
    expect(pp.filledCount.value).toBe(1)
  })

  it('addMaterial 新增空行不会被 persist/load 回环裁剪（自回声守卫）', async () => {
    vi.useFakeTimers()
    const filled = { ...emptyPurchaseMaterial(), materialName: '铜材' }
    const allResponses = makeResponses({ materials: [filled] })
    const pp = useF2PurchasePrice({ allResponses })

    pp.addMaterial()
    await nextTick()
    // persist 已写回 allResponses，watcher 触发 load；守卫应保留新增空行
    expect(pp.sheet.value.materials).toHaveLength(2)
    vi.runAllTimers()
    await nextTick()
    expect(pp.sheet.value.materials).toHaveLength(2)
    vi.useRealTimers()
  })

  it('updateMonth 后本期合计与平均单价联动', () => {
    const pp = useF2PurchasePrice({ allResponses: makeResponses() })
    const id = pp.sheet.value.materials[0].id
    pp.updateMonth(id, 0, { amount: 1000, qty: 100 })
    pp.updateMonth(id, 1, { amount: 2000, qty: 100 })
    const row = pp.enrichedMaterials.value[0]
    expect(row.currentTotalAmount).toBe(3000)
    expect(row.currentTotalQty).toBe(200)
    expect(row.currentAvgPrice).toBe(15)
  })
})
