/**
 * Task 11 — P9: fillActualFromSample 属性测试
 *
 * 验证：
 * 1. 匹配行正确填入实盘数 + 差异计算
 * 2. 未匹配项正确计数
 * 3. 空 F2-25 返回 {0,0}
 * 4. 只读模式不操作
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useF2StocktakeRows } from '../useF2StocktakeSheet'
import type { ChecklistResponse } from '../useF2StocktakeFormData'

// 模拟 window.dispatchEvent（persist 会调用）
beforeEach(() => {
  vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true)
})

function createAllResponses(data: Record<string, string | null>): Map<string, ChecklistResponse> {
  const map = new Map<string, ChecklistResponse>()
  for (const [k, v] of Object.entries(data)) {
    map.set(k, { item_id: k, conclusion: null, remark: v ?? '' })
  }
  return map
}

interface RecRow {
  id: string
  itemName: string
  bookQty: number
  bookAmount: number
  erpQty: number
  erpAmount: number
  remark: string
  actualQty?: number
  variance?: number
}

function emptyRow(name: string, bookQty = 100): RecRow {
  return {
    id: `r-${Math.random().toString(36).slice(2, 6)}`,
    itemName: name,
    bookQty,
    bookAmount: 0,
    erpQty: 0,
    erpAmount: 0,
    remark: '',
  }
}

describe('fillActualFromSample — P9', () => {
  it('匹配行正确填入实盘数并计算差异', () => {
    const reconcileRows = [
      emptyRow('钢板', 100),
      emptyRow('螺栓', 200),
    ]
    const sampleRows = [
      { id: 's1', itemName: '钢板', sampleQty: 95 },
      { id: 's2', itemName: '螺栓', sampleQty: 200 },
    ]
    const allResp = createAllResponses({
      'F2-24-rows': JSON.stringify(reconcileRows),
      'F2-24-note': '',
      'F2-25-rows': JSON.stringify(sampleRows),
    })
    const allResponsesRef = ref(allResp)

    const sheet = useF2StocktakeRows<RecRow>({
      rowsKey: 'F2-24-rows',
      noteKey: 'F2-24-note',
      allResponses: allResponsesRef,
      isReadonly: ref(false),
      emptyRow: () => emptyRow(''),
    })

    const result = sheet.fillActualFromSample('F2-25-rows')

    expect(result.matched).toBe(2)
    expect(result.unmatched).toBe(0)
    // 钢板: actualQty=95, variance = 95 - bookQty(100) = -5
    const steelRow = sheet.rows.value.find((r) => r.itemName === '钢板')
    expect(steelRow?.actualQty).toBe(95)
    expect(steelRow?.variance).toBe(-5)
    // 螺栓: actualQty=200, variance = 200 - bookQty(200) = 0
    const boltRow = sheet.rows.value.find((r) => r.itemName === '螺栓')
    expect(boltRow?.actualQty).toBe(200)
    expect(boltRow?.variance).toBe(0)
  })

  it('未匹配项计数正确', () => {
    const reconcileRows = [emptyRow('钢板', 100)]
    const sampleRows = [
      { id: 's1', itemName: '铜管', sampleQty: 50 },
      { id: 's2', itemName: '铝材', sampleQty: 30 },
    ]
    const allResp = createAllResponses({
      'F2-24-rows': JSON.stringify(reconcileRows),
      'F2-24-note': '',
      'F2-25-rows': JSON.stringify(sampleRows),
    })
    const allResponsesRef = ref(allResp)

    const sheet = useF2StocktakeRows<RecRow>({
      rowsKey: 'F2-24-rows',
      noteKey: 'F2-24-note',
      allResponses: allResponsesRef,
      isReadonly: ref(false),
      emptyRow: () => emptyRow(''),
    })

    const result = sheet.fillActualFromSample('F2-25-rows')
    expect(result.matched).toBe(0)
    expect(result.unmatched).toBe(2)
  })

  it('空 F2-25 返回 matched=0, unmatched=0', () => {
    const reconcileRows = [emptyRow('钢板', 100)]
    const allResp = createAllResponses({
      'F2-24-rows': JSON.stringify(reconcileRows),
      'F2-24-note': '',
    })
    const allResponsesRef = ref(allResp)

    const sheet = useF2StocktakeRows<RecRow>({
      rowsKey: 'F2-24-rows',
      noteKey: 'F2-24-note',
      allResponses: allResponsesRef,
      isReadonly: ref(false),
      emptyRow: () => emptyRow(''),
    })

    const result = sheet.fillActualFromSample('F2-25-rows')
    expect(result.matched).toBe(0)
    expect(result.unmatched).toBe(0)
  })

  it('只读模式不操作', () => {
    const reconcileRows = [emptyRow('钢板', 100)]
    const sampleRows = [{ id: 's1', itemName: '钢板', sampleQty: 88 }]
    const allResp = createAllResponses({
      'F2-24-rows': JSON.stringify(reconcileRows),
      'F2-24-note': '',
      'F2-25-rows': JSON.stringify(sampleRows),
    })
    const allResponsesRef = ref(allResp)

    const sheet = useF2StocktakeRows<RecRow>({
      rowsKey: 'F2-24-rows',
      noteKey: 'F2-24-note',
      allResponses: allResponsesRef,
      isReadonly: ref(true),
      emptyRow: () => emptyRow(''),
    })

    const result = sheet.fillActualFromSample('F2-25-rows')
    expect(result.matched).toBe(0)
    expect(result.unmatched).toBe(0)
    // 行未被修改
    const steelRow = sheet.rows.value.find((r) => r.itemName === '钢板')
    expect(steelRow?.actualQty).toBeUndefined()
  })

  it('名称规范化匹配（忽略空格和大小写）', () => {
    const reconcileRows = [emptyRow('钢  板', 100)]
    const sampleRows = [{ id: 's1', itemName: '钢板', sampleQty: 90 }]
    const allResp = createAllResponses({
      'F2-24-rows': JSON.stringify(reconcileRows),
      'F2-24-note': '',
      'F2-25-rows': JSON.stringify(sampleRows),
    })
    const allResponsesRef = ref(allResp)

    const sheet = useF2StocktakeRows<RecRow>({
      rowsKey: 'F2-24-rows',
      noteKey: 'F2-24-note',
      allResponses: allResponsesRef,
      isReadonly: ref(false),
      emptyRow: () => emptyRow(''),
    })

    const result = sheet.fillActualFromSample('F2-25-rows')
    expect(result.matched).toBe(1)
    const row = sheet.rows.value[0]
    expect(row.actualQty).toBe(90)
  })
})
