/**
 * 附注表格只读呈现（spec consol-autotree-linkage-closure R6）：表头以附注编辑器的投影为准。
 *
 * - 投影给出列树（`_column_tree`，如编辑器把两期并列合成的「本期 / 上期」期间层）时照它画表头，不按原始 headers 重建；
 * - 没有表头的表也显示行名；没有表格也没有正文时给空态。
 */
import { describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'
import { mount } from '@vue/test-utils'

const { projected } = vi.hoisted(() => ({ projected: { tables: null as any } }))
vi.mock('@/views/composables/useNoteTableProjection', () => ({
  useNoteTableProjection: () => ({ currentNoteTables: computed(() => projected.tables.value) }),
}))

import NoteTablesReadonly from '../NoteTablesReadonly.vue'

const NOTE = { note_section: '五、3', section_title: '应收款项融资', table_data: {}, text_content: '' }

function mountWith(tables: any[], note: Record<string, unknown> = NOTE) {
  projected.tables = ref(tables)
  return mount(NoteTablesReadonly, { props: { note }, global: { stubs: { 'el-empty': { template: '<div data-testid="ntr-empty" />' } } } })
}

describe('NoteTablesReadonly', () => {
  it('投影给出期间列树时照它画表头（两期并列：本期 / 上期各一组），单元格按叶子下标取值', () => {
    const wrapper = mountWith([{
      name: '应收款项融资情况',
      headers: ['项目', '金额', '比例', '金额', '比例'],
      _column_tree: [
        { label: '项目', headerIdx: 0 },
        { label: '本期', children: [{ label: '金额', headerIdx: 1 }, { label: '比例', headerIdx: 2 }] },
        { label: '上期', children: [{ label: '金额', headerIdx: 3 }, { label: '比例', headerIdx: 4 }] },
      ],
      rows: [{ label: '银行承兑汇票', values: [1200, '80%', 900, '75%'] }],
    }])
    const head = wrapper.findAll('[data-testid="ntr-table-0"] thead tr')
    expect(head).toHaveLength(2)
    expect(head[0].findAll('th').map((th) => [th.text(), th.attributes('colspan'), th.attributes('rowspan')])).toEqual([
      ['项目', '1', '2'], ['本期', '2', '1'], ['上期', '2', '1'],
    ])
    expect(wrapper.findAll('[data-testid="ntr-table-0"] tbody td').map((td) => td.text()))
      .toEqual(['银行承兑汇票', '1,200.00', '80%', '900.00', '75%'])
    expect(wrapper.find('[data-testid="ntr-table-name"]').text()).toBe('应收款项融资情况')
  })

  it('没有表头的表也显示行名；没有表格也没有正文 ⇒ 空态', () => {
    const noHead = mountWith([{ name: '', headers: [], rows: [{ label: '不适用', values: [] }] }])
    expect(noHead.find('[data-testid="ntr-table-0"] thead').exists()).toBe(false)
    expect(noHead.findAll('[data-testid="ntr-table-0"] tbody td').map((td) => td.text())).toEqual(['不适用'])
    expect(noHead.find('[data-testid="ntr-empty"]').exists()).toBe(false)

    const empty = mountWith([], { ...NOTE, text_content: '  ' })
    expect(empty.find('[data-testid="ntr-empty"]').exists()).toBe(true)
    expect(empty.find('[data-testid="ntr-text"]').exists()).toBe(false)
  })
})
