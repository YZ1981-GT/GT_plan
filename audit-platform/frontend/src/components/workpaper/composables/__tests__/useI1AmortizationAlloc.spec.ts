/**
 * useI1AmortizationAlloc — I1-9 摊销分配单元测试
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useI1AmortizationAlloc,
  calcI1RowAllocSum,
  isI1RowBalanced,
  calcI1RowRemainder,
  parseAmortizationByAsset,
  I1_EXPENSE_COLS,
  type I1AllocRow,
} from '../useI1AmortizationAlloc'

function makeMap(entries: Record<string, any>): Map<string, any> {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, typeof v === 'string' ? { remark: v } : { remark: JSON.stringify(v) })
  }
  return m
}

describe('useI1AmortizationAlloc', () => {
  it('费用列顺序对齐 Excel：生产成本→制造→销售→管理→研发→其他', () => {
    expect(I1_EXPENSE_COLS.map((c) => c.label)).toEqual([
      '生产成本',
      '制造费用',
      '销售费用',
      '管理费用',
      '研发费用',
      '其他',
    ])
  })

  it('销售费用→K8、管理费用→K9（修正原芯片错位）', () => {
    expect(I1_EXPENSE_COLS.find((c) => c.field === 'sellingExpense')?.targetWpCode).toBe('K8')
    expect(I1_EXPENSE_COLS.find((c) => c.field === 'managementExpense')?.targetWpCode).toBe('K9')
    expect(I1_EXPENSE_COLS.find((c) => c.field === 'rdExpense')?.targetWpCode).toBe('I6')
  })

  it('行合计与配平校验', () => {
    const row: I1AllocRow = {
      rowId: '1',
      name: '软件A',
      totalAmort: 1000,
      productionCost: 100,
      manufacturingCost: 200,
      sellingExpense: 0,
      managementExpense: 700,
      rdExpense: 0,
      otherExpense: 0,
      remark: '',
    }
    expect(calcI1RowAllocSum(row)).toBe(1000)
    expect(isI1RowBalanced(row)).toBe(true)
    expect(calcI1RowRemainder(row)).toBe(0)

    row.managementExpense = 600
    expect(isI1RowBalanced(row)).toBe(false)
    expect(calcI1RowRemainder(row)).toBe(100)
  })

  it('从 I1-10 解析按资产摊销额', () => {
    const map = makeMap({
      'I1-10-rows': [
        { name: '专利甲', periodAmortization: 12000 },
        { name: '商标乙', periodAmortization: 8000 },
      ],
    })
    const { byAsset, total, sourceSheet } = parseAmortizationByAsset(map)
    expect(sourceSheet).toBe('I1-10')
    expect(total).toBe(20000)
    expect(byAsset['专利甲']).toBe(12000)
  })

  it('优先取 I1-11（含减值）', () => {
    const map = makeMap({
      'I1-10-rows': [{ name: 'A', periodAmortization: 1 }],
      'I1-11-rows': [{ name: 'B', periodAmortization: 99 }],
    })
    const { byAsset, sourceSheet } = parseAmortizationByAsset(map)
    expect(sourceSheet).toBe('I1-11')
    expect(byAsset['B']).toBe(99)
    expect(byAsset['A']).toBeUndefined()
  })

  it('差额一键计入选定费用列后行配平', () => {
    const saved: Array<{ id: string; value: any }> = []
    const map = ref(makeMap({
      'I1-10-rows': [{ name: '软件A', periodAmortization: 1000 }],
      'I1-9-rows': [
        {
          rowId: 'r1',
          name: '软件A',
          totalAmort: 1000,
          productionCost: 0,
          manufacturingCost: 0,
          sellingExpense: 0,
          managementExpense: 400,
          rdExpense: 0,
          otherExpense: 0,
          remark: '',
        },
      ],
    }))

    const api = useI1AmortizationAlloc({
      allResponses: map,
      onSave: (id, value) => saved.push({ id, value }),
    })

    expect(api.unbalancedCount.value).toBe(1)
    const n = api.allocateAllRemaindersTo('managementExpense')
    expect(n).toBe(1)
    expect(api.rows.value[0]!.managementExpense).toBe(1000)
    expect(api.isRowBalanced(api.rows.value[0]!)).toBe(true)
    expect(api.isBalancedWithSource.value).toBe(true)
  })

  it('兼容旧数据缺 productionCost 字段', () => {
    const map = ref(makeMap({
      'I1-9-rows': [
        {
          rowId: 'r1',
          name: '旧行',
          totalAmort: 500,
          managementExpense: 500,
          sellingExpense: 0,
          manufacturingCost: 0,
          rdExpense: 0,
          otherExpense: 0,
        },
      ],
    }))
    const api = useI1AmortizationAlloc({ allResponses: map })
    expect(api.rows.value[0]!.productionCost).toBe(0)
    expect(api.isRowBalanced(api.rows.value[0]!)).toBe(true)
  })

  it('applyCounterpartPull 写入对方数；手工覆盖在拉取失败时保留', () => {
    const saved: any[] = []
    const map = ref(makeMap({ 'I1-9-rows': [] }))
    const api = useI1AmortizationAlloc({
      allResponses: map,
      onSave: (_id, v) => saved.push(v),
    })
    api.setCounterpartManual('managementExpense', 888)
    api.applyCounterpartPull({
      productionCost: { amount: 100, message: 'ok', matchedLabel: '无形资产摊销', status: 'ok' },
      sellingExpense: { amount: 200, message: 'ok', matchedLabel: '无形资产摊销', status: 'ok' },
      managementExpense: { amount: null, message: 'missing', matchedLabel: '', status: 'row_missing' },
      rdExpense: { amount: 50, message: 'ok', matchedLabel: '无形资产摊销', status: 'ok' },
    })
    expect(api.reconciliationRows.value.find((r) => r.field === 'managementExpense')?.counterpart).toBe(888)
    expect(api.reconciliationRows.value.find((r) => r.field === 'sellingExpense')?.counterpart).toBe(200)
  })

  it('按类别汇总视图聚合费用列', () => {
    const map = ref(makeMap({
      'I1-2-rows': [
        { name: '软件A', category: '软件' },
        { name: '专利B', category: '专利' },
      ],
      'I1-10-rows': [
        { name: '软件A', periodAmortization: 1000, category: '软件' },
        { name: '专利B', periodAmortization: 500, category: '专利' },
      ],
      'I1-9-rows': [
        {
          rowId: '1', name: '软件A', category: '软件', totalAmort: 1000,
          productionCost: 0, manufacturingCost: 0, sellingExpense: 0,
          managementExpense: 1000, rdExpense: 0, otherExpense: 0, remark: '',
        },
        {
          rowId: '2', name: '专利B', category: '专利', totalAmort: 500,
          productionCost: 500, manufacturingCost: 0, sellingExpense: 0,
          managementExpense: 0, rdExpense: 0, otherExpense: 0, remark: '',
        },
      ],
    }))
    const api = useI1AmortizationAlloc({ allResponses: map })
    const cats = api.categorySummaryRows.value
    expect(cats.find((c) => c.category === '软件')?.managementExpense).toBe(1000)
    expect(cats.find((c) => c.category === '专利')?.productionCost).toBe(500)
  })
})
