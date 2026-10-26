/**
 * 基本信息表企业树锁定模式（spec consol-autotree-linkage-closure R4.1~R4.3 / 任务 17）
 *
 * - 传入企业树代码即锁定：名称 / 代码 / 上级 / 最终控制方只读，不能新增；
 * - 企业树里已没有的行标「已不在企业树中」，只有这些行能勾选删除；
 * - 导入 Excel 按企业代码只更新可编辑字段、只更新填了的格，匹配不上的行列出并跳过；
 * - 企业树不可用（null）时保持手工维护。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

const { message } = vi.hoisted(() => ({ message: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() } }))
vi.mock('element-plus', () => ({ ElMessage: message }))
vi.mock('@/utils/confirm', () => ({ confirmBatch: vi.fn().mockResolvedValue(true) }))
vi.mock('@/composables/useFullscreen', () => ({ useFullscreen: () => ({ isFullscreen: ref(false), toggleFullscreen: vi.fn() }) }))
vi.mock('@/composables/useExcelIO', () => ({ useExcelIO: () => ({ exportTemplate: vi.fn(), exportData: vi.fn() }) }))

import SubsidiaryInfoSheet from '../worksheets/SubsidiaryInfoSheet.vue'

const Table = defineComponent({
  props: ['data'],
  provide() { return { rows: () => (this as any).data || [] } },
  setup(_, { slots }) { return () => h('div', { class: 'tbl' }, slots.default?.()) },
})
const Column = defineComponent({
  name: 'ElTableColumn',
  inject: ['rows'],
  props: ['label', 'prop', 'type', 'selectable'],
  setup(props, { slots }) {
    return function (this: any) {
      if (props.type) return h('div', { 'data-type': props.type })
      return h('div', { 'data-prop': props.prop || props.label }, this.rows().map((r: any) => h('div', { class: 'cell' }, slots.default?.({ row: r }))))
    }
  },
})
const Btn = defineComponent({
  emits: ['click'],
  setup(_, { slots, emit, attrs }) {
    return () => h('button', { 'data-testid': (attrs as any)['data-testid'], onClick: () => emit('click') }, slots.default?.())
  },
})
const Tag = defineComponent({ setup(_, { slots, attrs }) { return () => h('span', { 'data-testid': (attrs as any)['data-testid'] }, slots.default?.()) } })
const Input = defineComponent({ props: ['modelValue'], setup() { return () => h('input', { class: 'inp' }) } })
const Sel = defineComponent({ props: ['modelValue'], setup(_, { slots }) { return () => h('div', { class: 'sel' }, slots.default?.()) } })
const STUBS = {
  'el-table': Table, 'el-table-column': Column, 'el-button': Btn, 'el-tag': Tag, 'el-input': Input,
  'el-select': Sel, 'el-option': true, 'el-tooltip': { setup: (_: unknown, { slots }: any) => () => slots.default?.() },
  'el-icon': true, 'el-date-picker': Input, 'el-input-number': Input, ExcelImportPreviewDialog: true, WarningFilled: true,
}

function row(code: string, name: string, extra: Record<string, unknown> = {}) {
  return {
    company_name: name, company_code: code, parent_code: 'G', ultimate_controller: '某集团', ultimate_controller_code: 'G',
    account_subject: '', accounting_method: '', holding_type: '直接', indirect_holder: '', share_changed: '否', change_times: 0,
    acquisition_date: '', merge_type: '', first_consol_date: '', non_common_cost: null, non_common_ratio: null,
    common_cost: null, common_ratio: null, no_consol_cost: null, no_consol_ratio: null, disposal_date: '',
    disposal_amount: null, disposal_ratio: null, pre_disposal_reduce: '', pre_disposal_times: null,
    post_disposal_reduce: '', post_disposal_times: null, ...extra,
  }
}

function mountSheet(treeCodes: string[] | null, rows = [row('A', '甲公司', { accounting_method: '成本法' }), row('Z', '已转出公司')]) {
  return mount(SubsidiaryInfoSheet, {
    props: { modelValue: rows, treeCodes },
    global: { stubs: STUBS },
  })
}

function cells(wrapper: ReturnType<typeof mountSheet>, prop: string) {
  return wrapper.find(`[data-prop="${prop}"]`).findAll('.cell')
}

describe('SubsidiaryInfoSheet 企业树锁定模式', () => {
  beforeEach(() => { Object.values(message).forEach((f) => f.mockReset()) })

  it('三码与最终控制方只读、不能新增；不在企业树中的行标出，只有它能勾选', () => {
    const wrapper = mountSheet(['A'])
    expect(wrapper.find('[data-testid="info-add-row"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="info-tree-tip"]').exists()).toBe(true)
    for (const prop of ['company_name', 'company_code', 'parent_code', 'ultimate_controller', 'ultimate_controller_code']) {
      expect(cells(wrapper, prop)[0].find('input').exists()).toBe(false)
      expect(cells(wrapper, prop)[0].find('.sel').exists()).toBe(false)
    }
    expect(cells(wrapper, 'company_code')[0].text()).toBe('A')
    expect(cells(wrapper, 'company_name')[0].find('[data-testid="info-not-in-tree"]').exists()).toBe(false)
    expect(cells(wrapper, 'company_name')[1].find('[data-testid="info-not-in-tree"]').text()).toBe('已不在企业树中')
    // 可编辑字段仍是输入控件
    expect(cells(wrapper, 'accounting_method')[0].find('.sel').exists()).toBe(true)
    const selectable = wrapper.findAllComponents(Column).find((c) => c.props('type') === 'selection')!.props('selectable')
    expect(selectable(row('A', '甲公司'))).toBe(false)
    expect(selectable(row('Z', '已转出公司'))).toBe(true)
  })

  it('批量删除只删已不在企业树中的行', async () => {
    const wrapper = mountSheet(['A'])
    const vm = (wrapper.vm as any).$.setupState
    vm.onSelectionChange([...vm.rows])
    await flushPromises() // 等「删除」按钮按勾选数解除禁用
    await wrapper.find('[data-testid="info-batch-delete"]').trigger('click')
    await flushPromises()
    expect(vm.rows.map((r: any) => r.company_code)).toEqual(['A'])
    const emitted = wrapper.emitted('update:modelValue') as any[][]
    expect(emitted.at(-1)?.[0].map((r: any) => r.company_code)).toEqual(['A'])
  })

  it('导入按企业代码只更新可编辑且填了的格，不改树带出的字段、不新增行，匹配不上的列出', async () => {
    const wrapper = mountSheet(['A'])
    wrapper.findComponent({ name: 'ExcelImportPreviewDialog' }).vm.$emit('confirm', [
      { 企业代码: 'A', 子企业名称: '改名甲', 上级单位代码: 'HACK', 核算科目: '长期股权投资', '非同控-持股比例': 51 },
      { 企业代码: 'Q', 子企业名称: '外部公司' },
    ])
    await flushPromises()
    const rows = (wrapper.vm as any).$.setupState.rows
    expect(rows.map((r: any) => r.company_code)).toEqual(['A', 'Z'])
    expect(rows[0]).toMatchObject({
      company_name: '甲公司', parent_code: 'G', account_subject: '长期股权投资', non_common_ratio: 51, accounting_method: '成本法',
    })
    expect(message.warning).toHaveBeenCalledWith(expect.stringContaining('已跳过：Q'))
  })

  it('企业树不可用（null）时保持手工维护：可新增、三码可编辑、导入追加', async () => {
    const wrapper = mountSheet(null)
    expect(wrapper.find('[data-testid="info-add-row"]').exists()).toBe(true)
    expect(cells(wrapper, 'company_code')[0].find('input').exists()).toBe(true)
    expect(wrapper.find('[data-testid="info-not-in-tree"]').exists()).toBe(false)
    wrapper.findComponent({ name: 'ExcelImportPreviewDialog' }).vm.$emit('confirm', [{ 企业代码: 'Q', 子企业名称: '外部公司' }])
    await flushPromises()
    expect((wrapper.vm as any).$.setupState.rows.map((r: any) => r.company_code)).toEqual(['A', 'Z', 'Q'])
  })
})
