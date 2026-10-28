/**
 * spec excel-style-table-editing R3 / R4 / R5 / R6 / R7 / R8 / R9：el-table 上的选中、编辑、提交 / 取消、
 * 复制粘贴、撤销与只读格（真实 el-table + 适配组件 + 全局 mixin）。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import {
  activeInput, cell, click, clipboardEvent, dblclick, key, mountGrid, mousedown, settle, sink, typeInSink, unmountAll,
} from './gridHarness'

afterEach(() => unmountAll())

const TABLE = `
<el-table :data="rows" @cell-dblclick="onDbl">
  <el-table-column label="名称"><template #default="{ row }"><el-input v-model="row.name" /></template></el-table-column>
  <el-table-column label="金额"><template #default="{ row }">
    <el-input-number :model-value="row.amt" :controls="false" :precision="2" @change="(v) => onAmt(row, v)" />
  </template></el-table-column>
  <el-table-column label="审定" prop="audited" />
  <el-table-column label="备注"><template #default="{ row }">
    <el-input :model-value="row.remark" @blur="(e) => onRemarkBlur(row, e.target.value)" />
  </template></el-table-column>
</el-table>`

function rows() {
  return [
    { name: '甲', amt: 100, audited: 1, remark: '' },
    { name: '乙', amt: 2000.5, audited: 2, remark: 'x' },
    { name: '丙', amt: null, audited: 3, remark: '' },
  ]
}

async function grid(extra: Record<string, (...a: never[]) => unknown> = {}) {
  const onAmt = vi.fn((row: { amt: unknown }, v: unknown) => { row.amt = v })
  const onRemarkBlur = vi.fn((row: { remark: unknown }, v: unknown) => { row.remark = v })
  const onDbl = vi.fn()
  const w = await mountGrid(TABLE, () => ({ rows: rows() }), { onAmt, onRemarkBlur, onDbl, ...extra } as never)
  return { w, onAmt, onRemarkBlur, onDbl, data: (w.vm as unknown as { rows: ReturnType<typeof rows> }).rows }
}

describe('平时只显示文本（R3）', () => {
  it('表体单元格不挂输入框，显示格式化文本', async () => {
    const { w } = await grid()
    expect(w.element.querySelectorAll('table.el-table__body input').length).toBe(0)
    expect(cell(w, 0, 0).textContent).toContain('甲')
    expect(cell(w, 1, 1).querySelector('.gt-cell-display')!.textContent).toBe('2,000.50')
    expect(cell(w, 2, 1).querySelector('.gt-cell-display--empty')).not.toBeNull()
  })
})

describe('选中与键盘（R4）', () => {
  it('单击只选中、不进编辑；承接框拿到焦点', async () => {
    const { w } = await grid()
    click(cell(w, 0, 0))
    await settle()
    expect(cell(w, 0, 0).hasAttribute('data-gt-active')).toBe(true)
    expect(document.activeElement).toBe(sink(w))
    expect(w.element.querySelector('td[data-gt-editing]')).toBeNull()
  })

  it('方向键移动，Shift 扩展选区', async () => {
    const { w } = await grid()
    click(cell(w, 0, 0))
    key(sink(w), 'ArrowRight')
    expect(cell(w, 0, 1).hasAttribute('data-gt-active')).toBe(true)
    key(sink(w), 'ArrowDown', { shiftKey: true })
    expect(cell(w, 1, 1).getAttribute('data-gt-sel')).toContain('b')
    expect(cell(w, 0, 1).getAttribute('data-gt-sel')).toContain('t')
  })

  it('Tab 跳到下一个可编辑格（跳过只读的「审定」列）', async () => {
    const { w } = await grid()
    click(cell(w, 0, 1))
    key(sink(w), 'Tab')
    expect(cell(w, 0, 3).hasAttribute('data-gt-active')).toBe(true)
  })

  it('直接输入：覆盖原内容进入编辑，Enter 提交并下移', async () => {
    const { w, data } = await grid()
    click(cell(w, 0, 0))
    typeInSink(sink(w), '新')
    await settle()
    const input = activeInput(w)
    expect(input.value).toBe('新')
    key(input, 'Enter')
    await settle()
    expect(data[0].name).toBe('新')
    expect(cell(w, 1, 0).hasAttribute('data-gt-active')).toBe(true)
    expect(w.element.querySelector('td[data-gt-editing]')).toBeNull()
  })

  it('数字格：单向绑定 + @change，提交时按数字发一次 change', async () => {
    const { w, onAmt, data } = await grid()
    click(cell(w, 2, 1))
    typeInSink(sink(w), '1234.5')
    await settle()
    key(activeInput(w), 'Enter')
    await settle()
    expect(onAmt).toHaveBeenCalledTimes(1)
    expect(onAmt.mock.calls[0][1]).toBe(1234.5)
    expect(data[2].amt).toBe(1234.5)
    expect(cell(w, 2, 1).textContent).toContain('1,234.50')
  })

  it('Esc 取消并还原，且不冒泡到页面（不关弹窗）', async () => {
    const { w, data } = await grid()
    const docEsc = vi.fn()
    document.addEventListener('keydown', docEsc)
    click(cell(w, 1, 0))
    typeInSink(sink(w), '错')
    await settle()
    expect(data[1].name).toBe('错') // v-model 即时更新
    const ev = key(activeInput(w), 'Escape')
    await settle()
    document.removeEventListener('keydown', docEsc)
    expect(ev.defaultPrevented).toBe(true)
    expect(docEsc).not.toHaveBeenCalled()
    expect(data[1].name).toBe('乙')
  })

  it('读 e.target.value 的 @blur 宿主：提交时读到最终值', async () => {
    const { w, onRemarkBlur, data } = await grid()
    click(cell(w, 0, 3))
    typeInSink(sink(w), '备')
    await settle()
    const input = activeInput(w)
    input.value = '备注内容'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await settle()
    key(input, 'Tab')
    await settle()
    expect(onRemarkBlur).toHaveBeenCalled()
    expect(onRemarkBlur.mock.calls.at(-1)![1]).toBe('备注内容')
    expect(data[0].remark).toBe('备注内容')
  })

  it('可编辑格双击 = 编辑（拦下页面双击）；只读格双击放行', async () => {
    const { w, onDbl } = await grid()
    mousedown(cell(w, 0, 0))
    dblclick(cell(w, 0, 0))
    await settle()
    expect(w.element.querySelector('td[data-gt-editing] input')).not.toBeNull()
    expect(onDbl).not.toHaveBeenCalled()
    mousedown(cell(w, 0, 2))
    dblclick(cell(w, 0, 2))
    await settle()
    expect(onDbl).toHaveBeenCalledTimes(1)
  })

  it('F2 进入编辑、光标在末尾；Backspace 清空并进入编辑', async () => {
    const { w } = await grid()
    click(cell(w, 1, 0))
    key(sink(w), 'F2')
    await settle()
    const input = activeInput(w)
    expect(input.value).toBe('乙')
    expect(input.selectionStart).toBe(1)
    key(input, 'Escape')
    await settle()
    key(sink(w), 'Backspace')
    await settle()
    expect(activeInput(w).value).toBe('')
  })

  it('只读格输入给提示、不进编辑', async () => {
    const { w } = await grid()
    click(cell(w, 0, 2))
    typeInSink(sink(w), '9')
    await settle()
    expect(w.element.querySelector('td[data-gt-editing]')).toBeNull()
    expect(sink(w).value).toBe('')
  })
})

describe('输入法（ADR-4）', () => {
  it('组字在承接框里完成，组好的字带进编辑器', async () => {
    const { w } = await grid()
    click(cell(w, 0, 0))
    const s = sink(w)
    s.dispatchEvent(new Event('compositionstart'))
    expect(s.classList.contains('gt-grid-sink--composing')).toBe(true)
    s.value = '中文'
    s.dispatchEvent(new Event('input', { bubbles: true }))
    await settle()
    expect(w.element.querySelector('td[data-gt-editing]')).toBeNull() // 组字中不打开
    s.dispatchEvent(new Event('compositionend'))
    await settle()
    expect(activeInput(w).value).toBe('中文')
    expect(s.classList.contains('gt-grid-sink--composing')).toBe(false)
  })
})

describe('复制 / 粘贴 / 清空 / 撤销（R6）', () => {
  it('复制选区为制表符文本与 HTML', async () => {
    const { w } = await grid()
    click(cell(w, 0, 0))
    key(sink(w), 'ArrowDown', { shiftKey: true })
    key(sink(w), 'ArrowRight', { shiftKey: true })
    const { ev, store } = clipboardEvent('copy')
    sink(w).dispatchEvent(ev)
    expect(store['text/plain']).toBe('甲\t100.00\r\n乙\t2,000.50')
    expect(store['text/html']).toContain('<td>2,000.50</td>')
    expect(cell(w, 0, 0).getAttribute('data-gt-copy')).toContain('t')
  })

  it('粘贴多行多列：只读格跳过，按目标格类型解析', async () => {
    const { w, data, onAmt } = await grid()
    click(cell(w, 0, 1))
    const { ev } = clipboardEvent('paste', { 'text/plain': '1,500.25\t99\r\n(300)\t88\r\n' })
    sink(w).dispatchEvent(ev)
    await settle()
    expect(data[0].amt).toBe(1500.25)
    expect(data[1].amt).toBe(-300)
    expect(onAmt).toHaveBeenCalledTimes(2)
    expect(data[0].audited).toBe(1) // 只读列未改
  })

  it('单个值粘到区域则填满；Delete 清空；Ctrl+Z 撤销', async () => {
    const { w, data } = await grid()
    click(cell(w, 0, 0))
    key(sink(w), 'ArrowDown', { shiftKey: true })
    sink(w).dispatchEvent(clipboardEvent('paste', { 'text/plain': '同名' }).ev)
    await settle()
    expect([data[0].name, data[1].name]).toEqual(['同名', '同名'])
    key(sink(w), 'z', { ctrlKey: true })
    await settle()
    expect([data[0].name, data[1].name]).toEqual(['甲', '乙'])
    key(sink(w), 'Delete')
    await settle()
    expect([data[0].name, data[1].name]).toEqual(['', ''])
    key(sink(w), 'z', { ctrlKey: true })
    await settle()
    expect([data[0].name, data[1].name]).toEqual(['甲', '乙'])
  })
})

describe('编辑方式（R1）', () => {
  it('经典方式：输入框常驻，单击不画选中框', async () => {
    useDisplayPrefsStore().setGridEditMode('classic')
    const { w } = await grid()
    expect(w.element.querySelectorAll('table.el-table__body input').length).toBeGreaterThan(0)
    click(cell(w, 0, 2))
    await settle()
    expect(cell(w, 0, 2).hasAttribute('data-gt-active')).toBe(false)
  })

  it('单击编辑：单击可编辑格直接进入编辑', async () => {
    useDisplayPrefsStore().setGridEditMode('click')
    const { w } = await grid()
    click(cell(w, 0, 0))
    await settle()
    expect(activeInput(w).value).toBe('甲')
  })

  it('切换编辑方式即时生效', async () => {
    const { w } = await grid()
    expect(w.element.querySelectorAll('table.el-table__body input').length).toBe(0)
    useDisplayPrefsStore().setGridEditMode('classic')
    await settle()
    expect(w.element.querySelectorAll('table.el-table__body input').length).toBeGreaterThan(0)
  })
})
