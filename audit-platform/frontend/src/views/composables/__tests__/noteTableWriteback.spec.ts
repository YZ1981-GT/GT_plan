import { describe, expect, it } from 'vitest'
import { projectSubTablesClient } from '@/components/workpaper/composables/disclosureColumnDefs'
import {
  applyProjectedCell,
  applyProjectedLabel,
  NoteTableWritebackError,
  prepareNoteTableData,
} from '../noteTableWriteback'

function workpaperData() {
  return {
    _source: 'workpaper',
    _tables: [{ name: '旧投影', headers: ['项目', '金额'], rows: [{ label: '旧', values: [999] }] }],
    sub_table_data: {
      首表: [{ label: '甲', amount: 1 }],
      次表: [{ label: '乙', amount: 2 }],
    },
    _sub_table_columns: {
      首表: [
        { key: 'label', label: '项目', is_label: true },
        { key: 'amount', label: '金额' },
      ],
      次表: [
        { key: 'label', label: '项目', is_label: true },
        { key: 'amount', label: '金额' },
      ],
    },
  }
}

describe('noteTableWriteback', () => {
  it('按非首表 sourceSubTableKey 写回，不串到首表', () => {
    const original = workpaperData()
    const tables = projectSubTablesClient(original)!
    const updated = applyProjectedCell(original, tables[1], 0, 0, 0)

    expect(updated.sub_table_data.首表[0].amount).toBe(1)
    expect(updated.sub_table_data.次表[0].amount).toBe(0)
    expect(updated._tables[0].rows[0].values[0]).toBe(999)
  })

  it('标签按同一投影行写回对应业务键', () => {
    const original = workpaperData()
    const table = projectSubTablesClient(original)![1]
    const updated = applyProjectedLabel(original, table, 0, '')

    expect(updated.sub_table_data.首表[0].label).toBe('甲')
    expect(updated.sub_table_data.次表[0].label).toBe('')
  })

  it.each([null, 0, ''])('保留编辑值 %p，不按 falsy 丢弃', (value) => {
    const original = workpaperData()
    const table = projectSubTablesClient(original)![1]
    const updated = applyProjectedCell(original, table, 0, 0, value)

    expect(updated.sub_table_data.次表[0].amount).toBe(value)
  })

  it('过滤 expandable 行后仍写回过滤前的真实 raw 行下标', () => {
    const original = {
      _source: 'workpaper',
      sub_table_data: {
        次表: [
          { row_type: 'expandable', label: '可添加行', amount: 777 },
          { label: '真实行', amount: 2 },
        ],
      },
      _sub_table_columns: {
        次表: [
          { key: 'label', label: '项目', is_label: true },
          { key: 'amount', label: '金额' },
        ],
      },
    }
    const table = projectSubTablesClient(original)![0]
    expect(table._source_row_indexes).toEqual([1])

    const updated = applyProjectedCell(original, table, 0, 0, 3)
    expect(updated.sub_table_data.次表[0].amount).toBe(777)
    expect(updated.sub_table_data.次表[1].amount).toBe(3)
  })

  it('支持 { rows: [...] } 包装并按业务键写回', () => {
    const original = {
      _source: 'workpaper_html',
      sub_table_data: {
        次表: { rows: [{ label: '乙', amount: 2 }] },
      },
      _sub_table_columns: {
        次表: [
          { key: 'label', label: '项目', is_label: true },
          { key: 'amount', label: '金额' },
        ],
      },
    }
    const table = projectSubTablesClient(original)![0]
    const updated = applyProjectedCell(original, table, 0, 0, 8)

    expect(updated.sub_table_data.次表.rows[0].amount).toBe(8)
  })

  it('保存前把投影编辑提交回 raw，并移除 workpaper _tables', () => {
    const original = workpaperData()
    const tables = projectSubTablesClient(original)!
    tables[1].rows[0].label = '乙（已改）'
    tables[1].rows[0].values[0] = 0

    const prepared = prepareNoteTableData(original, tables)!
    expect(prepared._tables).toBeUndefined()
    expect(prepared.sub_table_data.次表[0]).toMatchObject({ label: '乙（已改）', amount: 0 })
    expect(prepared.sub_table_data.首表[0]).toMatchObject({ label: '甲', amount: 1 })
  })

  it('投影缺少源坐标时拒绝写入，不猜首表', () => {
    const original = workpaperData()
    const table = { name: '无坐标', headers: ['项目', '金额'], rows: [{ label: '乙', values: [2] }] }

    expect(() => applyProjectedCell(original, table, 0, 0, 9)).toThrow(NoteTableWritebackError)
    expect(() => prepareNoteTableData(original, [table])).toThrow(NoteTableWritebackError)
    expect(original.sub_table_data.首表[0].amount).toBe(1)
  })
})
