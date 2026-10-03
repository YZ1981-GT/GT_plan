/**
 * 分录表单（spec consol-elimination-single-source-push 任务 9.2 / 需求 1.3）
 *
 * 差额节点面板与合并抵消分录明细表共用：
 * - 明细表：归属从本项目承载的差额节点里选（hosted_nodes）；多个时必须选，只有一个时默认选中；
 * - 请求体的归属按所选节点（合并差额 ⇒ null，母分差额 ⇒ 企业代码）；
 * - 修改：按分录的 branch_entity_code 找回所选节点，走修改接口。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

const api = { createElimination: vi.fn(), updateElimination: vi.fn() }
vi.mock('@/services/consolidationApi', () => ({
  createElimination: (...a: any[]) => api.createElimination(...a),
  updateElimination: (...a: any[]) => api.updateElimination(...a),
}))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn() } }))

import ConsolElimEntryForm from '../ConsolElimEntryForm.vue'

const TARGETS = [
  { node_key: 'G:consol_elim', label: '某集团（合并差额）', branch_entity_code: null },
  { node_key: 'G:branch_elim', label: '某集团（母分差额）', branch_entity_code: 'G' },
]

const Btn = defineComponent({
  emits: ['click'],
  setup(_, { slots, emit, attrs }) {
    return () => h('button', { 'data-testid': (attrs as any)['data-testid'], disabled: (attrs as any).disabled, onClick: () => emit('click') }, slots.default?.())
  },
})
const Pass = (tag: string) => defineComponent({
  setup(_, { slots, attrs }) { return () => h(tag, { 'data-testid': (attrs as any)['data-testid'] }, [slots.default?.(), slots.footer?.()]) },
})
const STUBS = {
  'el-dialog': defineComponent({
    props: ['modelValue'],
    setup(p, { slots, attrs }) { return () => (p.modelValue ? h('div', { 'data-testid': (attrs as any)['data-testid'] }, [slots.default?.(), slots.footer?.()]) : null) },
  }),
  'el-form': defineComponent({ methods: { validate: () => Promise.resolve(true) }, template: '<form><slot /></form>' }),
  'el-form-item': Pass('div'),
  'el-table': Pass('div'),
  'el-table-column': true,
  'el-select': Pass('div'),
  'el-option': true,
  'el-input': true,
  'el-button': Btn,
}

function mountForm(props: Record<string, unknown> = {}) {
  return mount(ConsolElimEntryForm, {
    props: { modelValue: true, projectId: 'p-g', year: 2025, targets: TARGETS, ...props },
    global: { stubs: STUBS },
  })
}

const BALANCED = [
  { account_code: '1122', account_name: '应收账款', debit_amount: '80', credit_amount: '' },
  { account_code: '2202', account_name: '应付账款', debit_amount: '', credit_amount: '80' },
]

describe('ConsolElimEntryForm', () => {
  beforeEach(() => {
    api.createElimination.mockReset().mockResolvedValue({ id: 'e2' })
    api.updateElimination.mockReset().mockResolvedValue({ id: 'e1' })
  })

  it('多个可选节点：必须先选归属节点，未选时保存禁用并说明原因', async () => {
    const wrapper = mountForm()
    await flushPromises()
    expect(wrapper.find('[data-testid="elim-form-target-select"]').exists()).toBe(true)
    const form = (wrapper.vm as any).form
    form.lines = BALANCED
    await flushPromises()
    expect(wrapper.find('[data-testid="elim-form-totals"]').text()).toContain('请选择归属节点')
    expect(wrapper.find('[data-testid="elim-form-save"]').attributes('disabled')).toBeDefined()

    form.target_key = 'G:branch_elim'
    await flushPromises()
    expect(wrapper.find('[data-testid="elim-form-save"]').attributes('disabled')).toBeUndefined()
    await wrapper.find('[data-testid="elim-form-save"]').trigger('click')
    await flushPromises()
    const [pid, payload] = api.createElimination.mock.calls[0]
    expect(pid).toBe('p-g')
    expect(payload).toMatchObject({ project_id: 'p-g', year: 2025, branch_entity_code: 'G' })
    expect(wrapper.emitted('saved')?.[0]).toEqual([{ id: 'e2' }, 'create'])
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([false])
  })

  it('只有一个可选节点：默认选中；选合并差额 ⇒ 归属为空', async () => {
    const wrapper = mountForm({ targets: [TARGETS[0]] })
    await flushPromises()
    const form = (wrapper.vm as any).form
    expect(form.target_key).toBe('G:consol_elim')
    form.lines = BALANCED
    await flushPromises()
    await wrapper.find('[data-testid="elim-form-save"]').trigger('click')
    await flushPromises()
    expect(api.createElimination.mock.calls[0][1].branch_entity_code).toBeNull()
  })

  it('修改：按分录的 branch_entity_code 找回所选节点，走修改接口（不带项目与年度）', async () => {
    const entry = {
      id: 'e1', project_id: 'p-g', entry_no: 'IA-001', year: 2025, entry_type: 'internal_trade', description: '内部交易',
      related_company_codes: null, branch_entity_code: 'G', review_status: 'rejected', debit_amount: '5', credit_amount: '5',
      lines: [
        { account_code: '6001', account_name: '主营业务收入', debit_amount: '5', credit_amount: '0' },
        { account_code: '6401', account_name: '主营业务成本', debit_amount: '0', credit_amount: '5' },
      ],
    }
    const wrapper = mountForm({ entry })
    await flushPromises()
    const form = (wrapper.vm as any).form
    expect([form.target_key, form.entry_type, form.description]).toEqual(['G:branch_elim', 'internal_trade', '内部交易'])
    await wrapper.find('[data-testid="elim-form-save"]').trigger('click')
    await flushPromises()
    const [id, pid, payload] = api.updateElimination.mock.calls[0]
    expect([id, pid]).toEqual(['e1', 'p-g'])
    expect(payload.project_id).toBeUndefined()
    expect(payload.branch_entity_code).toBe('G')
    expect(wrapper.emitted('saved')?.[0]?.[1]).toBe('update')
  })

  it('没有可录入的差额节点：保存禁用并说明', async () => {
    const wrapper = mountForm({ targets: [] })
    await flushPromises()
    ;(wrapper.vm as any).form.lines = BALANCED
    await flushPromises()
    expect(wrapper.find('[data-testid="elim-form-totals"]').text()).toContain('本合并项目没有可录入的差额节点')
    expect(wrapper.find('[data-testid="elim-form-save"]').attributes('disabled')).toBeDefined()
  })

  it('重新打开即重置：上次填的明细不残留', async () => {
    const wrapper = mountForm({ targets: [TARGETS[0]] })
    await flushPromises()
    ;(wrapper.vm as any).form.lines = BALANCED
    await wrapper.setProps({ modelValue: false })
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    expect((wrapper.vm as any).form.lines.every((l: any) => !l.account_code)).toBe(true)
  })
})
