/**
 * IncomeTaxCalcDialog.spec.ts — N-F7 所得税费用测算弹窗 vitest
 *
 * spec workpaper-n-tax-cycle N-F7（Task 3.2）
 *
 * 验证：
 * 1. 组件可正常挂载（renders without errors）
 * 2. 表单字段存在（form fields are present）
 * 3. 提交按钮调用 API（submit button calls API）
 * 4. 计算后显示结果（results display after calculation）
 * 5. "采纳并写回" emits 'applied'
 * 6. 默认 statutory_rate = 0.25
 * 7. buildRequestBody 构造正确 payload
 * 8. formatAmount / formatRate 格式化正确
 * 9. 动态 key-value 差异项增删
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import IncomeTaxCalcDialog from '../IncomeTaxCalcDialog.vue'

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

// Mock api
const mockPost = vi.fn().mockResolvedValue({
  current_income_tax: '250000.00',
  deferred_income_tax: '-30000.00',
  total_income_tax: '220000.00',
  effective_rate: '0.22',
  reconciliation_items: [
    { label: '利润总额 × 法定税率', amount: '250000.00' },
    { label: '永久性差异影响', amount: '0.00' },
    { label: '递延所得税调整', amount: '-30000.00' },
  ],
  is_llm_stub: true,
  applied_to_sheet: null,
  applied_at: null,
})

vi.mock('@/services/apiProxy', () => ({
  api: {
    post: (...args: any[]) => mockPost(...args),
  },
}))

const globalStubs = {
  stubs: {
    'el-dialog': { template: '<div><slot /><slot name="footer" /></div>', props: ['modelValue'], emits: ['update:model-value'] },
    'el-form': { template: '<div><slot /></div>' },
    'el-form-item': { template: '<div><slot /></div>' },
    'el-input-number': true,
    'el-input': true,
    'el-button': { template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>', props: ['disabled', 'loading', 'type'] },
    'el-alert': true,
    'el-divider': true,
    'el-descriptions': { template: '<div><slot /></div>' },
    'el-descriptions-item': { template: '<div><slot /></div>', props: ['label'] },
    'el-tag': { template: '<span><slot /></span>', props: ['type', 'size'] },
  },
}

const defaultProps = {
  visible: true,
  projectId: 'proj-n1',
  wpId: 'wp-n5',
  targetSheet: '所得税费用审定表N5-1',
}

describe('IncomeTaxCalcDialog — 组件挂载', () => {
  it('组件可正常挂载', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('无 targetSheet 时组件仍可挂载', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: { ...defaultProps, targetSheet: '' },
      global: globalStubs,
    })
    expect(wrapper.exists()).toBe(true)
  })
})

describe('IncomeTaxCalcDialog — 默认值', () => {
  it('默认 statutory_rate = 0.25', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.form.statutory_rate).toBe(0.25)
  })

  it('默认 profit_before_tax = 0', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.form.profit_before_tax).toBe(0)
  })

  it('默认 permanent_differences 为空数组', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.form.permanent_differences).toEqual([])
  })

  it('默认 temporary_differences 为空数组', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.form.temporary_differences).toEqual([])
  })

  it('apply_to_sheet 从 targetSheet prop 初始化', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.form.apply_to_sheet).toBe('所得税费用审定表N5-1')
  })
})

describe('IncomeTaxCalcDialog — buildRequestBody', () => {
  it('默认表单构造正确 payload', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    const body = vm.buildRequestBody()
    expect(body).toEqual({
      profit_before_tax: 0,
      statutory_rate: 0.25,
      permanent_differences: {},
      temporary_differences: {},
      deferred_tax_asset_change: 0,
      deferred_tax_liability_change: 0,
      apply_to_sheet: null,
    })
  })

  it('传入 applySheet 参数时 apply_to_sheet 正确设置', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    const body = vm.buildRequestBody('所得税费用审定表N5-1')
    expect(body.apply_to_sheet).toBe('所得税费用审定表N5-1')
  })

  it('永久性差异 key-value 正确转换为 map', async () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.form.permanent_differences = [
      { key: '罚款支出', value: 50000 },
      { key: '免税收入', value: -20000 },
    ]
    await nextTick()
    const body = vm.buildRequestBody()
    expect(body.permanent_differences).toEqual({
      '罚款支出': 50000,
      '免税收入': -20000,
    })
  })

  it('空 key 的差异项被过滤', async () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.form.permanent_differences = [
      { key: '', value: 100 },
      { key: '有效项', value: 200 },
    ]
    await nextTick()
    const body = vm.buildRequestBody()
    expect(body.permanent_differences).toEqual({ '有效项': 200 })
  })
})

describe('IncomeTaxCalcDialog — formatAmount', () => {
  it('正数格式化为千分位 + 2 位小数', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    const result = vm.formatAmount('250000.00')
    expect(result).toContain('250')
    expect(result).toContain('000')
    expect(result).toContain('.00')
  })

  it('零值格式化正确', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.formatAmount(0)).toBe('0.00')
  })

  it('非数字字符串原样返回', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.formatAmount('N/A')).toBe('N/A')
  })
})

describe('IncomeTaxCalcDialog — formatRate', () => {
  it('0.25 格式化为 25.00%', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.formatRate('0.25')).toBe('25.00%')
  })

  it('0.22 格式化为 22.00%', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.formatRate('0.22')).toBe('22.00%')
  })

  it('非数字字符串原样返回', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.formatRate('N/A')).toBe('N/A')
  })
})

describe('IncomeTaxCalcDialog — 提交按钮调用 API', () => {
  it('点击计算按钮调用 POST API', async () => {
    mockPost.mockClear()
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.form.profit_before_tax = 1000000
    await nextTick()

    // Find and click the "计算" button
    const buttons = wrapper.findAll('button')
    const calcBtn = buttons.find(b => b.text().includes('计算'))
    expect(calcBtn).toBeDefined()
    await calcBtn!.trigger('click')

    // Wait for async
    await nextTick()
    await new Promise(r => setTimeout(r, 10))

    expect(mockPost).toHaveBeenCalledWith(
      `/api/projects/proj-n1/workpapers/wp-n5/n5/income-tax-calc`,
      expect.objectContaining({
        profit_before_tax: 1000000,
        statutory_rate: 0.25,
        apply_to_sheet: null,
      }),
    )
  })
})

describe('IncomeTaxCalcDialog — 结果显示', () => {
  it('计算后 result 被设置', async () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    await vm.onCalc()
    await nextTick()

    expect(vm.result).not.toBeNull()
    expect(vm.result.current_income_tax).toBe('250000.00')
    expect(vm.result.deferred_income_tax).toBe('-30000.00')
    expect(vm.result.total_income_tax).toBe('220000.00')
    expect(vm.result.effective_rate).toBe('0.22')
  })

  it('is_llm_stub 被正确设置', async () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    await vm.onCalc()
    await nextTick()

    expect(vm.isLlmStub).toBe(true)
  })
})

describe('IncomeTaxCalcDialog — 采纳并写回', () => {
  it('写回成功后 emits applied', async () => {
    mockPost.mockResolvedValueOnce({
      current_income_tax: '250000.00',
      deferred_income_tax: '-30000.00',
      total_income_tax: '220000.00',
      effective_rate: '0.22',
      reconciliation_items: [],
      is_llm_stub: true,
      applied_to_sheet: '所得税费用审定表N5-1',
      applied_at: '2026-05-20T10:00:00Z',
    })

    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    // Set result so the button appears
    vm.result = {
      current_income_tax: '250000.00',
      deferred_income_tax: '-30000.00',
      total_income_tax: '220000.00',
      effective_rate: '0.22',
      reconciliation_items: [],
      is_llm_stub: true,
    }
    await nextTick()

    await vm.onApplyToSheet()
    await nextTick()

    expect(wrapper.emitted('applied')).toBeTruthy()
    expect(wrapper.emitted('applied')![0]).toEqual(['所得税费用审定表N5-1'])
  })

  it('无 apply_to_sheet 时不 emit applied', async () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: { ...defaultProps, targetSheet: '' },
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.form.apply_to_sheet = ''
    vm.result = { current_income_tax: '0', deferred_income_tax: '0', total_income_tax: '0', effective_rate: '0', reconciliation_items: [], is_llm_stub: true }
    await nextTick()

    await vm.onApplyToSheet()
    await nextTick()

    expect(wrapper.emitted('applied')).toBeFalsy()
  })
})

describe('IncomeTaxCalcDialog — emit update:visible', () => {
  it('关闭按钮触发 update:visible(false)', async () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const buttons = wrapper.findAll('button')
    const closeBtn = buttons.find(b => b.text().includes('关闭'))
    expect(closeBtn).toBeDefined()
    await closeBtn!.trigger('click')
    expect(wrapper.emitted('update:visible')).toBeTruthy()
    expect(wrapper.emitted('update:visible')![0]).toEqual([false])
  })
})

describe('IncomeTaxCalcDialog — 动态差异项增删', () => {
  it('addPermanent 添加一项', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.form.permanent_differences.length).toBe(0)
    vm.addPermanent()
    expect(vm.form.permanent_differences.length).toBe(1)
    expect(vm.form.permanent_differences[0]).toEqual({ key: '', value: 0 })
  })

  it('removePermanent 删除指定项', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.form.permanent_differences = [
      { key: 'A', value: 1 },
      { key: 'B', value: 2 },
    ]
    vm.removePermanent(0)
    expect(vm.form.permanent_differences.length).toBe(1)
    expect(vm.form.permanent_differences[0].key).toBe('B')
  })

  it('addTemporary 添加一项', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.addTemporary()
    expect(vm.form.temporary_differences.length).toBe(1)
  })

  it('removeTemporary 删除指定项', () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.form.temporary_differences = [
      { key: 'X', value: 10 },
      { key: 'Y', value: 20 },
    ]
    vm.removeTemporary(1)
    expect(vm.form.temporary_differences.length).toBe(1)
    expect(vm.form.temporary_differences[0].key).toBe('X')
  })
})

describe('IncomeTaxCalcDialog — 采纳并写回按钮 disabled', () => {
  it('无 apply_to_sheet 时写回按钮 disabled', async () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: { ...defaultProps, targetSheet: '' },
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.form.apply_to_sheet = ''
    vm.result = {
      current_income_tax: '0',
      deferred_income_tax: '0',
      total_income_tax: '0',
      effective_rate: '0',
      reconciliation_items: [],
      is_llm_stub: true,
    }
    await nextTick()

    const buttons = wrapper.findAll('button')
    const applyBtn = buttons.find(b => b.text().includes('采纳并写回'))
    expect(applyBtn).toBeDefined()
    expect(applyBtn!.attributes('disabled')).toBeDefined()
  })

  it('有 apply_to_sheet 时写回按钮不 disabled', async () => {
    const wrapper = mount(IncomeTaxCalcDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.result = {
      current_income_tax: '0',
      deferred_income_tax: '0',
      total_income_tax: '0',
      effective_rate: '0',
      reconciliation_items: [],
      is_llm_stub: true,
    }
    await nextTick()

    const buttons = wrapper.findAll('button')
    const applyBtn = buttons.find(b => b.text().includes('采纳并写回'))
    expect(applyBtn).toBeDefined()
    expect(applyBtn!.attributes('disabled')).toBeUndefined()
  })
})
