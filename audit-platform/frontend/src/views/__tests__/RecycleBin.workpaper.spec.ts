/**
 * 回收站里的底稿（spec procedure-trim-generation-delegation-chain 任务 10）：底稿不支持彻底删除（后端 409），
 * 行上不显示「删除」与倒计时、标「长期保留」，也不标「即将清理」；其他类型照旧。
 * 类型标签按后端真实类型键 `working_paper` 配色（原写 `workpaper`，底稿行恒为默认色）。
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, inject, provide } from 'vue'

const mocks = vi.hoisted(() => ({ stats: vi.fn(), list: vi.fn(), restore: vi.fn(), purge: vi.fn(), empty: vi.fn() }))
vi.mock('@/services/commonApi', () => ({
  getRecycleBinStats: mocks.stats,
  listRecycleBinItems: mocks.list,
  restoreRecycleBinItem: mocks.restore,
  permanentDeleteItem: mocks.purge,
  emptyRecycleBin: mocks.empty,
}))
vi.mock('@/utils/confirm', () => ({ confirmDangerous: vi.fn() }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn() } }))

import RecycleBin from '../RecycleBin.vue'

// el-table 桩：把行交给每一列按作用域插槽逐行渲染，并记下每行的 row-class-name
const ROWS = Symbol('rows')
const TableStub = defineComponent({
  props: { data: { type: Array, default: () => [] }, rowClassName: { type: Function, default: null } },
  setup(props, { slots }) {
    provide(ROWS, () => props.data)
    return () => h('div', [
      ...(props.data as any[]).map(row => h('span', { class: 'row-cls' }, String(props.rowClassName?.({ row }) ?? ''))),
      slots.default?.(),
    ])
  },
})
const ColumnStub = defineComponent({
  props: { label: { type: String, default: '' } },
  setup(props, { slots }) {
    const rows = inject(ROWS) as () => any[]
    return () => h('div', { 'data-col': props.label },
      rows().map((row, i) => h('div', { class: 'cell' }, slots.default?.({ row, $index: i }))))
  },
})
const stubs = {
  'el-table': TableStub,
  'el-table-column': ColumnStub,
  'el-button': { template: '<button><slot /></button>' },
  'el-tag': { props: ['type'], template: '<span class="tag" :data-type="type"><slot /></span>' },
  'el-icon': { template: '<i><slot /></i>' },
  'el-alert': true,
  'el-progress': true,
  'el-pagination': true,
  'el-radio-group': { template: '<div><slot /></div>' },
  'el-radio-button': { template: '<span><slot /></span>' },
}

const daysAgo = (n: number) => new Date(Date.now() - n * 86400000).toISOString()

describe('回收站：底稿行', () => {
  it('底稿不显示删除与倒计时、标「长期保留」、不标即将清理；附件照旧', async () => {
    mocks.stats.mockResolvedValue({ total: 2, limit: 500, is_over_limit: false, by_type: {} })
    mocks.list.mockResolvedValue({
      total: 2,
      items: [
        { id: 'w1', type: 'working_paper', type_label: '底稿', name: 'H3 投资性房地产', deleted_at: daysAgo(28), purgeable: false },
        { id: 'a1', type: 'attachment', type_label: '附件', name: '合同.pdf', deleted_at: daysAgo(28), purgeable: true },
      ],
    })
    const w = mount(RecycleBin, { global: { stubs, directives: { permission: {}, loading: {} } } })
    await flushPromises()

    const ops = w.find('[data-col="操作"]').findAll('.cell')
    expect(ops.map(c => c.text().replace(/\s+/g, ''))).toEqual(['恢复', '恢复删除'])
    const left = w.find('[data-col="剩余"]').findAll('.cell')
    expect(left.map(c => c.text())).toEqual(['长期保留', '2天'])
    expect(w.findAll('.row-cls').map(s => s.text())).toEqual(['', 'gt-rb-row--expiring'])
    const tags = w.find('[data-col="类型"]').findAll('.tag')
    expect(tags.map(t => t.attributes('data-type'))).toEqual(['success', 'info'])
  })
})
