import { describe, it, expect } from 'vitest'
import { mergeAuxRowsIntoDetail, normalizeInvesteeName } from '../g7AuxExtraction'
import { createG7CostRow, createG7EquityRow, type G7DetailState } from '../g7DetailModel'

function emptyState(): G7DetailState {
  return { costRows: [], equityRows: [], impairmentRows: [] }
}

describe('normalizeInvesteeName', () => {
  it('去空白/全角空格/全角括号', () => {
    expect(normalizeInvesteeName(' 子公司 甲 ')).toBe('子公司甲')
    expect(normalizeInvesteeName('乙（北京）公司')).toBe('乙(北京)公司')
  })
})

describe('mergeAuxRowsIntoDetail', () => {
  it('新单位 → 新增成本法行', () => {
    const state = emptyState()
    const r = mergeAuxRowsIntoDetail(state, [
      { investeeName: '子公司甲', openingAmount: 100, increaseAmount: 30, decreaseAmount: 10 },
    ], { overwrite: false })
    expect(r.added).toBe(1)
    expect(state.costRows).toHaveLength(1)
    expect(state.costRows[0].section).toBe('cost')
    expect(state.costRows[0].openingAmount).toBe(100)
  })

  it('Property 2：overwrite=false 只填空值，已填值不变', () => {
    const state = emptyState()
    const row = createG7CostRow(1, '子公司甲')
    row.openingAmount = 999 // 已填
    row.increaseAmount = 0  // 空
    state.costRows.push(row)

    const r = mergeAuxRowsIntoDetail(state, [
      { investeeName: '子公司甲', openingAmount: 100, increaseAmount: 30 },
    ], { overwrite: false })

    expect(r.added).toBe(0)
    expect(r.filled).toBe(1)
    expect(state.costRows[0].openingAmount).toBe(999) // 已填不变
    expect(state.costRows[0].increaseAmount).toBe(30) // 空值被填
  })

  it('overwrite=true 覆盖已填金额', () => {
    const state = emptyState()
    const row = createG7CostRow(1, '子公司甲')
    row.openingAmount = 999
    state.costRows.push(row)
    const r = mergeAuxRowsIntoDetail(state, [
      { investeeName: '子公司甲', openingAmount: 100 },
    ], { overwrite: true })
    expect(r.filled).toBe(1)
    expect(state.costRows[0].openingAmount).toBe(100)
  })

  it('Property 4：同一取数重复应用幂等（不新增、不改值）', () => {
    const state = emptyState()
    const aux = [{ investeeName: '子公司甲', openingAmount: 100, increaseAmount: 30 }]
    mergeAuxRowsIntoDetail(state, aux, { overwrite: false })
    const before = state.costRows.length
    const r2 = mergeAuxRowsIntoDetail(state, aux, { overwrite: false })
    expect(state.costRows.length).toBe(before)
    expect(r2.added).toBe(0)
    expect(r2.filled).toBe(0)
    expect(r2.skipped).toBe(1)
  })

  it('名称规范化匹配（带空白视为同一单位）', () => {
    const state = emptyState()
    state.costRows.push(createG7CostRow(1, ' 子公司甲 '))
    const r = mergeAuxRowsIntoDetail(state, [
      { investeeName: '子公司甲', openingAmount: 100 },
    ], { overwrite: false })
    expect(r.added).toBe(0) // 未新增重复行
    expect(state.costRows).toHaveLength(1)
  })

  it('保留权益法行不动', () => {
    const state = emptyState()
    state.equityRows.push(createG7EquityRow(1, '合营丙', 'joint_venture'))
    mergeAuxRowsIntoDetail(state, [{ investeeName: '子公司甲', openingAmount: 100 }], { overwrite: false })
    expect(state.equityRows).toHaveLength(1)
    expect(state.equityRows[0].investeeName).toBe('合营丙')
  })
})
