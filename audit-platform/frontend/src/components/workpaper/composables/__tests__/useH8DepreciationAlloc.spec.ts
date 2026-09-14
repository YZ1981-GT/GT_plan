/**
 * useH8DepreciationAlloc — H8-9 矩阵分配单元测试
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  useH8DepreciationAlloc,
  calcH8RowAllocSum,
  isH8RowBalanced,
  H8_DEFAULT_CATEGORIES,
} from '../useH8DepreciationAlloc'

function makeMap(entries: Record<string, any> = {}) {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) {
    m.set(k, { remark: typeof v === 'string' ? v : JSON.stringify(v) })
  }
  return m
}

describe('useH8DepreciationAlloc', () => {
  it('默认播种 Excel 五类资产', () => {
    const allResponses = ref(makeMap())
    const { rows } = useH8DepreciationAlloc({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
    })
    expect(rows.value.map((r) => r.category)).toEqual([...H8_DEFAULT_CATEGORIES])
  })

  it('横向：行合计等于折旧总额时配平', () => {
    const row = {
      rowId: '1',
      category: '房屋及建筑物',
      depTotal: 1000,
      operatingCost: 400,
      manufacturing: 0,
      selling: 0,
      admin: 600,
      rd: 0,
      other: 0,
      remark: '',
    }
    expect(calcH8RowAllocSum(row)).toBe(1000)
    expect(isH8RowBalanced(row)).toBe(true)
  })

  it('横向：未配平行标红', () => {
    const row = {
      rowId: '1',
      category: '机器设备',
      depTotal: 500,
      operatingCost: 100,
      manufacturing: 100,
      selling: 0,
      admin: 0,
      rd: 0,
      other: 0,
      remark: '',
    }
    expect(isH8RowBalanced(row)).toBe(false)
  })

  it('从 H8-8 按分类同步折旧总额', () => {
    const allResponses = ref(makeMap())
    const byCat = ref({ 房屋及建筑物: 1200, 机器设备: 800 })
    const total = ref(2000)
    const { rows, h88DepTotal, isBalancedWithH88, updateCell } = useH8DepreciationAlloc({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      crossSheetByCategory: byCat,
      crossSheetDepTotal: total,
    })

    expect(rows.value.find((r) => r.category === '房屋及建筑物')?.depTotal).toBe(1200)
    expect(rows.value.find((r) => r.category === '机器设备')?.depTotal).toBe(800)
    expect(h88DepTotal.value).toBe(2000)

    const bldg = rows.value.find((r) => r.category === '房屋及建筑物')!
    updateCell(bldg.rowId, 'admin', 1200)
    const mach = rows.value.find((r) => r.category === '机器设备')!
    updateCell(mach.rowId, 'operatingCost', 800)
    expect(isBalancedWithH88.value).toBe(true)
  })

  it('迁移旧版比例分配结构到矩阵', () => {
    const legacy = [
      { rowId: 'a1', expenseType: '管理费用', allocRatio: 60, allocAmount: 600 },
      { rowId: 'a2', expenseType: '销售费用', allocRatio: 40, allocAmount: 400 },
    ]
    const allResponses = ref(makeMap({ 'H8-9-alloc-rows': legacy }))
    const saved: any[] = []
    const { rows, colTotals } = useH8DepreciationAlloc({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave: (_id, val) => { if (Array.isArray(val)) saved.push(val) },
    })

    const catchAll = rows.value.find((r) => r.category === '其他设备')!
    expect(catchAll.admin).toBe(600)
    expect(catchAll.selling).toBe(400)
    expect(catchAll.remark).toContain('迁移')
    expect(colTotals.value.allocSum).toBe(1000)
    expect(saved.length).toBeGreaterThan(0)
  })

  it('勾稽核对含 H8-8 与各费用列', () => {
    const allResponses = ref(makeMap())
    const { reconciliationRows } = useH8DepreciationAlloc({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      crossSheetDepTotal: ref(0),
    })
    const labels = reconciliationRows.value.map((r) => r.label)
    expect(labels[0]).toBe('分配合计 vs H8-8')
    expect(labels).toContain('营业成本折旧')
    expect(labels).toContain('管理费用折旧')
    expect(labels).toContain('研发支出折旧')
  })

  it('差额一键计入指定费用列后行配平', () => {
    const allResponses = ref(makeMap())
    const byCat = ref({ 房屋及建筑物: 1000 })
    const { rows, allocateAllRemaindersTo, isRowBalanced } = useH8DepreciationAlloc({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      crossSheetByCategory: byCat,
      crossSheetDepTotal: ref(1000),
    })
    const bldg = rows.value.find((r) => r.category === '房屋及建筑物')!
    expect(isRowBalanced(bldg)).toBe(false)
    const n = allocateAllRemaindersTo('admin')
    expect(n).toBeGreaterThanOrEqual(1)
    expect(bldg.admin).toBe(1000)
    expect(isRowBalanced(bldg)).toBe(true)
  })

  it('手工覆盖对方底稿数并标记', () => {
    const allResponses = ref(makeMap())
    const { setCounterpartManual, reconciliationRows } = useH8DepreciationAlloc({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
    })
    setCounterpartManual('admin', 888)
    const adminRow = reconciliationRows.value.find((r) => r.field === 'admin')!
    expect(adminRow.counterpart).toBe(888)
    expect(adminRow.isManual).toBe(true)
  })

  it('保存上期一致性评估', () => {
    const saved: Record<string, any> = {}
    const allResponses = ref(makeMap())
    const { savePriorAssessment, priorConsistent, priorNote } = useH8DepreciationAlloc({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
      onSave: (id, val) => { saved[id] = val },
    })
    savePriorAssessment('Y', '用途与上期相同')
    expect(priorConsistent.value).toBe('Y')
    expect(priorNote.value).toBe('用途与上期相同')
    expect(saved['H8-9-prior-consistency']).toEqual({ consistent: 'Y', note: '用途与上期相同' })
  })

  it('exposes client xlsx exportData/importData', () => {
    const allResponses = ref(makeMap())
    const api = useH8DepreciationAlloc({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses,
    })
    expect(typeof api.exportData).toBe('function')
    expect(typeof api.importData).toBe('function')
  })
})
