/**
 * R3 守卫：投影反写补充场景
 *
 * Spec: disclosure-multitable-refresh-and-edit-writeback Task 4 (R3)
 *
 * 覆盖：
 * - 纯 _tables 多表（非 workpaper）反写正确原表
 * - legacy 单表（无 _tables）反写
 * - null/0 保留
 * - 保存 prepare 对纯 _tables 多表的幂等反写
 * - sourceKeysForProjectedTable 导出源集合
 */
import { describe, expect, it } from 'vitest'
import {
  applyProjectedCell,
  applyProjectedLabel,
  NoteTableWritebackError,
  prepareNoteTableData,
  sourceKeysForProjectedTable,
} from '../noteTableWriteback'

/** 纯 binding 多表数据（非 workpaper，_source 不是 workpaper） */
function bindingMultiTableData() {
  return {
    headers: ['项目', '期末余额'],
    rows: [{ label: '首表行1', values: [100] }],
    name: '表A',
    _tables: [
      {
        name: '表A',
        headers: ['项目', '期末余额'],
        rows: [{ label: '首表行1', values: [100] }],
      },
      {
        name: '表B',
        headers: ['项目', '本期发生额'],
        rows: [
          { label: '行B1', values: [200] },
          { label: '合计', values: [200], is_total: true },
        ],
      },
      {
        name: '表C',
        headers: ['项目', '金额'],
        rows: [{ label: '行C1', values: [300] }],
      },
    ],
  }
}

function enrichTable(table: any, tableIndex: number) {
  const rows = Array.isArray(table.rows) ? table.rows : []
  const valueCount = Math.max(0, (table.headers?.length || 0) - 1)
  return {
    ...table,
    _sourceTableIndexes: [tableIndex],
    _sourceTableKeys: [],
    _sourceRowRefs: rows.map((_: any, ri: number) => [{ tableIndex, rowIndex: ri }]),
    _sourceLabelRefs: rows.map((_: any, ri: number) => ({ tableIndex, rowIndex: ri })),
    _sourceColumnRefs: Array.from({ length: valueCount }, (_, vi) => ({ tableIndex, valueIndex: vi })),
    _sourceCellRefs: rows.map((_: any, ri: number) =>
      Array.from({ length: valueCount }, (_, vi) => ({
        row: { tableIndex, rowIndex: ri },
        column: { tableIndex, valueIndex: vi },
      })),
    ),
  }
}

describe('R3: 纯 _tables 多表反写', () => {
  it('写回非首表 _tables[2] 不影响首表', () => {
    const data = bindingMultiTableData()
    const table2 = enrichTable(data._tables[2], 2)
    const updated = applyProjectedCell(data, table2, 0, 0, 999)

    expect(updated._tables[2].rows[0].values[0]).toBe(999)
    expect(updated._tables[0].rows[0].values[0]).toBe(100)
    expect(updated._tables[1].rows[0].values[0]).toBe(200)
  })

  it('写回首表 _tables[0] 不影响其他表', () => {
    const data = bindingMultiTableData()
    const table0 = enrichTable(data._tables[0], 0)
    const updated = applyProjectedCell(data, table0, 0, 0, 0)

    expect(updated._tables[0].rows[0].values[0]).toBe(0)
    expect(updated._tables[1].rows[0].values[0]).toBe(200)
  })

  it('标签反写到正确源表', () => {
    const data = bindingMultiTableData()
    const table1 = enrichTable(data._tables[1], 1)
    const updated = applyProjectedLabel(data, table1, 0, '新标签')

    expect(updated._tables[1].rows[0].label).toBe('新标签')
    expect(updated._tables[0].rows[0].label).toBe('首表行1')
  })
})

describe('R3: legacy 单表反写', () => {
  it('无 _tables 时写回顶层 rows', () => {
    const data = {
      headers: ['项目', '金额'],
      rows: [{ label: '行1', values: [50] }],
    }
    const table = enrichTable(data, 0)
    const updated = applyProjectedCell(data, table, 0, 0, 77)

    expect(updated.rows[0].values[0]).toBe(77)
  })
})

describe('R3: null / 0 保留', () => {
  it.each([null, 0, -1, ''])('_tables 反写保留 %p', (value) => {
    const data = bindingMultiTableData()
    const table1 = enrichTable(data._tables[1], 1)
    const updated = applyProjectedCell(data, table1, 0, 0, value)

    expect(updated._tables[1].rows[0].values[0]).toBe(value)
  })
})

describe('R3: prepareNoteTableData 对纯 _tables 多表', () => {
  it('多表投影编辑幂等反写', () => {
    const data = bindingMultiTableData()
    const projected = data._tables.map((t: any, i: number) => enrichTable(t, i))
    // 模拟编辑
    projected[1].rows[0].values[0] = 999
    projected[2].rows[0].label = '改过的C'

    const prepared = prepareNoteTableData(data, projected)!
    expect(prepared._tables[1].rows[0].values[0]).toBe(999)
    expect(prepared._tables[2].rows[0].label).toBe('改过的C')
    // 未编辑的保持原值
    expect(prepared._tables[0].rows[0].values[0]).toBe(100)
    // 非 workpaper 保留 _tables
    expect(prepared._tables).toBeDefined()
  })

  it('幂等：相同编辑反写两次结果一致', () => {
    const data = bindingMultiTableData()
    const projected = data._tables.map((t: any, i: number) => enrichTable(t, i))
    projected[1].rows[0].values[0] = 42

    const first = prepareNoteTableData(data, projected)!
    const second = prepareNoteTableData(data, projected)!
    expect(JSON.stringify(first)).toBe(JSON.stringify(second))
  })
})

describe('R3: sourceKeysForProjectedTable', () => {
  it('有 _sourceTableKeys 时返回', () => {
    const table = { _sourceTableKeys: ['首表', '续表'] }
    expect(sourceKeysForProjectedTable(table)).toEqual(['首表', '续表'])
  })

  it('有 _source_sub_table_key 时返回单元素', () => {
    const table = { _source_sub_table_key: '次表' }
    expect(sourceKeysForProjectedTable(table)).toEqual(['次表'])
  })

  it('无 key 返回空数组', () => {
    expect(sourceKeysForProjectedTable({})).toEqual([])
    expect(sourceKeysForProjectedTable(null)).toEqual([])
  })
})
