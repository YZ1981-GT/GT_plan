/**
 * useG4SppiInventory 单元测试 — 头信息完备性、监盘叙述、日差判断、推送 G4-8
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  buildInventoryNarrative,
  createDefaultHeader,
  headerCompleteness,
  isRollForwardNeeded,
  useG4SppiInventory,
} from '@/composables/useG4SppiInventory'
import type { ChecklistResponse } from '@/composables/useG4SppiFormData'

describe('buildInventoryNarrative', () => {
  it('按纸质底稿句式生成叙述', () => {
    const h = createDefaultHeader()
    h.participantCount = '3'
    h.countDate = '2025-12-31'
    h.location = '公司财务室'
    h.observer = '张三'
    h.counter = '李四'
    h.company = '示例公司'
    const text = buildInventoryNarrative(h)
    expect(text).toContain('3人于2025-12-31，在公司财务室对有价证券进行盘点')
    expect(text).toContain('现将现场盘点出的有价证券列示如下')
    expect(text).toContain('监盘人：张三')
    expect(text).toContain('盘点人：李四')
    expect(text).toContain('盘点单位：示例公司')
  })

  it('缺省字段用破折号占位', () => {
    const text = buildInventoryNarrative(createDefaultHeader())
    expect(text).toContain('—人于—年—月—日，在—对有价证券进行盘点')
  })
})

describe('headerCompleteness', () => {
  it('关键字段齐全时 missing 为空', () => {
    const h = createDefaultHeader()
    h.company = 'A'
    h.countDate = '2025-01-01'
    h.location = '财务室'
    h.observer = '监盘'
    h.counter = '盘点'
    const status = headerCompleteness(h)
    expect(status.filled).toBe(5)
    expect(status.total).toBe(5)
    expect(status.missing).toEqual([])
  })

  it('列出未填关键字段', () => {
    const status = headerCompleteness(createDefaultHeader())
    expect(status.filled).toBe(0)
    expect(status.missing).toEqual(['盘点单位', '盘点日期', '盘点地点', '监盘人', '盘点人'])
  })
})

describe('isRollForwardNeeded', () => {
  it('两日均填且不相等时需要倒轧', () => {
    expect(isRollForwardNeeded('2026-01-15', '2025-12-31')).toBe(true)
  })

  it('两日相同不需要倒轧', () => {
    expect(isRollForwardNeeded('2025-12-31', '2025-12-31')).toBe(false)
  })

  it('缺任一日不判定需倒轧', () => {
    expect(isRollForwardNeeded('2025-12-31', '')).toBe(false)
    expect(isRollForwardNeeded('', '2025-12-31')).toBe(false)
  })
})

describe('pushToReconciliation', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('将有效盘点行写入 G4-8-items 并同步日期头', () => {
    const allResponses = ref(new Map<string, ChecklistResponse>())
    const saved: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const saveImmediate = (itemId: string, data: Partial<ChecklistResponse>) => {
      saved.push({ id: itemId, data })
      const existing = allResponses.value.get(itemId) || {
        item_id: itemId,
        conclusion: null,
        remark: null,
      }
      allResponses.value.set(itemId, { ...existing, ...data, item_id: itemId })
    }

    const inv = useG4SppiInventory({
      allResponses,
      debouncedSave: saveImmediate,
      saveImmediate,
      isReadonly: ref(false),
      projectBalanceSheetDate: ref('2025-12-31'),
    })

    inv.updateHeader({
      countDate: '2026-01-10',
      balanceSheetDate: '2025-12-31',
      company: '测试',
      location: '财务室',
      observer: 'A',
      counter: 'B',
    })
    inv.updateItem(inv.items.value[0].id, {
      securitiesName: '国债21001',
      faceValue: 100,
      quantity: 10,
      couponRate: 3.5,
      maturityDate: '2030-06-30',
    })

    expect(inv.needsRollForward.value).toBe(true)
    const n = inv.pushToReconciliation()
    expect(n).toBe(1)

    const itemsSave = saved.find((s) => s.id === 'G4-8-items')
    expect(itemsSave).toBeTruthy()
    const rows = JSON.parse(String(itemsSave!.data.remark))
    expect(rows).toHaveLength(1)
    expect(rows[0].securitiesName).toBe('国债21001')
    expect(rows[0].countQuantity).toBe(10)
    expect(rows[0].countFaceValue).toBe(100)
    expect(rows[0].inventoryRowId).toBe(inv.items.value[0].id)

    const headerSave = saved.find((s) => s.id === 'G4-8-header')
    expect(headerSave).toBeTruthy()
    const hdr = JSON.parse(String(headerSave!.data.remark))
    expect(hdr.countDate).toBe('2026-01-10')
    expect(hdr.balanceSheetDate).toBe('2025-12-31')
  })

  it('再次推送时按 inventoryRowId 更新并保留增减', () => {
    const allResponses = ref(
      new Map<string, ChecklistResponse>([
        [
          'G4-8-items',
          {
            item_id: 'G4-8-items',
            conclusion: null,
            remark: JSON.stringify([
              {
                id: 'keep-1',
                securitiesName: '国债21001',
                inventoryRowId: 'inv-1',
                countQuantity: 1,
                countFaceValue: 100,
                increaseQuantity: 2,
                decreaseQuantity: 1,
                remark: '已有说明',
              },
            ]),
          },
        ],
      ]),
    )
    const saved: Array<{ id: string; data: Partial<ChecklistResponse> }> = []
    const saveImmediate = (itemId: string, data: Partial<ChecklistResponse>) => {
      saved.push({ id: itemId, data })
      allResponses.value.set(itemId, {
        item_id: itemId,
        conclusion: null,
        remark: null,
        ...data,
      })
    }

    const inv = useG4SppiInventory({
      allResponses,
      debouncedSave: saveImmediate,
      saveImmediate,
      isReadonly: ref(false),
    })

    inv.items.value = [
      {
        id: 'inv-1',
        seq: 1,
        securitiesName: '国债21001',
        faceValue: 100,
        quantity: 20,
        total: 2000,
        couponRate: 3,
        maturityDate: '2030-01-01',
      },
    ]

    inv.pushToReconciliation()
    const rows = JSON.parse(String(saved.find((s) => s.id === 'G4-8-items')!.data.remark))
    expect(rows).toHaveLength(1)
    expect(rows[0].id).toBe('keep-1')
    expect(rows[0].countQuantity).toBe(20)
    expect(rows[0].increaseQuantity).toBe(2)
    expect(rows[0].decreaseQuantity).toBe(1)
    expect(rows[0].remark).toBe('已有说明')
  })
})
