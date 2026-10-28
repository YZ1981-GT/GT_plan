/**
 * spec excel-style-table-editing 5.5：v-html 表格里的 contenteditable 格接入内核（表样编辑器 StructureEditor）。
 *
 * 原状：后端 excel-html 预览给可编辑格写 contenteditable="true"，一点就进编辑、方向键在格里移光标、
 * 输入法与撤销各算各的。现在：平时只显示文字；双击 / F2 / 直接输入才编辑；Enter / Tab / Esc / Delete / 撤销同其他表格。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, getCurrentInstance, h, onBeforeUnmount, onMounted, ref } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
import { bindContentEditableCells, CE_VALUE_CLASS } from '../contentEditableCells'
import { primaryEditor } from '../editorHost'
import { kernelForRawTable } from '../gridRegistry'
import { dblclick, key, mousedown, settle, typeInSink } from './gridHarness'

const HTML = `<table class="gt-excel-table">
<tr class="gt-col-header-row"><td class="gt-col-header"></td><td class="gt-col-header">A</td><td class="gt-col-header">B</td></tr>
<tr><td class="gt-row-header">1</td><td data-cell="0:0" contenteditable="true">项目<span class="gt-cell-coord">A1</span></td><td data-cell="0:1" contenteditable="true">期末<span class="gt-cell-coord">B1</span></td></tr>
<tr><td class="gt-row-header">2</td><td data-cell="1:0" contenteditable="true">货币资金<span class="gt-cell-coord">A2</span></td><td data-cell="1:1" contenteditable="true">100<span class="gt-cell-coord">B2</span></td></tr>
</table>`

const live: VueWrapper[] = []
afterEach(() => {
  while (live.length) live.pop()!.unmount()
  document.body.innerHTML = ''
})

function plainTable(): HTMLTableElement {
  document.body.innerHTML = HTML
  return document.querySelector('table') as HTMLTableElement
}
const tdOf = (root: ParentNode, cell: string) => root.querySelector(`td[data-cell="${cell}"]`) as HTMLTableCellElement
const valueOf = (td: Element) => td.querySelector(`.${CE_VALUE_CLASS}`) as HTMLElement

describe('bindContentEditableCells（不接内核）', () => {
  it('可编辑格不再 contenteditable；文字进编辑器 span，坐标标签留在外面', () => {
    const table = plainTable()
    bindContentEditableCells(table, { ignoreSelector: '.gt-cell-coord', onChange: vi.fn() })
    const td = tdOf(table, '1:0')
    expect(td.hasAttribute('contenteditable')).toBe(false)
    expect(valueOf(td).textContent).toBe('货币资金')
    expect(valueOf(td).hasAttribute('contenteditable')).toBe(false)
    expect(td.lastElementChild!.className).toBe('gt-cell-coord')
    expect(td.textContent).toBe('货币资金A2') // 读整格文字的旧代码不受影响
    expect(primaryEditor(td)!.getText()).toBe('货币资金')
    expect(table.querySelector('.gt-row-header .' + CE_VALUE_CLASS)).toBeNull()
  })

  it('打开才可编辑（纯文本）；提交回调新旧值并关闭；值没变不回调', async () => {
    const table = plainTable()
    const onChange = vi.fn()
    bindContentEditableCells(table, { ignoreSelector: '.gt-cell-coord', onChange })
    const td = tdOf(table, '1:1')
    const hd = primaryEditor(td)!
    expect(await hd.open({ mode: 'editing' })).toBe(true)
    expect(valueOf(td).getAttribute('contenteditable')).toBe('plaintext-only')
    expect(document.activeElement).toBe(valueOf(td))
    valueOf(td).textContent = '200'
    expect(hd.commit()).toBe('200')
    expect(onChange).toHaveBeenCalledWith(td, '200', '100')
    expect(valueOf(td).hasAttribute('contenteditable')).toBe(false)
    await hd.open({ mode: 'editing' })
    hd.commit()
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('取消还原原文字、不回调；直接输入带入首字与后敲的字', async () => {
    const table = plainTable()
    const onChange = vi.fn()
    bindContentEditableCells(table, { ignoreSelector: '.gt-cell-coord', onChange })
    const td = tdOf(table, '1:0')
    const hd = primaryEditor(td)!
    await hd.open({ mode: 'editing' })
    valueOf(td).textContent = '乱改'
    hd.cancel()
    expect(valueOf(td).textContent).toBe('货币资金')
    expect(valueOf(td).hasAttribute('contenteditable')).toBe(false)
    await hd.open({ mode: 'entering', initialText: '应', takePendingText: () => '收' })
    expect(valueOf(td).textContent).toBe('应收')
    hd.commit()
    expect(onChange).toHaveBeenCalledWith(td, '应收', '货币资金')
  })

  it('粘贴 / 撤销写入回调；拆掉接入还原后端结构（经典方式又回到一点就编辑）', () => {
    const table = plainTable()
    const onChange = vi.fn()
    const unbind = bindContentEditableCells(table, { ignoreSelector: '.gt-cell-coord', onChange })
    const td = tdOf(table, '0:1')
    const hd = primaryEditor(td)!
    expect(hd.applyText('期初')).toEqual({ ok: true, value: '期初' })
    expect(hd.setValue(null)).toBe(true)
    expect(onChange.mock.calls.map((c) => [c[1], c[2]])).toEqual([['期初', '期末'], ['', '期初']])
    unbind()
    expect(td.getAttribute('contenteditable')).toBe('true')
    expect(td.querySelector('.' + CE_VALUE_CLASS)).toBeNull()
    expect(td.innerHTML).toBe('<span class="gt-cell-coord">B1</span>')
    expect(primaryEditor(tdOf(table, '1:0'))).toBeNull()
    expect(tdOf(table, '1:0').innerHTML).toBe('货币资金<span class="gt-cell-coord">A2</span>')
  })
})

/** 与 StructureEditor.attachGrid 同样的接法：v-html 容器里的 table + 零高 caption 承接框 + 内核 */
function mountHost(onChange: (td: HTMLTableCellElement, text: string, before: string) => void) {
  const Host = defineComponent({
    setup() {
      const box = ref<HTMLElement | null>(null)
      let table: HTMLTableElement | null = null
      let unbind: (() => void) | null = null
      const k = kernelForRawTable(getCurrentInstance()!, () => table)
      onMounted(() => {
        box.value!.innerHTML = HTML
        table = box.value!.querySelector('table')!
        const cap = document.createElement('caption')
        table.insertBefore(cap, table.firstChild)
        unbind = bindContentEditableCells(table, { ignoreSelector: '.gt-cell-coord', onChange })
        k.attach(table, { sinkHost: cap })
      })
      onBeforeUnmount(() => { k.detach(); unbind?.() })
      return () => h('div', { ref: box })
    },
  })
  const w = mount(Host, { attachTo: document.body })
  live.push(w)
  return w
}

describe('接内核（Excel 方式）', () => {
  async function host() {
    const onChange = vi.fn()
    const w = mountHost(onChange)
    await settle()
    const sink = w.element.querySelector('.gt-grid-sink') as HTMLTextAreaElement
    return { w, onChange, sink, td: (cell: string) => tdOf(w.element, cell) }
  }

  it('单击只选中、不进编辑；双击才可编辑，Enter 提交并移到下一行', async () => {
    const { onChange, sink, td } = await host()
    mousedown(td('0:1'))
    await settle()
    expect(valueOf(td('0:1')).hasAttribute('contenteditable')).toBe(false)
    expect(document.activeElement).toBe(sink)
    dblclick(td('0:1'))
    await settle()
    const span = valueOf(td('0:1'))
    expect(span.getAttribute('contenteditable')).toBe('plaintext-only')
    span.textContent = '期末余额'
    key(span, 'Enter')
    await settle()
    expect(onChange).toHaveBeenCalledWith(td('0:1'), '期末余额', '期末')
    expect(span.hasAttribute('contenteditable')).toBe(false)
    expect(td('1:1').hasAttribute('data-gt-editing')).toBe(false)
    // 下移一行后直接打字：带入首字，Esc 还原且不回调
    typeInSink(sink, '9')
    await settle()
    expect(valueOf(td('1:1')).textContent).toBe('9')
    key(valueOf(td('1:1')), 'Escape')
    await settle()
    expect(valueOf(td('1:1')).textContent).toBe('100')
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('Delete 清空选中格、Ctrl+Z 撤销回原值（各回调一次）', async () => {
    const { onChange, sink, td } = await host()
    mousedown(td('1:0'))
    await settle()
    key(sink, 'Delete')
    await settle()
    expect(valueOf(td('1:0')).textContent).toBe('')
    key(sink, 'z', { ctrlKey: true })
    await settle()
    expect(valueOf(td('1:0')).textContent).toBe('货币资金')
    expect(onChange.mock.calls.map((c) => [c[0], c[1], c[2]])).toEqual([[td('1:0'), '', '货币资金'], [td('1:0'), '货币资金', '']])
  })
})
