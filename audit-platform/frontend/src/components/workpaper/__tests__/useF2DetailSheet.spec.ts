/**
 * useF2DetailSheet — 单元测试
 *
 * 覆盖：addRow/removeRow/updateRow/enrichRow/搜索筛选/虚拟滚动/库龄校验/长期积压
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed, nextTick } from 'vue'

// Mock ElMessageBox
vi.mock('element-plus', () => ({
  ElMessageBox: {
    prompt: vi.fn().mockResolvedValue({ value: '测试品名' }),
  },
}))

import { useF2DetailSheet, type F2DetailRow } from '../composables/useF2DetailSheet'
import type { ChecklistResponse } from '../composables/useF2FormData'

function makeConfig(sheetCode = 'F2-3') {
  return computed(() => ({
    sheetCode,
    categoryLabel: '原材料',
    hasQuantity: true,
    accountCode: '1401',
  }))
}

function makeResponses(rows?: F2DetailRow[]): Map<string, ChecklistResponse> {
  const map = new Map<string, ChecklistResponse>()
  if (rows) {
    map.set('F2-3-rows', {
      item_id: 'F2-3-rows',
      conclusion: null,
      remark: JSON.stringify(rows),
    })
  }
  return map
}

describe('useF2DetailSheet', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Mock CustomEvent dispatch
    vi.spyOn(window, 'dispatchEvent').mockImplementation(() => true)
  })

  it('初始化空数据时创建一个空行', () => {
    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(new Map()),
      isReadonly: ref(false),
    })

    expect(detail.rows.value).toHaveLength(1)
    expect(detail.rows.value[0].itemName).toBe('')
  })

  it('加载已有数据并enrichRow计算公式', () => {
    const rows: F2DetailRow[] = [{
      id: '1', itemName: '钢材',
      openingQty: 100, openingAmt: 10000,
      increaseQty: 50, increaseAmt: 5000,
      decreaseQty: 30, decreaseAmt: 3000,
      closingQty: 0, closingAmt: 0, unitPrice: '',
      agingLt1: 8000, aging1to2: 2000, aging2to3: 1500, agingGt3: 500, agingTotal: 0,
    }]

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
    })

    const row = detail.rows.value[0]
    // 期末数量 = 100 + 50 - 30 = 120
    expect(row.closingQty).toBe(120)
    // 期末金额 = 10000 + 5000 - 3000 = 12000
    expect(row.closingAmt).toBe(12000)
    // 单价 = 12000 / 120 = 100
    expect(row.unitPrice).toBe(100)
    // 库龄合计 = 8000 + 2000 + 1500 + 500 = 12000
    expect(row.agingTotal).toBe(12000)
  })

  it('addRow 弹出输入框后新增行', async () => {
    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(new Map()),
      isReadonly: ref(false),
    })

    await detail.addRow()
    expect(detail.rows.value).toHaveLength(2)
    expect(detail.rows.value[1].itemName).toBe('测试品名')
  })

  it('removeRow 删除行（保留至少1行）', () => {
    const rows: F2DetailRow[] = [
      { id: '1', itemName: 'A', openingQty: 0, openingAmt: 0, increaseQty: 0, increaseAmt: 0, decreaseQty: 0, decreaseAmt: 0, closingQty: 0, closingAmt: 0, unitPrice: '', agingLt1: 0, aging1to2: 0, aging2to3: 0, agingGt3: 0, agingTotal: 0 },
      { id: '2', itemName: 'B', openingQty: 0, openingAmt: 0, increaseQty: 0, increaseAmt: 0, decreaseQty: 0, decreaseAmt: 0, closingQty: 0, closingAmt: 0, unitPrice: '', agingLt1: 0, aging1to2: 0, aging2to3: 0, agingGt3: 0, agingTotal: 0 },
    ]

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
    })

    detail.removeRow('1')
    expect(detail.rows.value).toHaveLength(1)
    expect(detail.rows.value[0].itemName).toBe('B')

    // 不能删到0行
    detail.removeRow('2')
    expect(detail.rows.value).toHaveLength(1)
  })

  it('updateRow 触发公式重算', () => {
    const rows: F2DetailRow[] = [{
      id: '1', itemName: '铜管',
      openingQty: 100, openingAmt: 10000,
      increaseQty: 0, increaseAmt: 0,
      decreaseQty: 0, decreaseAmt: 0,
      closingQty: 0, closingAmt: 0, unitPrice: '',
      agingLt1: 0, aging1to2: 0, aging2to3: 0, agingGt3: 0, agingTotal: 0,
    }]

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
    })

    detail.updateRow('1', { increaseAmt: 5000 })
    expect(detail.rows.value[0].closingAmt).toBe(15000)
  })

  it('searchText 筛选品名', () => {
    const rows: F2DetailRow[] = [
      { id: '1', itemName: '钢材A型', openingQty: 0, openingAmt: 100, increaseQty: 0, increaseAmt: 0, decreaseQty: 0, decreaseAmt: 0, closingQty: 0, closingAmt: 100, unitPrice: '', agingLt1: 100, aging1to2: 0, aging2to3: 0, agingGt3: 0, agingTotal: 100 },
      { id: '2', itemName: '铜管B型', openingQty: 0, openingAmt: 200, increaseQty: 0, increaseAmt: 0, decreaseQty: 0, decreaseAmt: 0, closingQty: 0, closingAmt: 200, unitPrice: '', agingLt1: 200, aging1to2: 0, aging2to3: 0, agingGt3: 0, agingTotal: 200 },
      { id: '3', itemName: '钢材C型', openingQty: 0, openingAmt: 300, increaseQty: 0, increaseAmt: 0, decreaseQty: 0, decreaseAmt: 0, closingQty: 0, closingAmt: 300, unitPrice: '', agingLt1: 300, aging1to2: 0, aging2to3: 0, agingGt3: 0, agingTotal: 300 },
    ]

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
    })

    expect(detail.filteredRows.value).toHaveLength(3)

    detail.searchText.value = '钢材'
    expect(detail.filteredRows.value).toHaveLength(2)
    expect(detail.filteredRows.value.every((r) => r.itemName.includes('钢材'))).toBe(true)

    detail.searchText.value = 'B型'
    expect(detail.filteredRows.value).toHaveLength(1)
    expect(detail.filteredRows.value[0].itemName).toBe('铜管B型')

    detail.searchText.value = ''
    expect(detail.filteredRows.value).toHaveLength(3)
  })

  it('useVirtualScroll F2-7始终启用', () => {
    const detail = useF2DetailSheet({
      config: computed(() => ({
        sheetCode: 'F2-7',
        categoryLabel: '委托加工',
        hasQuantity: true,
        accountCode: '1405',
      })),
      allResponses: ref(new Map()),
      isReadonly: ref(false),
    })

    expect(detail.useVirtualScroll.value).toBe(true)
  })

  it('agingMismatch 检测库龄≠期末', () => {
    const rows: F2DetailRow[] = [{
      id: '1', itemName: '品A',
      openingQty: 0, openingAmt: 1000,
      increaseQty: 0, increaseAmt: 0,
      decreaseQty: 0, decreaseAmt: 0,
      closingQty: 0, closingAmt: 0, unitPrice: '',
      agingLt1: 500, aging1to2: 200, aging2to3: 100, agingGt3: 50, agingTotal: 0,
    }]

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
    })

    // closingAmt = 1000, agingTotal = 850 → mismatch
    expect(detail.agingMismatch.value).toHaveLength(1)
  })

  it('isLongTermRow 标记库龄3年以上有值', () => {
    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(new Map()),
      isReadonly: ref(false),
    })

    expect(detail.isLongTermRow({ agingGt3: 100 } as F2DetailRow)).toBe(true)
    expect(detail.isLongTermRow({ agingGt3: 0 } as F2DetailRow)).toBe(false)
  })

  it('readonly 模式下 addRow/removeRow/updateRow 无效', async () => {
    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(new Map()),
      isReadonly: ref(true),
    })

    const initialLen = detail.rows.value.length
    await detail.addRow()
    expect(detail.rows.value).toHaveLength(initialLen)

    detail.removeRow(detail.rows.value[0].id)
    expect(detail.rows.value).toHaveLength(initialLen)
  })
})
