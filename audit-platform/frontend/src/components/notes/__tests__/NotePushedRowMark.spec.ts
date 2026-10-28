/**
 * 集团下推行在子企业附注编辑器里（spec note-pull-followup-closure R14）：固定行行名只读 + 锁；可选行「本企业不适用」开关。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it } from 'vitest'
import NotePushedRowMark from '../NotePushedRowMark.vue'
import { isPushedFixedRow } from '@/composables/useNoteTableStructure'
import { applyProjectedRowFlag, NoteTableWritebackError } from '@/views/composables/noteTableWriteback'

const fixed = { label: '库存现金', _pushed_row_id: 'r1', _pushed_category: 'required' }
const optional = { label: '数字货币', _pushed_row_id: 'r2', _pushed_category: 'optional', _pushed_optional_active: true }

function render(row: any, editable: boolean) {
  return mount(NotePushedRowMark, { props: { row, editable }, global: { plugins: [ElementPlus] } })
}

describe('NotePushedRowMark', () => {
  it('固定行显示锁；可选行编辑时可勾「本企业不适用」，查看时只在不适用时标出；普通行什么都不显示', async () => {
    expect(render(fixed, true).find('[data-testid="note-pushed-fixed"]').exists()).toBe(true)
    const w = render(optional, true)
    const box = w.find('[data-testid="note-pushed-optional"] input')
    expect(box.exists()).toBe(true)
    await box.setValue(true)
    expect(w.emitted('toggle')?.[0]).toEqual([false])
    expect(render(optional, false).text()).toBe('')
    expect(render({ ...optional, _pushed_optional_active: false }, false).text()).toContain('本企业不适用')
    expect(render({ label: '自加行' }, true).html()).not.toContain('gt-pushed')
  })

  it('类别缺省按固定行算（与后端保存校验同口径）', () => {
    expect(isPushedFixedRow({ _pushed_row_id: 'r' })).toBe(true)
    expect(isPushedFixedRow(optional)).toBe(false)
    expect(isPushedFixedRow({ _pushed_category: 'required' })).toBe(false)
  })
})

describe('applyProjectedRowFlag', () => {
  const raw = () => ({
    _tables: [{ name: '货币资金', headers: ['项目', '期末'], rows: [{ ...fixed }, { ...optional }] as Array<Record<string, unknown>> }],
  })
  const projected = {
    rows: [{ ...fixed }, { ...optional }],
    _sourceLabelRefs: [{ tableIndex: 0, rowIndex: 0 }, { tableIndex: 0, rowIndex: 1 }],
  }

  it('按标签源坐标写进 raw 的那一行，原对象不动', () => {
    const before = raw()
    const out = applyProjectedRowFlag(before, projected, 1, '_pushed_optional_active', false)
    expect(out._tables[0].rows[1]._pushed_optional_active).toBe(false)
    expect(before._tables[0].rows[1]._pushed_optional_active).toBe(true)
  })

  it('底稿来源（子表投影）的行拒绝写入', () => {
    const sub = { rows: [{ label: '甲' }], _sourceLabelRefs: [{ tableIndex: 0, rowIndex: 0, sourceSubTableKey: '主表' }] }
    expect(() => applyProjectedRowFlag({ sub_table_data: { 主表: [{ label: '甲' }] } }, sub, 0, '_pushed_optional_active', false))
      .toThrow(NoteTableWritebackError)
  })
})

describe('接线：附注编辑器', () => {
  const editor = readFileSync(resolve(__dirname, '../../../views/DisclosureEditor.vue'), 'utf-8')

  it('固定行不进行名编辑分支；标记挂在行名格；开关写 _pushed_optional_active', () => {
    expect(editor).toContain('<template v-if="editMode && !row.is_total && !isPushedFixedRow(row)">')
    expect(editor.match(/<NotePushedRowMark :row="row" :editable="editMode" @toggle="onPushedOptionalToggle\(\$index, \$event\)" \/>/g)?.length).toBe(1)
    const fn = editor.slice(editor.indexOf('function onPushedOptionalToggle('), editor.indexOf('function commitProjectedCellValue('))
    expect(fn).toContain("applyProjectedRowFlag(")
    expect(fn).toContain("'_pushed_optional_active', active)")
    expect(fn).toContain('autoSave.markDirty()')
  })
})
