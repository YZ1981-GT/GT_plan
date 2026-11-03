/**
 * 保存前反写：workpaper 来源但没有子表数据时，`_tables` 是存下来的数据，不是读时投影（spec note-pull-followup-closure 浏览器实测）。
 *
 * 公式推送对旧格式附注兜底写 `_tables` 并把 `_source` 标成 workpaper（真库和平 / 宜宾 / 重药安徽共 117 个章节是这种形态）。
 * 原来 `prepareNoteTableData` 对 workpaper 来源一律剥掉 `_tables` ⇒ 在编辑器里保存一次，首表以外的表整张消失、
 * 这次在 `_tables` 上的编辑也丢了（【测试】甲 五、1 保存后「受限制的货币资金明细」没了、改的 101 回到 100）。
 * 判据与后端 GET 同口径：子表数据能投影出表（投影非空）才剥 `_tables`。
 */
import { describe, expect, it } from 'vitest'
import { projectSubTablesClient } from '@/components/workpaper/composables/disclosureColumnDefs'
import { applyProjectedCell, prepareNoteTableData } from '../noteTableWriteback'

function row(label: string, values: Array<number | null>, extra: Record<string, unknown> = {}) {
  return { label, values, _cell_modes: { 0: 'auto', 1: 'auto' }, ...extra }
}

/** 与【测试】甲 五、1 同形：顶层是首表镜像，`_tables` 两张表，没有 sub_table_data */
function pushedLegacyNote(extra: Record<string, unknown> = {}) {
  const cash = [row('库存现金', [100, 0]), row('银行存款', [200, 0]), row('合计', [300, 0], { is_total: true })]
  return {
    name: '货币资金',
    rows: cash.map((r) => ({ ...r, values: [...r.values] })),
    headers: ['项目', '期末余额', '上年年末余额'],
    _source: 'workpaper',
    _last_sync_wp_id: 'wp-e1',
    _tables: [
      { name: '货币资金', headers: ['项目', '期末余额', '上年年末余额'], rows: cash },
      {
        name: '受限制的货币资金明细',
        headers: ['项目', '期末余额', '上年年末余额'],
        rows: [row('银行承兑汇票保证金', [350, 0]), row('合计', [350, 0], { is_total: true })],
      },
    ],
    ...extra,
  }
}

/** 编辑器对 `_tables` 的投影（源坐标指回 `_tables[i]`，与 useNoteTableProjection 第一层同形） */
function projected(table: any, tableIndex: number) {
  const valueCount = table.headers.length - 1
  return {
    ...table,
    rows: table.rows.map((r: any) => ({ ...r, values: [...r.values] })),
    _sourceRowRefs: table.rows.map((_: any, ri: number) => [{ tableIndex, rowIndex: ri }]),
    _sourceLabelRefs: table.rows.map((_: any, ri: number) => ({ tableIndex, rowIndex: ri })),
    _sourceColumnRefs: Array.from({ length: valueCount }, (_, vi) => ({ tableIndex, valueIndex: vi })),
    _sourceCellRefs: table.rows.map((_: any, ri: number) => Array.from({ length: valueCount }, (_, vi) => ({
      row: { tableIndex, rowIndex: ri }, column: { tableIndex, valueIndex: vi },
    }))),
  }
}

describe('workpaper 来源但没有子表数据：保存保留 `_tables`', () => {
  it('两张表都保留，首表与次表的编辑都写进去', () => {
    const note = pushedLegacyNote()
    const tables = note._tables.map((t, i) => projected(t, i))
    tables[0].rows[0].values[0] = 101
    tables[1].rows[0].values[0] = 360

    const prepared = prepareNoteTableData(note, tables)!
    expect(prepared._tables.map((t: any) => t.name)).toEqual(['货币资金', '受限制的货币资金明细'])
    expect(prepared._tables[0].rows[0].values).toEqual([101, 0])
    expect(prepared._tables[1].rows[0].values).toEqual([360, 0])
    expect(note._tables[0].rows[0].values[0]).toBe(100)  // 不改入参
  })

  it('编辑器改值标的人工标记随 `_tables` 一起保存（R5 ✏️）', () => {
    const note = pushedLegacyNote()
    const table = projected(note._tables[0], 0)
    const edited = applyProjectedCell(note, table, 0, 0, 101, { markManual: true })
    table.rows[0].values[0] = 101

    const prepared = prepareNoteTableData(edited, [table, projected(note._tables[1], 1)])!
    expect(prepared._tables[0].rows[0]).toMatchObject({ values: [101, 0], _cell_modes: { 0: 'manual', 1: 'auto' } })
  })

  it.each([
    ['sub_table_data 为空对象', { sub_table_data: {} }],
    ['sub_table_data 只有元数据键', { sub_table_data: { _manual_override: true } }],
  ])('%s：投影为空 ⇒ `_tables` 仍是存下来的数据', (_name, extra) => {
    const note = pushedLegacyNote(extra)
    expect(projectSubTablesClient(note)).toEqual([])
    const prepared = prepareNoteTableData(note, note._tables.map((t, i) => projected(t, i)))!
    expect(prepared._tables).toHaveLength(2)
  })

  it('对照：有子表数据时 `_tables` 是投影，照旧剥掉、编辑写回 sub_table_data', () => {
    const note = {
      _source: 'workpaper',
      _tables: [{ name: '旧投影', headers: ['项目', '金额'], rows: [{ label: '旧', values: [999] }] }],
      sub_table_data: { 首表: [{ label: '甲', amount: 1 }] },
      _sub_table_columns: { 首表: [{ key: 'label', label: '项目', is_label: true }, { key: 'amount', label: '金额' }] },
    }
    const tables = projectSubTablesClient(note)!
    tables[0].rows[0].values[0] = 5

    const prepared = prepareNoteTableData(note, tables)!
    expect(prepared._tables).toBeUndefined()
    expect(prepared.sub_table_data.首表[0].amount).toBe(5)
  })
})
