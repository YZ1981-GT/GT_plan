/**
 * 一格多控件（spec excel-style-table-editing 5.6 补）。
 *
 * 原状（可打红）：内核一格只开一个编辑器（第一个输入类），平时各控件都显示成文字 ——
 * 起止日期的「止」、金额 + 说明的「说明」、下拉 + 条件说明的「说明」在 Excel / 单击编辑方式下永远打不开
 * （现扫 13 个文件 16 格，如 H1 闲置检查起止时间、G12 头寸、凭证抽样未检查处置）。
 * 现在：同一格里两个及以上输入类控件 ⇒ 都按普通控件常驻显示，点哪个就在哪个里输入；格子照常可选中；
 * 只有一个输入类控件的格不受影响；勾选 / 开关不计数；条件控件出现 / 消失时随之切换。
 */
import { afterEach, describe, expect, it } from 'vitest'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { cell, dblclick, kernelOf, mountGrid, mousedown, settle, sink, typeInSink, unmountAll } from './gridHarness'

afterEach(() => {
  unmountAll()
  useDisplayPrefsStore().gridEditMode = 'excel'
})

const rows = () => [
  { name: '甲', start: '2025-01-01', end: '2025-06-30', desc: '外币收入', amount: '100', mode: 'a', note: '' },
  { name: '乙', start: '', end: '', desc: '', amount: '', mode: 'b', note: '' },
]

const TABLE = `
<el-table :data="rows">
  <el-table-column label="名称" prop="name"><template #default="{ row }"><el-input v-model="row.name" @change="onChange('name', $event)" /></template></el-table-column>
  <el-table-column label="期间"><template #default="{ row }">
    <el-input v-model="row.start" class="t-start" @change="onChange('start', $event)" />
    <el-input v-model="row.end" class="t-end" @change="onChange('end', $event)" />
  </template></el-table-column>
  <el-table-column label="处置"><template #default="{ row }">
    <el-select v-model="row.mode" class="t-mode"><el-option label="甲方式" value="a" /><el-option label="乙方式" value="b" /></el-select>
    <el-input v-if="row.mode === 'b'" v-model="row.note" class="t-note" />
  </template></el-table-column>
  <el-table-column label="手工"><template #default="{ row }">
    <el-checkbox v-model="row.manual" class="t-manual" />
    <el-input v-model="row.desc" class="t-desc" />
  </template></el-table-column>
</el-table>`

async function mountTable() {
  const changes: Array<[string, unknown]> = []
  const w = await mountGrid(TABLE, () => ({ rows: rows() }), { onChange: (f: never, v: never) => { changes.push([f, v]) } })
  return { w, changes }
}

describe('一格多控件：都按普通控件常驻', () => {
  it('两个输入框的格常驻真实输入框，不登记为单元格编辑器；单控件格照常显示文字', async () => {
    const { w } = await mountTable()
    const period = cell(w, 0, 1)
    expect(period.querySelectorAll('input').length).toBe(2)
    expect(period.querySelector('[data-gt-cell-editor]')).toBeNull()
    expect(period.querySelector('.gt-cell-display')).toBeNull()
    // 单控件格：平时文字，没有输入框
    const name = cell(w, 0, 0)
    expect(name.querySelector('input')).toBeNull()
    expect(name.querySelector('.gt-cell-display')?.textContent).toBe('甲')
  })

  it('点第二个控件直接在里面输入，提交照常发 change；格子仍被选中', async () => {
    const { w, changes } = await mountTable()
    const end = cell(w, 0, 1).querySelector('.t-end input') as HTMLInputElement
    const down = mousedown(end)
    end.focus()
    await settle()
    // 点在控件上：内核只选中格子、不拦默认行为（焦点留在控件里）
    expect(down.defaultPrevented).toBe(false)
    expect(document.activeElement).toBe(end)
    expect(cell(w, 0, 1).hasAttribute('data-gt-active')).toBe(true)
    end.value = '2025-12-31'
    end.dispatchEvent(new Event('input', { bubbles: true }))
    end.dispatchEvent(new Event('change', { bubbles: true }))
    await settle()
    expect((w.vm as unknown as { rows: Array<{ end: string }> }).rows[0].end).toBe('2025-12-31')
    expect(changes).toContainEqual(['end', '2025-12-31'])
  })

  it('双击多控件格不开编辑器（内核按只读格放行），直接打字也不写进任何控件', async () => {
    const { w } = await mountTable()
    const period = cell(w, 1, 1)
    mousedown(period)
    const ev = dblclick(period)
    await settle()
    expect(ev.defaultPrevented).toBe(false)
    expect(w.element.querySelector('td[data-gt-editing]')).toBeNull()
    typeInSink(sink(w), 'x')
    await settle()
    expect((w.vm as unknown as { rows: Array<{ start: string; end: string }> }).rows[1]).toMatchObject({ start: '', end: '' })
  })

  it('条件控件出现 / 消失时切换：只剩一个输入类控件就回到「平时文字、双击编辑」', async () => {
    const { w } = await mountTable()
    const vm = w.vm as unknown as { rows: Array<{ mode: string }> }
    // 第 1 行 mode=b：下拉 + 说明两个控件 ⇒ 常驻
    expect(cell(w, 1, 2).querySelectorAll('input').length).toBeGreaterThanOrEqual(2)
    // 第 0 行 mode=a：只有下拉 ⇒ 显示文字
    expect(cell(w, 0, 2).querySelector('.gt-cell-display')?.textContent).toBe('甲方式')
    vm.rows[0].mode = 'b'
    await settle()
    expect(cell(w, 0, 2).querySelector('.gt-cell-display')).toBeNull()
    expect(cell(w, 0, 2).querySelector('.t-note input')).not.toBeNull()
    vm.rows[0].mode = 'a'
    await settle()
    expect(cell(w, 0, 2).querySelector('.gt-cell-display')?.textContent).toBe('甲方式')
    expect(cell(w, 0, 2).querySelector('[data-gt-cell-editor]')).not.toBeNull()
  })

  it('勾选不计数：勾选 + 一个输入框的格，输入框照常是单元格编辑器（双击打开）', async () => {
    const { w } = await mountTable()
    const c = cell(w, 0, 3)
    expect(c.querySelector('.t-manual')).not.toBeNull()
    expect(c.querySelector('.gt-cell-display--text')?.textContent).toBe('外币收入')
    mousedown(c)
    dblclick(c)
    await settle()
    expect(w.element.querySelector('td[data-gt-editing] .t-desc input')).not.toBeNull()
  })

  it('复制 / 统计取的格文字含常驻输入框里的值（innerText 不含输入框的字）', async () => {
    const { w } = await mountTable()
    const k = kernelOf(w)
    expect(k.cellText(cell(w, 0, 1))).toBe('2025-01-01 2025-06-30')
    // 下拉的输入框只用于过滤：取选中项文字，不取输入框（过滤中打的字不算格的内容）
    const filter = cell(w, 1, 2).querySelector('.el-select input') as HTMLInputElement
    filter.value = '乙'
    expect(k.cellText(cell(w, 1, 2))).toBe('乙方式')
    // 单控件格照旧取编辑器的显示文字
    expect(k.cellText(cell(w, 0, 0))).toBe('甲')
  })

  it('经典方式不受影响（本来就常驻）', async () => {
    useDisplayPrefsStore().gridEditMode = 'classic'
    const { w } = await mountTable()
    expect(cell(w, 0, 0).querySelector('input')).not.toBeNull()
    expect(cell(w, 0, 1).querySelectorAll('input').length).toBe(2)
  })

  it('原生表格（GtGridTable）同样按格判定', async () => {
    const w = await mountGrid(`
<gt-grid-table><tbody>
  <tr><td><el-input v-model="a" class="t-a" /></td><td><el-input v-model="b" class="t-b" /><el-input v-model="c" class="t-c" /></td></tr>
</tbody></gt-grid-table>`, () => ({ a: '1', b: '2', c: '3' }))
    const tds = w.element.querySelectorAll('tbody td')
    expect(tds[0].querySelector('input')).toBeNull()
    expect(tds[0].querySelector('.gt-cell-display')?.textContent).toBe('1')
    expect(tds[1].querySelectorAll('input').length).toBe(2)
    expect(tds[1].querySelector('[data-gt-cell-editor]')).toBeNull()
  })
})
