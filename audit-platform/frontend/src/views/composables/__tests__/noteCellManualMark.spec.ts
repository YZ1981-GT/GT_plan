/**
 * 附注编辑器：用户改了数值的格标人工、可恢复自动（spec note-pull-followup-closure R5 / ADR-5「没有绑定 ≠ 人工」）。
 *
 * 生成不再把没有绑定的格标 manual（后端 `_cell_meta.unbound`）；人工只来自编辑器：用户改的这一格写 `_cell_modes[列]='manual'`
 * （推送 / 公式 / 刷新不覆盖），合计与横向公式等派生写入不标；点 ✏️ 恢复自动。底稿来源（子表投影）的格没有这类标记。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { applyProjectedCell, applyProjectedCellAuto, NoteTableWritebackError } from '../noteTableWriteback'
import { projectSubTablesClient } from '@/components/workpaper/composables/disclosureColumnDefs'
import { useNoteTableProjection } from '../useNoteTableProjection'

function data() {
  return {
    _tables: [{
      name: '货币资金', headers: ['项目', '期末余额', '期初余额'],
      rows: [{
        label: '银行存款', values: [null, null], _cell_modes: { 0: 'auto' },
        _cell_meta: { 0: { semantic: 'closing_balance' }, 1: { semantic: 'opening_balance', unbound: true } },
      }],
    }],
  }
}

function projected(table: any, tableIndex = 0) {
  const rows = table.rows
  return {
    ...table,
    _sourceCellRefs: rows.map((_: any, ri: number) => [0, 1].map(vi => ({
      row: { tableIndex, rowIndex: ri }, column: { tableIndex, valueIndex: vi } }))),
  }
}

describe('applyProjectedCell markManual', () => {
  it('用户改的格标人工，原对象不动；不带选项（派生写入）不标', () => {
    const raw = data()
    const out = applyProjectedCell(raw, projected(raw._tables[0]), 0, 1, 7, { markManual: true })
    expect(out._tables[0].rows[0].values).toEqual([null, 7])
    expect(out._tables[0].rows[0]._cell_modes).toEqual({ 0: 'auto', 1: 'manual' })
    expect(raw._tables[0].rows[0]._cell_modes).toEqual({ 0: 'auto' })
    const derived = applyProjectedCell(raw, projected(raw._tables[0]), 0, 0, 3)
    expect(derived._tables[0].rows[0]._cell_modes).toEqual({ 0: 'auto' })
  })

  it('恢复自动：有绑定的格记 auto，没有绑定的格去掉模式', () => {
    let raw: any = data()
    raw = applyProjectedCell(raw, projected(raw._tables[0]), 0, 0, 5, { markManual: true })
    raw = applyProjectedCell(raw, projected(raw._tables[0]), 0, 1, 6, { markManual: true })
    expect(raw._tables[0].rows[0]._cell_modes).toEqual({ 0: 'manual', 1: 'manual' })
    raw = applyProjectedCellAuto(raw, projected(raw._tables[0]), 0, 0)
    raw = applyProjectedCellAuto(raw, projected(raw._tables[0]), 0, 1)
    expect(raw._tables[0].rows[0]._cell_modes).toEqual({ 0: 'auto' })
    // 恢复自动不清值，等下次推送 / 公式 / 刷新写入
    expect(raw._tables[0].rows[0].values).toEqual([5, 6])
  })

  it('底稿来源（子表投影）的格不写人工标记；恢复自动拒绝', () => {
    const raw = { _source: 'workpaper', sub_table_data: { 主表: [{ label: '甲', amount: 1 }] },
      _sub_table_columns: { 主表: [{ key: 'label', label: '项目', is_label: true }, { key: 'amount', label: '金额' }] } }
    const table = projectSubTablesClient(raw)![0]
    const out = applyProjectedCell(raw, table, 0, 0, 9, { markManual: true })
    expect(out.sub_table_data.主表[0]).toEqual({ label: '甲', amount: 9 })
    expect(() => applyProjectedCellAuto(raw, table, 0, 0)).toThrow(NoteTableWritebackError)
  })
})

describe('期间并列 / 续表合并后的列也带模式标记', () => {
  it('右侧表的 _cell_modes / _cell_meta 按列平移到合成表，源数据不动', () => {
    const left = { name: '左', headers: ['项目', '期末'], rows: [{ label: '甲', values: [1], _cell_modes: { 0: 'auto' } }] }
    const right = { name: '左（续）', headers: ['项目', '期初'],
      rows: [{ label: '甲', values: [2], _cell_modes: { 0: 'manual' }, _cell_meta: { 0: { unbound: true } } }] }
    const { currentNoteTables } = useNoteTableProjection({
      currentNote: ref({ table_data: { _tables: [left, right] } }),
      projectSubTablesClient: () => null,
      deriveLegacyTableHeaders: () => null,
    })
    const [merged] = currentNoteTables.value
    expect(merged.headers).toEqual(['项目', '期末', '期初'])
    expect(merged.rows[0]._cell_modes).toEqual({ 0: 'auto', 1: 'manual' })
    expect(merged.rows[0]._cell_meta).toEqual({ 1: { unbound: true } })
    expect(left.rows[0]._cell_modes).toEqual({ 0: 'auto' })
  })
})

describe('接线：附注编辑器', () => {
  const editor = readFileSync(resolve(__dirname, '../../DisclosureEditor.vue'), 'utf-8')

  it('只有用户改的那一格带 markManual；✏️ 只在编辑态点了恢复自动', () => {
    const fn = editor.slice(editor.indexOf('function onCellValueChange('), editor.indexOf('function recalcHorizontalFormula('))
    expect(fn.match(/commitProjectedCellValue\(/g)?.length).toBe(3)
    expect(fn.match(/\{ markManual: true \}/g)?.length).toBe(1)
    expect(fn).toContain('commitProjectedCellValue(table, rowIndex, colIndex, newValue, { markManual: true })')
    // 选项原样传到写入函数（否则用户改值照样不标人工）
    const commit = editor.slice(editor.indexOf('function commitProjectedCellValue('), editor.indexOf('function onRestoreCellAuto('))
    expect(commit).toMatch(/applyProjectedCell\(\s*currentNote\.value\.table_data,\s*table,\s*rowIndex,\s*colIndex,\s*value,\s*options,?\s*\)/)
    expect(editor).toContain('@click.stop="editMode && onRestoreCellAuto($index, headerIdx - 1)"')
    const restore = editor.slice(editor.indexOf('function onRestoreCellAuto('), editor.indexOf('function onCellValueChange('))
    expect(restore).toContain('applyProjectedCellAuto(')
    expect(restore).toContain('autoSave.markDirty()')
  })
})
