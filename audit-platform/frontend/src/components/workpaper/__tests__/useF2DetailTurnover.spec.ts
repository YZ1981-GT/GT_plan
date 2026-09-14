import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useF2DetailTurnover } from '../composables/useF2DetailTurnover'
import type { ChecklistResponse } from '../composables/useF2FormData'

vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessageBox: { prompt: vi.fn().mockResolvedValue({ value: '测试品名' }), confirm: vi.fn() },
    ElMessage: { warning: vi.fn(), success: vi.fn() },
  }
})

describe('useF2DetailTurnover', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('初始按六组种子行，合计为 0', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const sheet = useF2DetailTurnover({
      allResponses: map,
      isReadonly: ref(false),
    })
    expect(sheet.rows.value.length).toBe(6)
    expect(sheet.grandTotal.value.closingAmt).toBe(0)
    expect(sheet.grandTotal.value.agingOk).toBe(true)
  })

  it('更新收发存后自动算期末与分组小计', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const sheet = useF2DetailTurnover({
      allResponses: map,
      isReadonly: ref(false),
    })
    const id = sheet.rowsOf('revolving')[0].id
    sheet.updateRow(id, {
      openingAmt: 100,
      increaseAmt: 50,
      decreaseAmt: 20,
      openingQty: 10,
      increaseQty: 5,
      decreaseQty: 2,
    })
    const row = sheet.rows.value.find((r) => r.id === id)!
    expect(row.closingAmt).toBe(130)
    expect(row.closingQty).toBe(13)
    expect(sheet.sectionATotal.value.closingAmt).toBe(130)
    expect(sheet.grandTotal.value.closingAmt).toBe(130)
  })

  it('包装物小计汇总四用途；净额 = 合计 − 跌价', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const sheet = useF2DetailTurnover({
      allResponses: map,
      isReadonly: ref(false),
    })
    for (const key of ['packProd', 'packSoldIncl', 'packSoldSep', 'packRent'] as const) {
      const id = sheet.rowsOf(key)[0].id
      sheet.updateRow(id, { openingAmt: 25 })
    }
    expect(sheet.packagingTotal.value.closingAmt).toBe(100)
    sheet.persistImpairment(15)
    expect(sheet.netAmt.value).toBe(85)
  })

  it('库龄与期末不一致时 agingOk=false', () => {
    const map = ref(new Map<string, ChecklistResponse>())
    const sheet = useF2DetailTurnover({
      allResponses: map,
      isReadonly: ref(false),
    })
    const id = sheet.rowsOf('lowValue')[0].id
    sheet.updateRow(id, { openingAmt: 100 })
    sheet.updateAgingCell(id, 'within1', 40)
    expect(sheet.agingMismatchCount.value).toBe(1)
    expect(sheet.grandTotal.value.agingOk).toBe(false)
  })
})
