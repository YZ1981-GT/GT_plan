/**
 * spec excel-style-table-editing ADR-3：分组表头（多级 el-table-column）下的叶子列同样进坐标。
 *
 * 分组表头下叶子列的列 id 是「父 id + _column_n」（`el-table_1_column_3_column_4`）；原先列 id 正则只认
 * `el-table_1_column_3` ⇒ 分组下的格不在坐标里：单击选不中、双击打不开，Excel 方式下整列改不了
 * （试算平衡表「审计调整 / 重分类调整」借贷列实测）。
 */
import { afterEach, describe, expect, it } from 'vitest'
import { activeInput, cell, click, dblclick, key, mountGrid, settle, sink, unmountAll } from './gridHarness'

afterEach(() => unmountAll())

const TABLE = `
<el-table :data="rows">
  <el-table-column label="项目" prop="name" />
  <el-table-column label="重分类调整">
    <el-table-column label="借方"><template #default="{ row }"><el-input v-model="row.dr" /></template></el-table-column>
    <el-table-column label="贷方"><template #default="{ row }"><el-input v-model="row.cr" /></template></el-table-column>
  </el-table-column>
  <el-table-column label="审定数" prop="audited" />
</el-table>`

const rows = () => [
  { name: '货币资金', dr: '10', cr: '', audited: 1 },
  { name: '应收账款', dr: '', cr: '5', audited: 2 },
]

describe('分组表头下的叶子列', () => {
  it('单击选中分组下的格；方向键在顶层列与分组列之间连续移动', async () => {
    const w = await mountGrid(TABLE, () => ({ rows: rows() }))
    click(cell(w, 0, 1))
    await settle()
    expect(cell(w, 0, 1).hasAttribute('data-gt-active')).toBe(true)
    key(sink(w), 'ArrowRight')
    expect(cell(w, 0, 2).hasAttribute('data-gt-active')).toBe(true)
    key(sink(w), 'ArrowRight')
    expect(cell(w, 0, 3).hasAttribute('data-gt-active')).toBe(true)
    key(sink(w), 'ArrowLeft')
    key(sink(w), 'ArrowLeft')
    key(sink(w), 'ArrowLeft')
    expect(cell(w, 0, 0).hasAttribute('data-gt-active')).toBe(true)
  })

  it('双击分组下的可编辑格进入编辑，回车提交写回', async () => {
    const w = await mountGrid(TABLE, () => ({ rows: rows() }))
    const data = (w.vm as unknown as { rows: ReturnType<typeof rows> }).rows
    click(cell(w, 1, 1))
    dblclick(cell(w, 1, 1))
    await settle()
    const input = activeInput(w)
    expect(input.value).toBe('')
    input.value = '30'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    key(input, 'Enter')
    await settle()
    expect(data[1].dr).toBe('30')
    expect(w.element.querySelector('td[data-gt-editing]')).toBeNull()
  })
})
