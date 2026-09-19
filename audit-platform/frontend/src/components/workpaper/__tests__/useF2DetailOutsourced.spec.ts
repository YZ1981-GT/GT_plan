/**
 * useF2DetailOutsourced — F2-7 单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useF2DetailOutsourced } from '../composables/useF2DetailOutsourced'
import type { ChecklistResponse } from '../composables/useF2FormData'

vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessageBox: { prompt: vi.fn().mockResolvedValue({ value: '钢材坯料' }), confirm: vi.fn() },
    ElMessage: { warning: vi.fn(), success: vi.fn() },
  }
})

describe('useF2DetailOutsourced', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true)
  })

  it('金额=数量×单价；加工物资成本=金额+加工费+运杂费+税金', () => {
    const sheet = useF2DetailOutsourced({
      allResponses: ref(new Map()),
      isReadonly: ref(false),
    })
    const id = sheet.rows.value[0].id
    sheet.updateRow(id, {
      qty: 10,
      unitPrice: 100,
      processingFee: 50,
      freight: 20,
      taxInCost: 30,
    })
    const row = sheet.rows.value[0]
    expect(row.amount).toBe(1000)
    expect(row.processingCost).toBe(1100)
    expect(row.closingAmt).toBe(1100)
  })

  it('库龄合计≠成本时 agingOk=false', () => {
    const sheet = useF2DetailOutsourced({
      allResponses: ref(new Map()),
      isReadonly: ref(false),
    })
    const id = sheet.rows.value[0].id
    sheet.updateRow(id, { qty: 1, unitPrice: 100 })
    sheet.updateAgingCell(id, 'within1', 40)
    expect(sheet.agingMismatch.value).toHaveLength(1)
    expect(sheet.totals.value.agingOk).toBe(false)
  })

  it('净额 = 成本合计 − 跌价；始终启用虚拟滚动', () => {
    const sheet = useF2DetailOutsourced({
      allResponses: ref(new Map()),
      isReadonly: ref(false),
    })
    const id = sheet.rows.value[0].id
    sheet.updateRow(id, { qty: 2, unitPrice: 50, processingFee: 10 })
    sheet.persistImpairment(20)
    expect(sheet.totals.value.processingCost).toBe(110)
    expect(sheet.netAmt.value).toBe(90)
    expect(sheet.useVirtualScroll.value).toBe(true)
  })

  it('旧收发存数据可迁移 materialName/closingAmt', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    map.value.set('F2-7-rows', {
      item_id: 'F2-7-rows',
      conclusion: null,
      remark: JSON.stringify([
        { id: '1', itemName: '旧品名', closingAmt: 500, agingLt1: 500 },
      ]),
    })
    const sheet = useF2DetailOutsourced({
      allResponses: map,
      isReadonly: ref(false),
    })
    expect(sheet.rows.value[0].materialName).toBe('旧品名')
    expect(sheet.rows.value[0].processingCost).toBe(500)
    expect(sheet.rows.value[0].aging.within1).toBe(500)
    expect(sheet.totals.value.agingOk).toBe(true)
  })
})
