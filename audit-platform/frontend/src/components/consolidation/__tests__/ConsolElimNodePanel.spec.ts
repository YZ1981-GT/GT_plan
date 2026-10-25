/**
 * 差额分录面板（spec consol-tree-three-code-autobuild 任务 10.5 / 10.7，需求 9.3）
 *
 * - 本项目承载的差额节点：按 node_key 拉分录列表、节点金额、可选科目；新增按节点决定归属
 *   （母分差额 ⇒ branch_entity_code=企业代码）；提交审批 / 审批调复核接口并刷新、通知上层；
 * - 其他合并项目承载（下级合并企业的差额）：只读，经当前项目穿透接口读取，给前往链接，不显示新增与操作列。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import type { ConsolTreeNode } from '@/services/consolidationApi'

const api = {
  getEliminations: vi.fn(),
  getNodeAmounts: vi.fn(),
  getWorksheetAccounts: vi.fn(),
  createElimination: vi.fn(),
  updateElimination: vi.fn(),
  deleteElimination: vi.fn(),
  reviewElimination: vi.fn(),
  drillToEliminations: vi.fn(),
}
vi.mock('@/services/consolidationApi', () => ({
  getEliminations: (...a: any[]) => api.getEliminations(...a),
  getNodeAmounts: (...a: any[]) => api.getNodeAmounts(...a),
  getWorksheetAccounts: (...a: any[]) => api.getWorksheetAccounts(...a),
  createElimination: (...a: any[]) => api.createElimination(...a),
  updateElimination: (...a: any[]) => api.updateElimination(...a),
  deleteElimination: (...a: any[]) => api.deleteElimination(...a),
  reviewElimination: (...a: any[]) => api.reviewElimination(...a),
  drillToEliminations: (...a: any[]) => api.drillToEliminations(...a),
}))
const mockPush = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ push: mockPush }) }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() } }))
vi.mock('@/utils/confirm', () => ({
  confirmDelete: vi.fn().mockResolvedValue(undefined),
  confirmDangerous: vi.fn().mockResolvedValue(undefined),
  promptRejectReason: vi.fn().mockResolvedValue('金额需核对'),
}))

import ConsolElimNodePanel from '../ConsolElimNodePanel.vue'
import ConsolElimEntryForm from '../ConsolElimEntryForm.vue'

/** 表单在共用组件 ConsolElimEntryForm 里（与合并抵消分录明细表同一个），经其 expose 的 form 填明细行 */
function formOf(wrapper: ReturnType<typeof mountPanel>) {
  return (wrapper.findComponent(ConsolElimEntryForm).vm as any).form
}

function node(key: string, name: string, extra: Partial<ConsolTreeNode> = {}): ConsolTreeNode {
  const [code, role] = key.split(':') as [string, ConsolTreeNode['role']]
  return {
    project_id: null, company_code: code, company_name: name, parent_company_code: null, ultimate_company_code: null,
    consol_level: 1, children: [], node_key: key, role, kind: 'elim', display_name: `${name}（${role === 'branch_elim' ? '母分差额' : '合并差额'}）`,
    relation: null, host_project_id: 'p-g', flags: [], via: [], mode: null, ...extra,
  }
}
const TREE: ConsolTreeNode = {
  ...node('G:consol', '某集团'), kind: 'aggregate', project_id: 'p-g', display_name: '某集团（合并）', host_project_id: null,
  children: [
    node('G:branch_elim', '某集团'),
    { ...node('A:consol', '甲公司'), kind: 'aggregate', project_id: 'p-a', display_name: '甲公司（合并）', host_project_id: null,
      children: [node('A:consol_elim', '甲公司', { host_project_id: 'p-a' })] },
  ],
}

// 依赖注入式表格替身：逐行渲染列插槽，按钮可点击
const Table = defineComponent({
  props: ['data'],
  provide() { return { rows: () => (this as any).data || [] } },
  setup(_, { slots, attrs }) { return () => h('div', { class: 'tbl', 'data-testid': (attrs as any)['data-testid'] }, slots.default?.()) },
})
const Column = defineComponent({
  inject: ['rows'],
  props: ['label'],
  setup(props, { slots }) {
    return function (this: any) {
      return h('div', { class: 'col', 'data-label': props.label },
        this.rows().map((row: any, i: number) => h('div', { class: 'cell' }, slots.default?.({ row, $index: i }) ?? String(row[(this.$attrs as any).prop] ?? ''))))
    }
  },
})
const Btn = defineComponent({
  emits: ['click'],
  setup(_, { slots, emit, attrs }) {
    return () => h('button', { 'data-testid': (attrs as any)['data-testid'], disabled: (attrs as any).disabled, onClick: () => emit('click') }, slots.default?.())
  },
})
const Pass = (tag: string) => defineComponent({
  setup(_, { slots, attrs }) { return () => h(tag, { 'data-testid': (attrs as any)['data-testid'] }, [slots.default?.(), slots.title?.(), slots.footer?.()]) },
})
const STUBS = {
  // 抽屉替身：「离场开始」按钮模拟 Element Plus 的 close 事件（离场动画结束前不回写 update:modelValue）
  'el-drawer': defineComponent({
    props: ['modelValue'],
    emits: ['open', 'close'],
    setup(p, { slots, emit }) {
      return () => (p.modelValue
        ? h('section', { class: 'drawer' }, [
          h('button', { 'data-testid': 'drawer-leave-start', onClick: () => emit('close') }),
          slots.default?.(),
        ])
        : null)
    },
  }),
  'el-dialog': defineComponent({
    props: ['modelValue'],
    setup(p, { slots, attrs }) { return () => (p.modelValue ? h('div', { 'data-testid': (attrs as any)['data-testid'] }, [slots.default?.(), slots.footer?.()]) : null) },
  }),
  'el-table': Table,
  'el-table-column': Column,
  'el-button': Btn,
  'el-link': Btn,
  'el-alert': Pass('div'),
  'el-tag': Pass('span'),
  // 带 validate 的表单替身：表头规则交给 Element Plus 自己，这里只验明细行校验与请求体
  'el-form': defineComponent({
    methods: { validate: () => Promise.resolve(true) },
    template: '<form><slot /></form>',
  }),
  'el-form-item': Pass('div'),
  'el-select': true,
  'el-option': true,
  'el-input': true,
  GtAmountCell: defineComponent({ props: ['value'], setup: (p) => () => h('span', { class: 'amt' }, String(p.value ?? '')) }),
}
const directives = { loading: {} }

function mountPanel(n: ConsolTreeNode) {
  return mount(ConsolElimNodePanel, {
    props: { modelValue: true, projectId: 'p-g', year: 2025, node: n, tree: TREE },
    global: { stubs: STUBS, directives },
  })
}

const ENTRY = {
  id: 'e1', project_id: 'p-g', entry_no: 'IA-001', year: 2025, entry_type: 'internal_ar_ap', description: '内部往来',
  related_company_codes: null, branch_entity_code: 'G', review_status: 'draft', debit_amount: '60.00', credit_amount: '60.00',
  lines: [
    { account_code: '1122', account_name: '应收账款', debit_amount: '60.00', credit_amount: '0.00' },
    { account_code: '2202', account_name: '应付账款', debit_amount: '0.00', credit_amount: '60.00' },
  ],
}

describe('ConsolElimNodePanel', () => {
  beforeEach(() => {
    Object.values(api).forEach((f) => f.mockReset())
    api.getEliminations.mockResolvedValue([ENTRY])
    api.getNodeAmounts.mockResolvedValue({ year: 2025, node_key: 'G:branch_elim', display_name: '', kind: 'elim', rows: [] })
    api.getWorksheetAccounts.mockResolvedValue({ year: 2025, accounts: [] })
    api.reviewElimination.mockResolvedValue({ ...ENTRY, review_status: 'pending_review' })
    api.createElimination.mockResolvedValue({ ...ENTRY, id: 'e2' })
  })

  it('本项目承载：打开即按 node_key 列分录与节点金额；提交审批后刷新并通知上层', async () => {
    const wrapper = mountPanel(node('G:branch_elim', '某集团'))
    await flushPromises()
    expect(api.getEliminations).toHaveBeenCalledTimes(1)
    expect(api.getEliminations).toHaveBeenCalledWith('p-g', 2025, { nodeKey: 'G:branch_elim' })
    expect(api.getNodeAmounts).toHaveBeenCalledWith('p-g', 'G:branch_elim', 2025)
    expect(api.getWorksheetAccounts).toHaveBeenCalledWith('p-g', 2025)
    expect(wrapper.find('[data-testid="elim-panel-readonly"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="elim-status-IA-001"]').text()).toBe('草稿')

    await wrapper.find('[data-testid="elim-submit-IA-001"]').trigger('click')
    await flushPromises()
    expect(api.reviewElimination).toHaveBeenCalledWith('e1', 'p-g', { action: 'submit' })
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(api.getEliminations.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('新增：母分差额节点的分录归属该企业，保存后刷新', async () => {
    const wrapper = mountPanel(node('G:branch_elim', '某集团'))
    await flushPromises()
    await wrapper.find('[data-testid="elim-panel-new"]').trigger('click')
    await flushPromises()
    // 面板里归属固定为所点节点：只显示，不给下拉
    expect(wrapper.find('[data-testid="elim-form-target"]').text()).toBe('某集团（母分差额）')
    expect(wrapper.find('[data-testid="elim-form-target-select"]').exists()).toBe(false)
    formOf(wrapper).lines = [
      { account_code: '1122', account_name: '应收账款', debit_amount: '80', credit_amount: '' },
      { account_code: '2202', account_name: '应付账款', debit_amount: '', credit_amount: '80' },
    ]
    await flushPromises()
    await wrapper.find('[data-testid="elim-form-save"]').trigger('click')
    await flushPromises()
    expect(api.createElimination).toHaveBeenCalledTimes(1)
    const [pid, payload] = api.createElimination.mock.calls[0]
    expect(pid).toBe('p-g')
    expect(payload).toMatchObject({ project_id: 'p-g', year: 2025, branch_entity_code: 'G' })
    expect(payload.lines.map((l: any) => [l.account_code, l.debit_amount, l.credit_amount])).toEqual([
      ['1122', '80.00', '0.00'], ['2202', '0.00', '80.00'],
    ])
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.find('[data-testid="elim-form"]').exists()).toBe(false)
  })

  it('修改：回填原分录，按修改接口保存（不带项目与年度）', async () => {
    const wrapper = mountPanel(node('G:branch_elim', '某集团'))
    await flushPromises()
    api.updateElimination.mockResolvedValue(ENTRY)
    const editBtn = wrapper.findAll('button').find((b) => b.text() === '修改')
    await editBtn!.trigger('click')
    await flushPromises()
    const form = formOf(wrapper)
    expect(form.description).toBe('内部往来')
    expect(form.lines.map((l: any) => [l.account_code, l.debit_amount, l.credit_amount])).toEqual([
      ['1122', '60.00', ''], ['2202', '', '60.00'],
    ])
    await wrapper.find('[data-testid="elim-form-save"]').trigger('click')
    await flushPromises()
    expect(api.updateElimination).toHaveBeenCalledTimes(1)
    const [id, pid, payload] = api.updateElimination.mock.calls[0]
    expect([id, pid]).toEqual(['e1', 'p-g'])
    expect(payload.project_id).toBeUndefined()
    expect(payload.branch_entity_code).toBe('G')
  })

  it('已审批分录可撤销审批：确认后调复核接口 revoke，刷新并通知上层', async () => {
    api.getEliminations.mockResolvedValue([{ ...ENTRY, review_status: 'approved' }])
    api.reviewElimination.mockResolvedValue({ ...ENTRY, review_status: 'draft' })
    const wrapper = mountPanel(node('G:branch_elim', '某集团'))
    await flushPromises()
    expect(wrapper.find('[data-testid="elim-submit-IA-001"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="elim-delete-IA-001"]').exists()).toBe(false)
    await wrapper.find('[data-testid="elim-revoke-IA-001"]').trigger('click')
    await flushPromises()
    expect(api.reviewElimination).toHaveBeenCalledWith('e1', 'p-g', { action: 'revoke' })
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('借贷不平衡时保存按钮禁用且不调接口', async () => {
    const wrapper = mountPanel(node('G:branch_elim', '某集团'))
    await flushPromises()
    await wrapper.find('[data-testid="elim-panel-new"]').trigger('click')
    await flushPromises()
    formOf(wrapper).lines = [
      { account_code: '1122', account_name: '', debit_amount: '80', credit_amount: '' },
      { account_code: '2202', account_name: '', debit_amount: '', credit_amount: '70' },
    ]
    await flushPromises()
    expect(wrapper.find('[data-testid="elim-form-totals"]').text()).toContain('借贷不平衡')
    expect(wrapper.find('[data-testid="elim-form-save"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-testid="elim-form-save"]').trigger('click')
    expect(api.createElimination).not.toHaveBeenCalled()
  })

  it('其他合并项目承载：只读，经穿透接口读取，给前往链接，无新增与操作', async () => {
    api.drillToEliminations.mockResolvedValue({ rows: [{
      entry_id: 'e9', entry_no: 'IA-009', entry_type: 'internal_ar_ap', review_status: 'approved', host_project_id: 'p-a',
      debit_amount: '5.00', credit_amount: '5.00', lines: [],
    }] })
    const wrapper = mountPanel(node('A:consol_elim', '甲公司', { host_project_id: 'p-a' }))
    await flushPromises()
    expect(api.drillToEliminations).toHaveBeenCalledWith('p-g', 2025, 'A:consol_elim')
    expect(api.getEliminations).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="elim-panel-readonly"]').text()).toContain('甲公司（合并）')
    expect(wrapper.find('[data-testid="elim-panel-new"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="elim-status-IA-009"]').text()).toBe('已审批')
    await wrapper.find('[data-testid="elim-panel-goto"]').trigger('click')
    expect(mockPush).toHaveBeenCalledWith({ path: '/projects/p-a/consolidation', query: { year: '2025' } })
  })

  it('抽屉一开始离场就回写关闭：父组件随即能再次打开（不等离场动画结束）', async () => {
    const wrapper = mountPanel(node('G:branch_elim', '某集团'))
    await flushPromises()
    await wrapper.find('[data-testid="drawer-leave-start"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  })

  it('打开状态下切换到另一个差额节点会重新读取；同一节点引用刷新不重复读取', async () => {
    const wrapper = mountPanel(node('G:branch_elim', '某集团'))
    await flushPromises()
    expect(api.getEliminations).toHaveBeenCalledTimes(1)
    await wrapper.setProps({ node: { ...node('G:branch_elim', '某集团') } })
    await flushPromises()
    expect(api.getEliminations).toHaveBeenCalledTimes(1)
    await wrapper.setProps({ node: node('G:consol_elim', '某集团') })
    await flushPromises()
    expect(api.getEliminations).toHaveBeenCalledTimes(2)
    expect(api.getEliminations).toHaveBeenLastCalledWith('p-g', 2025, { nodeKey: 'G:consol_elim' })
    expect(api.getWorksheetAccounts).toHaveBeenCalledTimes(1)
  })
})
