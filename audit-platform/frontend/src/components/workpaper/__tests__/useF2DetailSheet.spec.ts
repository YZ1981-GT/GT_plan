/**
 * useF2DetailSheet — 单元测试
 *
 * 覆盖：addRow/removeRow/updateRow/enrichRow/搜索筛选/虚拟滚动/库龄校验/长期积压
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, computed } from 'vue'

vi.mock('element-plus', () => ({
  ElMessageBox: {
    prompt: vi.fn().mockResolvedValue({ value: '测试品名' }),
  },
  ElMessage: { warning: vi.fn(), success: vi.fn() },
}))

import { useF2DetailSheet, type F2DetailRow } from '../composables/useF2DetailSheet'
import type { ChecklistResponse } from '../composables/useF2FormData'
import { F2_DETAIL_SHEET_CONFIGS } from '../f2/detail/f2DetailSheetConfigs'

function makeConfig(sheetCode = 'F2-3') {
  return computed(() => ({
    sheetCode,
    categoryLabel: '原材料',
    hasQuantity: true,
    accountCode: '1401',
  }))
}

function legacyRow(partial: Partial<F2DetailRow> & { id: string; itemName: string }): F2DetailRow {
  return {
    itemCode: '',
    supplier: '',
    spec: '',
    unit: '',
    openingQty: 0,
    openingAmt: 0,
    increaseQty: 0,
    increaseAmt: 0,
    decreaseQty: 0,
    decreaseAmt: 0,
    closingQty: 0,
    closingAmt: 0,
    postPeriodQty: 0,
    postPeriodAmt: 0,
    postPeriodUnitPrice: '',
    openingUnitPrice: '',
    increaseUnitPrice: '',
    decreaseUnitPrice: '',
    unitPrice: '',
    aging: {},
    agingTotal: 0,
    qualityStatus: '',
    hasOpenOrder: '',
    orderNo: '',
    salesUnitPrice: '',
    agingLt1: 0,
    aging1to2: 0,
    aging2to3: 0,
    agingGt3: 0,
    ...partial,
  }
}

function makeResponses(rows?: F2DetailRow[], sheetCode = 'F2-3'): Map<string, ChecklistResponse> {
  const map = new Map<string, ChecklistResponse>()
  if (rows) {
    map.set(`${sheetCode}-rows`, {
      item_id: `${sheetCode}-rows`,
      conclusion: null,
      remark: JSON.stringify(rows),
    })
  }
  return map
}

describe('useF2DetailSheet', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
    expect(detail.rows.value[0].aging).toBeTruthy()
  })

  it('加载已有数据并 enrichRow 计算公式（含旧库龄 flat 迁移）', () => {
    const rows = [legacyRow({
      id: '1',
      itemName: '钢材',
      openingQty: 100,
      openingAmt: 10000,
      increaseQty: 50,
      increaseAmt: 5000,
      decreaseQty: 30,
      decreaseAmt: 3000,
      agingLt1: 8000,
      aging1to2: 2000,
      aging2to3: 1500,
      agingGt3: 500,
    })]

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
    })

    const row = detail.rows.value[0]
    expect(row.closingQty).toBe(120)
    expect(row.closingAmt).toBe(12000)
    expect(row.unitPrice).toBe(100)
    expect(row.agingTotal).toBe(12000)
    expect(row.aging.within1).toBe(8000)
    expect(detail.totals.value.agingOk).toBe(true)
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
    const rows = [
      legacyRow({ id: '1', itemName: 'A' }),
      legacyRow({ id: '2', itemName: 'B' }),
    ]

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
    })

    detail.removeRow('1')
    expect(detail.rows.value).toHaveLength(1)
    expect(detail.rows.value[0].itemName).toBe('B')

    detail.removeRow('2')
    expect(detail.rows.value).toHaveLength(1)
  })

  it('updateRow 触发公式重算', () => {
    const rows = [legacyRow({
      id: '1',
      itemName: '铜管',
      openingQty: 100,
      openingAmt: 10000,
    })]

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
    })

    detail.updateRow('1', { increaseAmt: 5000 })
    expect(detail.rows.value[0].closingAmt).toBe(15000)
  })

  it('searchText 筛选编码/品名/规格', () => {
    const rows = [
      legacyRow({ id: '1', itemName: '钢材A型', itemCode: 'RM-01', openingAmt: 100, closingAmt: 100, agingLt1: 100 }),
      legacyRow({ id: '2', itemName: '铜管B型', itemCode: 'RM-02', openingAmt: 200, closingAmt: 200, agingLt1: 200 }),
      legacyRow({ id: '3', itemName: '钢材C型', spec: 'Φ20', openingAmt: 300, closingAmt: 300, agingLt1: 300 }),
    ]

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
    })

    detail.searchText.value = '钢材'
    expect(detail.filteredRows.value).toHaveLength(2)

    detail.searchText.value = 'RM-02'
    expect(detail.filteredRows.value).toHaveLength(1)

    detail.searchText.value = 'Φ20'
    expect(detail.filteredRows.value).toHaveLength(1)
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
    const rows = [legacyRow({
      id: '1',
      itemName: '品A',
      openingAmt: 1000,
      agingLt1: 500,
      aging1to2: 200,
      aging2to3: 100,
      agingGt3: 50,
    })]

    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
    })

    expect(detail.agingMismatch.value).toHaveLength(1)
    expect(detail.totals.value.agingOk).toBe(false)
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

  it('净额 = 期末合计 − 跌价准备', () => {
    const rows = [legacyRow({
      id: '1',
      itemName: 'A',
      openingAmt: 1000,
      agingLt1: 1000,
    })]
    const detail = useF2DetailSheet({
      config: makeConfig(),
      allResponses: ref(makeResponses(rows)),
      isReadonly: ref(false),
    })
    detail.persistImpairment(200)
    expect(detail.netAmt.value).toBe(800)
  })

  it('F2-4 期后结转单价自动计算', () => {
    const map = new Map<string, ChecklistResponse>()
    map.set('F2-4-rows', {
      item_id: 'F2-4-rows',
      conclusion: null,
      remark: JSON.stringify([legacyRow({
        id: '1',
        itemName: '钢板',
        supplier: '甲钢厂',
        openingAmt: 1000,
        agingLt1: 1000,
        postPeriodQty: 10,
        postPeriodAmt: 500,
      })]),
    })
    const detail = useF2DetailSheet({
      config: computed(() => ({
        sheetCode: 'F2-4',
        categoryLabel: '材料采购/在途物资',
        accountCode: '1402',
        hasQuantity: true,
        identityMode: 'inTransit' as const,
        hasPostPeriod: true,
        decreaseGroupLabel: '本期转出',
        noteProfile: 'inTransit' as const,
      })),
      allResponses: ref(map),
      isReadonly: ref(false),
    })
    expect(detail.rows.value[0].supplier).toBe('甲钢厂')
    expect(detail.rows.value[0].postPeriodUnitPrice).toBe(50)
    expect(detail.totals.value.postPeriodAmt).toBe(500)
  })

  it('F2-8/F2-9 销售台账差异 = 发出数量合计 − 台账数量', () => {
    const rows = [legacyRow({
      id: '1',
      itemName: '成品A',
      openingQty: 0,
      increaseQty: 100,
      decreaseQty: 80,
      openingAmt: 0,
      increaseAmt: 1000,
      decreaseAmt: 800,
      agingLt1: 200,
    })]
    const detail = useF2DetailSheet({
      config: computed(() => ({
        ...F2_DETAIL_SHEET_CONFIGS['F2-8'],
      })),
      allResponses: ref(makeResponses(rows, 'F2-8')),
      isReadonly: ref(false),
    })
    expect(detail.totals.value.decreaseQty).toBe(80)
    detail.persistSalesLedgerQty(75)
    expect(detail.salesLedgerQty.value).toBe(75)
    expect(detail.salesLedgerDiff.value).toBe(5)
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
