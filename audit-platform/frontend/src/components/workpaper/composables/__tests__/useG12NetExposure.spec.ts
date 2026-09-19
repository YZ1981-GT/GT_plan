import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useG12NetExposure } from '../useG12NetExposure'
import { suggestNetPosition, inferCurrencyFromAmount, resolveRowCurrency } from '../g12NetExposureCalc'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), success: vi.fn(), info: vi.fn() },
}))

describe('g12NetExposureCalc', () => {
  it('从头寸金额建议净头寸', () => {
    expect(suggestNetPosition('1,000万美元', '1,200万美元')).toBe('支付200万美元')
    expect(suggestNetPosition('1,200万美元', '1,000万美元')).toBe('收200万美元')
  })

  it('无嵌入币种时使用行币种', () => {
    expect(suggestNetPosition('1,000万', '1,200万', 'EUR')).toBe('支付200万欧元')
    expect(inferCurrencyFromAmount('500万欧元')).toBe('EUR')
  })

  it('resolveRowCurrency 从金额推断', () => {
    expect(resolveRowCurrency({ position1Amount: '100万英镑' })).toBe('GBP')
  })
})

describe('useG12NetExposure', () => {
  let allResponses: ReturnType<typeof ref<Map<string, ChecklistResponse>>>
  let saved: Array<{ id: string; data: Partial<ChecklistResponse> }>
  let ne: ReturnType<typeof useG12NetExposure>

  beforeEach(() => {
    saved = []
    allResponses = ref(new Map())
    ne = useG12NetExposure({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: (id, data) => { saved.push({ id, data }) },
    })
  })

  it('种子含源模板示例行与 USD 币种', () => {
    expect(ne.rows.value.length).toBeGreaterThanOrEqual(1)
    expect(ne.rows.value[0].item).toContain('外汇净头寸')
    expect(ne.rows.value[0].currency).toBe('USD')
    expect(ne.testObjective.value).toContain('支持性证据')
  })

  it('修改头寸金额时自动建议净头寸', () => {
    const rowId = ne.rows.value[0].rowId
    ne.updateCell(rowId, 'position1Amount', '500万美元')
    ne.updateCell(rowId, 'position2Amount', '800万美元')
    const row = ne.rows.value.find((r) => r.rowId === rowId)!
    expect(row.netPosition).toBe('支付300万美元')
  })

  it('addCurrencyRow 同项目新增币种分行', () => {
    const src = ne.rows.value[0]
    const before = ne.rows.value.length
    ne.addCurrencyRow(src.rowId, 'EUR')
    expect(ne.rows.value.length).toBe(before + 1)
    const eurRow = ne.rows.value.find((r) => r.currency === 'EUR')!
    expect(eurRow.item).toBe(src.item)
    expect(eurRow.position1Desc).toBe(src.position1Desc)
    expect(eurRow.position1Amount).toBe('')
    expect(ne.itemGroups.value.some((g) => g.currencies.includes('USD') && g.currencies.includes('EUR'))).toBe(true)
  })

  it('未完成必填项时 saveValidated 阻断', () => {
    saved.length = 0
    ne.addRow()
    expect(ne.saveValidated()).toBe(false)
  })

  it('全部行完善后可保存', () => {
    for (const row of ne.rows.value) {
      ne.updateCell(row.rowId, 'item', row.item || '测试项目')
      ne.updateCell(row.rowId, 'currency', row.currency || 'USD')
      ne.updateCell(row.rowId, 'position1Desc', row.position1Desc || '头寸A')
      ne.updateCell(row.rowId, 'position2Desc', row.position2Desc || '头寸B')
      if (!row.netPosition) ne.updateCell(row.rowId, 'netPosition', '零净头寸')
    }
    saved.length = 0
    expect(ne.saveValidated()).toBe(true)
    expect(saved.some((s) => s.id === 'G12-net-exposure-rows')).toBe(true)
  })

  it('旧版问卷数据自动降级为种子行', () => {
    allResponses.value = new Map([
      ['G12-net-exposure-rows', {
        remark: JSON.stringify([{ checkItem: '旧问卷', compliance: 'compliant' }]),
      } as ChecklistResponse],
    ])
    const ne2 = useG12NetExposure({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: () => {},
    })
    expect(ne2.rows.value[0].item).toContain('外汇净头寸')
    expect(ne2.rows.value[0].currency).toBe('USD')
  })

  it('无 currency 的历史行从金额推断币种', () => {
    allResponses.value = new Map([
      ['G12-net-exposure-rows', {
        remark: JSON.stringify([{
          rowId: 'legacy-1',
          item: '欧元敞口',
          position1Amount: '100万欧元',
          position2Amount: '80万欧元',
          netPosition: '收20万欧元',
          position1Desc: 'A',
          position2Desc: 'B',
        }]),
      } as ChecklistResponse],
    ])
    const ne2 = useG12NetExposure({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: () => {},
    })
    expect(ne2.rows.value[0].currency).toBe('EUR')
  })

  it('无 evidenceType 的历史行从 supportingEvidence 推断类型', () => {
    allResponses.value = new Map([
      ['G12-net-exposure-rows', {
        remark: JSON.stringify([{
          rowId: 'legacy-ev',
          item: '外汇净头寸',
          currency: 'USD',
          position1Desc: 'A',
          position2Desc: 'B',
          netPosition: '零',
          supportingEvidence: '销售预算表',
        }]),
      } as ChecklistResponse],
    ])
    const ne2 = useG12NetExposure({
      allResponses,
      isReadonly: ref(false),
      debouncedSave: () => {},
    })
    expect(ne2.rows.value[0].evidenceType).toBe('sales_budget')
  })

  it('importFromHedgeDetail sets hedgeRelationId', () => {
    saved.length = 0
    ne.importFromHedgeDetail([{
      item: '预期销售',
      hedgingInstrument: '远期A',
      hedgeRelationId: 'HR-99',
      indexRef: '',
    }])
    const row = ne.rows.value.find((r) => r.hedgeRelationId === 'HR-99')
    expect(row).toBeTruthy()
    expect(row!.hedgingInstrument).toBe('远期A')
  })
})
