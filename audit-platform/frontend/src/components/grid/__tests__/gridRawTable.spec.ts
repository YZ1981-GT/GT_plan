/**
 * spec excel-style-table-editing ADR-3 / ADR-6：原生表格（GtGridTable）、合并单元格坐标、GtGridCell 自定义显示。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { buildRawTableGeometry, rectWithin } from '../gridDom'
import { gridTableMixin } from '../plugin'
import {
  activeInput, click, clipboardEvent, gridComponents, key, mountGrid, settle, sink, typeInSink, unmountAll,
} from './gridHarness'

afterEach(() => unmountAll())

describe('原生表格坐标（合并单元格）', () => {
  it('rowspan / colspan 占位：被覆盖位置指回源格', () => {
    document.body.innerHTML = `<table id="t">
      <tr><td id="a" rowspan="2">A</td><td id="b" colspan="2">B</td></tr>
      <tr><td id="c">C</td><td id="d">D</td></tr></table>`
    const g = buildRawTableGeometry(document.getElementById('t') as HTMLTableElement)
    expect(g.rowCount).toBe(2)
    expect(g.colCount).toBe(3)
    expect(g.cellAt(1, 0)!.id).toBe('a')
    expect(g.cellAt(0, 2)!.id).toBe('b')
    expect(g.cellAt(1, 1)!.id).toBe('c')
    expect(g.boxOf(document.getElementById('d')!)).toEqual({ r: 1, c: 2, rs: 1, cs: 1 })
  })

  it('承接框定位扣掉根节点自己的边框（绝对定位以内边距框为基准）', () => {
    const root = document.createElement('table')
    const td = document.createElement('td')
    Object.defineProperty(root, 'clientLeft', { value: 2 })
    Object.defineProperty(root, 'clientTop', { value: 3 })
    root.getBoundingClientRect = () => ({ left: 100, top: 200, width: 400, height: 300 }) as DOMRect
    td.getBoundingClientRect = () => ({ left: 110, top: 220, width: 50, height: 20 }) as DOMRect
    expect(rectWithin(td, root)).toEqual({ left: 8, top: 17, width: 50, height: 20 })
  })
})

const RAW = `
<div class="host">
<GtGridTable class="sheet" data-sheet="明细" @click="onTableClick">
  <thead><tr><th>项目</th><th>期末</th><th>期初</th></tr></thead>
  <tbody>
    <tr v-for="row in rows" :key="row.k">
      <td>{{ row.k }}</td>
      <td><el-input-number v-model="row.end" :controls="false" :precision="2" /></td>
      <td>
        <GtGridCell :value="row.begin">
          <template #display><span class="amt">{{ (row.begin ?? 0).toFixed(1) }} 万</span></template>
          <el-input-number v-model="row.begin" :controls="false" @change="onBegin" />
        </GtGridCell>
      </td>
    </tr>
  </tbody>
</GtGridTable>
</div>`

describe('GtGridTable + GtGridCell', () => {
  async function raw() {
    const onBegin = vi.fn()
    const onTableClick = vi.fn()
    const w = await mountGrid(RAW, () => ({ rows: [{ k: '货币资金', end: 10, begin: 1 }, { k: '应收账款', end: 20, begin: 2 }] }), { onBegin, onTableClick } as never)
    const td = (r: number, c: number) => (w.element.querySelectorAll('tbody tr')[r] as HTMLTableRowElement).cells[c]
    return { w, td, onBegin, onTableClick, data: (w.vm as unknown as { rows: Array<{ end: number; begin: number }> }).rows }
  }

  it('渲染出来的就是那一张 table：class / 属性 / 事件落在它上面，外层不多包一层', async () => {
    const { w, td, onTableClick } = await raw()
    const table = w.element.querySelector('table.sheet') as HTMLTableElement
    expect(table).not.toBeNull()
    expect(table.parentElement).toBe(w.element) // `.host > table` 这类选择器照样命中
    expect(table.classList.contains('gt-grid-raw')).toBe(true)
    expect(table.getAttribute('data-sheet')).toBe('明细')
    td(0, 0).dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(onTableClick).toHaveBeenCalledTimes(1)
    expect(w.element.querySelectorAll('tbody input').length).toBe(0)
    expect(td(0, 1).textContent).toContain('10.00')
    expect(td(0, 2).querySelector('.amt')!.textContent).toBe('1.0 万')
  })

  it('承接框与读屏播报放在 table 的第一个子元素 —— 零高 caption 里，不进行列', async () => {
    const { w } = await raw()
    const table = w.element.querySelector('table.sheet') as HTMLTableElement
    const s = sink(w)
    expect(s.parentElement?.tagName).toBe('CAPTION')
    expect(table.caption).toBe(s.parentElement)
    expect(table.firstElementChild).toBe(s.parentElement)
    expect(s.parentElement?.querySelector('.gt-grid-live')).not.toBeNull()
    expect(buildRawTableGeometry(table).rowCount).toBe(3)
  })

  it('父组件的 scoped 样式落在 table 上（组件根节点继承父作用域）', async () => {
    const Host = defineComponent({
      __scopeId: 'data-v-host',
      template: '<div class="wrap"><GtGridTable class="sheet"><tbody><tr><td>甲</td></tr></tbody></GtGridTable></div>',
    } as Record<string, unknown>)
    const w = mount(Host, { attachTo: document.body, global: { components: gridComponents, mixins: [gridTableMixin] } })
    await settle()
    const table = w.element.querySelector('table.sheet') as HTMLTableElement
    expect(table.hasAttribute('data-v-host')).toBe(true)
    expect(table.parentElement?.classList.contains('wrap')).toBe(true)
    w.unmount()
  })

  it('直接输入编辑原生表格单元格，Enter 下移（行号含表头行）', async () => {
    const { w, td, data } = await raw()
    click(td(0, 1))
    typeInSink(sink(w), '55')
    await settle()
    key(activeInput(w), 'Enter')
    await settle()
    expect(data[0].end).toBe(55)
    expect(td(1, 1).hasAttribute('data-gt-active')).toBe(true)
  })

  it('GtGridCell：双击 / F2 进入编辑器，提交后回到自定义显示', async () => {
    const { w, td, onBegin, data } = await raw()
    click(td(1, 2))
    key(sink(w), 'F2')
    await settle()
    const input = activeInput(w)
    input.value = '8'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    key(input, 'Enter')
    await settle()
    expect(data[1].begin).toBe(8)
    expect(onBegin).toHaveBeenCalled()
    expect(td(1, 2).querySelector('.amt')!.textContent).toBe('8.0 万')
  })

  it('GtGridCell 粘贴：静默挂编辑器写入，宿主收到 change', async () => {
    const { w, td, onBegin, data } = await raw()
    click(td(0, 2))
    sink(w).dispatchEvent(clipboardEvent('paste', { 'text/plain': '3.5\n4.5' }).ev)
    await settle()
    expect(data.map((r) => r.begin)).toEqual([3.5, 4.5])
    expect(onBegin).toHaveBeenCalledTimes(2)
    expect(td(0, 2).querySelector('input')).toBeNull()
  })
})
