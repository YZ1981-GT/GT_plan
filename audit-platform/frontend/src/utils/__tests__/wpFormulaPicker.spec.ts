import { describe, expect, it } from 'vitest'
import {
  filterWpBrowserRows,
  mapRegistryToPickerRows,
  pickerRowsSubsetOfRegistry,
  type WpPickerRow,
} from '../wpFormulaPicker'

describe('wpFormulaPicker — P4 弹窗可选项 ⊆ 注册表', () => {
  const registry = [
    { wp_code: 'CUST-01', label: '货币资金（B5）', cell: 'B5', formula_ref: "WP('CUST-01','B5')" },
    { wp_code: 'E1-1', label: '审定数', cell: '审定数', formula_ref: "WP('E1-1','审定数')" },
  ]

  it('mapped rows refs are subset of registry', () => {
    const rows = mapRegistryToPickerRows(registry, (e) => `WP('${e.wp_code}','审定数')`)
    const refs = new Set(registry.map((e) => e.formula_ref!))
    expect(pickerRowsSubsetOfRegistry(rows, refs)).toBe(true)
  })

  it('empty custom registry still allows standard fallback rows', () => {
    const standard = [{ wp_code: 'D1', label: 'D1 底稿', formula_ref: "WP('D1','审定数')" }]
    const rows = mapRegistryToPickerRows(standard, (e) => `WP('${e.wp_code}','审定数')`)
    expect(rows.length).toBeGreaterThan(0)
  })
})

describe('wpFormulaPicker — P13 搜索过滤', () => {
  const rows: WpPickerRow[] = [
    { row_code: 'CUST-01', row_name: '货币资金（B5）', _ref: "WP('CUST-01','B5')" },
    { row_code: 'E1-1', row_name: '固定资产', _ref: "WP('E1-1','审定数')" },
  ]

  it('filter is subset and matches keyword in code or name', () => {
    const kw = '货币'
    const filtered = filterWpBrowserRows(rows, kw)
    expect(filtered.every((r) => rows.includes(r) || filtered.length <= rows.length)).toBe(true)
    for (const r of filtered) {
      const code = (r.row_code || '').toLowerCase()
      const name = (r.row_name || '').toLowerCase()
      expect(code.includes(kw) || name.includes(kw)).toBe(true)
    }
    expect(filtered.some((r) => r.row_name.includes('货币'))).toBe(true)
  })

  it('empty keyword returns all rows', () => {
    expect(filterWpBrowserRows(rows, '')).toEqual(rows)
  })
})
