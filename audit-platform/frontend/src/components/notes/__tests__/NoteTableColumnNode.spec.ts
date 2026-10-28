/**
 * NoteTableColumnNode：列树递归渲染成 el-table 多级表头，单元格内容走宿主同一个 #cell 插槽
 * （spec note-pull-header-formula-closure R4）。
 */
import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import ElementPlus, { ElTable } from 'element-plus'
import NoteTableColumnNode from '../NoteTableColumnNode.vue'
import { buildNoteColumnTree } from '@/views/composables/noteColumnTree'

if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
}

const TABLE = {
  headers: ['类别', '金额', '比例', '账面价值', '金额', '比例', '账面价值'],
  multi_header: [
    ['类别', '期末数', '', '', '期初数', '', ''],
    ['', '账面余额', '', '账面价值', '账面余额', '', '账面价值'],
    ['', '金额', '比例', '', '金额', '比例', ''],
  ],
  rows: [{ label: '按组合计提', values: [100, 10, 90, 80, 8, 72] }],
}

describe('NoteTableColumnNode', () => {
  it('三层表头渲染成三行 thead，叶子单元格拿到正确的 headerIdx', async () => {
    const Host = defineComponent({
      setup() {
        const tree = buildNoteColumnTree(TABLE)
        return () => h(ElTable, { data: TABLE.rows, border: true }, () => tree.map((node, i) =>
          h(NoteTableColumnNode, { key: i, node }, {
            cell: ({ row, headerIdx }: any) => h('span', { class: 'cell-probe' },
              headerIdx === 0 ? row.label : `${headerIdx}:${row.values[headerIdx - 1]}`),
          })))
      },
    })
    const wrapper = mount(Host, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    await flushPromises()
    const headRows = wrapper.findAll('thead tr')
    expect(headRows).toHaveLength(3)
    expect(headRows[0].text()).toContain('期末数')
    expect(headRows[0].text()).toContain('期初数')
    expect(headRows[1].text()).toContain('账面余额')
    expect(headRows[2].findAll('th').map((th) => th.text())).toEqual(['金额', '比例', '金额', '比例'])
    // el-table-column 会用空行（$index = -1）预渲染一次插槽探测子列，只看表体
    const cells = wrapper.findAll('tbody .cell-probe').map((c) => c.text())
    expect(cells).toEqual(['按组合计提', '1:100', '2:10', '3:90', '4:80', '5:8', '6:72'])
    wrapper.unmount()
  })

  it('叶子列带 column-key = h{表头序号}：同名叶子（期末 / 期初下的「金额」）点击时按它定位', async () => {
    const keys: string[] = []
    const Host = defineComponent({
      setup() {
        const tree = buildNoteColumnTree(TABLE)
        return () => h(ElTable, { data: TABLE.rows, border: true }, () => tree.map((node, i) =>
          h(NoteTableColumnNode, { key: i, node }, {
            cell: ({ column, headerIdx, $index }: any) => {
              if ($index >= 0) keys.push(`${headerIdx}=${column?.columnKey}`)
              return h('span')
            },
          })))
      },
    })
    const wrapper = mount(Host, { global: { plugins: [ElementPlus] }, attachTo: document.body })
    await flushPromises()
    await flushPromises()
    expect([...new Set(keys)]).toEqual(['0=h0', '1=h1', '2=h2', '3=h3', '4=h4', '5=h5', '6=h6'])
    wrapper.unmount()
  })
})
