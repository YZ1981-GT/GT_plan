/**
 * queryTemplateRestore.spec.ts — 模板 config → 查询界面状态（advanced-query-linkage-closure 任务 33；R9.4）
 */
import { describe, it, expect } from 'vitest'
import { QUERY_PAGE_SIZES, restoreTemplateQuery, templateSourceOf } from '../queryTemplateRestore'

describe('restoreTemplateQuery', () => {
  it('页面版模板：数据源取 data_source，条件兼容旧写法，列 / 排序 / 每页行数 / 取值目标都还原；年度项目不还原', () => {
    const r = restoreTemplateQuery({ data_source: 'ledger_entries', config: {
      project_id: 'p1', year: 2023, condition_logic: 'OR',
      conditions: [{ field: 'summary', operator: 'contains', value: '冲销' }, { field: 'voucher_date', op: 'between', value: ['2025-12-25', '2025-12-31'] }],
      selected_columns: ['voucher_no', 'summary'], available_columns: ['voucher_no', 'summary', 'debit_amount'],
      sort_field: 'voucher_date', sort_order: 'descending', page_size: 500, acnr_targets: ['E1/E1-14/C10'],
    } })
    expect(r).toEqual({
      source: 'ledger_entries',
      condition: { conditions: [{ field: 'summary', op: 'like', value: '冲销' },
        { field: 'voucher_date', op: 'between', value: '2025-12-25,2025-12-31' }], logic: 'or' },
      columns: ['voucher_no', 'summary'], availableColumns: ['voucher_no', 'summary', 'debit_amount'],
      sort: { field: 'voucher_date', direction: 'desc' }, pageSize: 500,
      cellRange: '', sheetName: '', filterText: '', acnrTargets: ['E1/E1-14/C10'],
    })
    expect(r).not.toHaveProperty('year')
    expect(r).not.toHaveProperty('projectId')
  })

  it('弹窗模板：config.source 优先，底稿选区 / 本页筛选还原；sort 数组取第一项', () => {
    const r = restoreTemplateQuery({ data_source: 'workpaper', config: {
      source: 'workpaper:E1|货币资金分析表E1-14', cell_range: 'C10:C11', sheet_name: '货币资金分析表E1-14',
      filter_text: '利息', sort: [{ field: 'value', direction: 'asc' }], limit: 200,
    } })!
    expect([r.source, r.cellRange, r.sheetName, r.filterText, r.pageSize]).toEqual(
      ['workpaper:E1|货币资金分析表E1-14', 'C10:C11', '货币资金分析表E1-14', '利息', 200])
    expect(r.sort).toEqual({ field: 'value', direction: 'asc' })
  })

  it('每页行数不在 100 / 200 / 500 里不还原；没有排序为 null；没有数据源为 null', () => {
    expect(QUERY_PAGE_SIZES).toEqual([100, 200, 500])
    expect(restoreTemplateQuery({ data_source: 'tb_detail', config: { page_size: 2000 } })!.pageSize).toBeNull()
    expect(restoreTemplateQuery({ data_source: 'tb_detail', config: null })!.sort).toBeNull()
    expect(restoreTemplateQuery({ data_source: '', config: {} })).toBeNull()
    expect(templateSourceOf({ data_source: ' adj_aje ', config: { source: '' } })).toBe('adj_aje')
  })
})
