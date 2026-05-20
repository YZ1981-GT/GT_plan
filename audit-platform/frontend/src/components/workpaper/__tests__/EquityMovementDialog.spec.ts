/**
 * EquityMovementDialog.spec.ts — M-F7 权益变动表计算弹窗 vitest
 *
 * spec workpaper-m-equity-cycle M-F7（Task 3.3）
 *
 * 验证：
 * 1. buildRequestBody 构造正确 API payload
 * 2. formatAmount 格式化数字（千分位 + 2 位小数）
 * 3. formatChange 添加 +/- 前缀
 * 4. dialog emits update:visible on close
 * 5. "采纳并写回" 按钮 disabled when no targetSheet
 * 6. is_llm_stub 指示器渲染正确
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import EquityMovementDialog from '../EquityMovementDialog.vue'

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

// Mock api
vi.mock('@/services/apiProxy', () => ({
  api: {
    post: vi.fn().mockResolvedValue({
      closing_balances: {
        paid_in_capital: '5000000.00',
        capital_reserve: '2100000.00',
        surplus_reserve: '560000.00',
        retained_earnings: '1340000.00',
        oci: '50000.00',
        other_equity_instruments: '0.00',
      },
      movement_summary: {
        paid_in_capital_change: '0.00',
        capital_reserve_change: '100000.00',
        surplus_reserve_change: '60000.00',
        retained_earnings_change: '-160000.00',
        oci_change: '50000.00',
        other_equity_instruments_change: '0.00',
      },
      is_llm_stub: true,
      applied_to_sheet: null,
      applied_at: null,
    }),
  },
}))

const globalStubs = {
  stubs: {
    'el-dialog': { template: '<div><slot /><slot name="footer" /></div>', props: ['modelValue'], emits: ['update:model-value'] },
    'el-form': { template: '<div><slot /></div>' },
    'el-form-item': { template: '<div><slot /></div>' },
    'el-input-number': true,
    'el-button': { template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>', props: ['disabled', 'loading', 'type'] },
    'el-alert': true,
    'el-divider': true,
    'el-descriptions': true,
    'el-descriptions-item': true,
    'el-tag': { template: '<span><slot /></span>', props: ['type', 'size'] },
  },
}

const defaultProps = {
  visible: true,
  projectId: 'proj-m1',
  wpId: 'wp-m6',
  targetSheet: '明细表M6-2',
}

describe('EquityMovementDialog — 组件挂载', () => {
  it('组件可正常挂载', () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('无 targetSheet 时组件仍可挂载', () => {
    const wrapper = mount(EquityMovementDialog, {
      props: { ...defaultProps, targetSheet: '' },
      global: globalStubs,
    })
    expect(wrapper.exists()).toBe(true)
  })
})

describe('EquityMovementDialog — buildRequestBody 逻辑', () => {
  it('默认表单构造正确 payload（opening_balances 全 0 + changes 全 0）', () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    // Access the component's exposed buildRequestBody via vm
    const vm = wrapper.vm as any
    const body = vm.buildRequestBody()
    expect(body).toEqual({
      opening_balances: {
        paid_in_capital: 0,
        capital_reserve: 0,
        surplus_reserve: 0,
        retained_earnings: 0,
        oci: 0,
        other_equity_instruments: 0,
      },
      net_profit: 0,
      dividends: 0,
      surplus_reserve: 0,
      capital_reserve_changes: 0,
      oci_changes: 0,
      apply_to_sheet: null,
    })
  })

  it('传入 applySheet 参数时 apply_to_sheet 正确设置', () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    const body = vm.buildRequestBody('明细表M6-2')
    expect(body.apply_to_sheet).toBe('明细表M6-2')
  })

  it('表单修改后 payload 反映新值', async () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.form.paid_in_capital = 5000000
    vm.form.capital_reserve = 2000000
    vm.form.net_profit = 600000
    vm.form.dividends = 200000
    await nextTick()

    const body = vm.buildRequestBody()
    expect(body.opening_balances.paid_in_capital).toBe(5000000)
    expect(body.opening_balances.capital_reserve).toBe(2000000)
    expect(body.net_profit).toBe(600000)
    expect(body.dividends).toBe(200000)
    expect(body.apply_to_sheet).toBeNull()
  })
})

describe('EquityMovementDialog — formatAmount', () => {
  it('正数格式化为千分位 + 2 位小数', () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    const result = vm.formatAmount('5000000.00')
    // 5,000,000.00 (zh-CN locale)
    expect(result).toContain('5')
    expect(result).toContain('000')
    expect(result).toContain('.00')
  })

  it('零值格式化正确', () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.formatAmount('0')).toBe('0.00')
    expect(vm.formatAmount(0)).toBe('0.00')
  })

  it('非数字字符串原样返回', () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.formatAmount('N/A')).toBe('N/A')
    expect(vm.formatAmount('--')).toBe('--')
  })

  it('负数格式化正确', () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    const result = vm.formatAmount('-1234567.89')
    expect(result).toContain('1,234,567.89') // negative sign + formatted
  })
})

describe('EquityMovementDialog — formatChange', () => {
  it('正数添加 + 前缀', () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    const result = vm.formatChange('100000.00')
    expect(result.startsWith('+')).toBe(true)
    expect(result).toContain('100,000.00')
  })

  it('负数保留 - 前缀（不加 +）', () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    const result = vm.formatChange('-160000.00')
    expect(result.startsWith('+')).toBe(false)
    expect(result).toContain('160,000.00')
  })

  it('零值不加前缀', () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    const result = vm.formatChange('0')
    expect(result.startsWith('+')).toBe(false)
    expect(result).toContain('0.00')
  })

  it('非数字字符串原样返回', () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    expect(vm.formatChange('N/A')).toBe('N/A')
  })
})

describe('EquityMovementDialog — emit update:visible', () => {
  it('关闭按钮触发 update:visible(false)', async () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    // Find the "关闭" button and click it
    const buttons = wrapper.findAll('button')
    const closeBtn = buttons.find(b => b.text().includes('关闭'))
    expect(closeBtn).toBeDefined()
    await closeBtn!.trigger('click')
    expect(wrapper.emitted('update:visible')).toBeTruthy()
    expect(wrapper.emitted('update:visible')![0]).toEqual([false])
  })
})

describe('EquityMovementDialog — 采纳并写回按钮 disabled', () => {
  it('无 targetSheet 时写回按钮 disabled', async () => {
    const wrapper = mount(EquityMovementDialog, {
      props: { ...defaultProps, targetSheet: '' },
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    // Simulate having a result
    vm.result = {
      closing_balances: { paid_in_capital: '0', capital_reserve: '0', surplus_reserve: '0', retained_earnings: '0', oci: '0', other_equity_instruments: '0' },
      movement_summary: { paid_in_capital_change: '0', capital_reserve_change: '0', surplus_reserve_change: '0', retained_earnings_change: '0', oci_change: '0', other_equity_instruments_change: '0' },
      is_llm_stub: true,
      applied_to_sheet: null,
    }
    await nextTick()

    const buttons = wrapper.findAll('button')
    const applyBtn = buttons.find(b => b.text().includes('采纳并写回'))
    expect(applyBtn).toBeDefined()
    expect(applyBtn!.attributes('disabled')).toBeDefined()
  })

  it('有 targetSheet 时写回按钮不 disabled', async () => {
    const wrapper = mount(EquityMovementDialog, {
      props: { ...defaultProps, targetSheet: '明细表M6-2' },
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.result = {
      closing_balances: { paid_in_capital: '0', capital_reserve: '0', surplus_reserve: '0', retained_earnings: '0', oci: '0', other_equity_instruments: '0' },
      movement_summary: { paid_in_capital_change: '0', capital_reserve_change: '0', surplus_reserve_change: '0', retained_earnings_change: '0', oci_change: '0', other_equity_instruments_change: '0' },
      is_llm_stub: true,
      applied_to_sheet: null,
    }
    await nextTick()

    const buttons = wrapper.findAll('button')
    const applyBtn = buttons.find(b => b.text().includes('采纳并写回'))
    expect(applyBtn).toBeDefined()
    expect(applyBtn!.attributes('disabled')).toBeUndefined()
  })
})

describe('EquityMovementDialog — is_llm_stub 指示器', () => {
  it('isLlmStub=true 时显示 warning tag', async () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.isLlmStub = true
    await nextTick()

    const tag = wrapper.find('span') // el-tag stubbed as <span>
    expect(wrapper.text()).toContain('Stub 模式')
  })

  it('isLlmStub=false 时显示 success tag', async () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.isLlmStub = false
    await nextTick()

    expect(wrapper.text()).toContain('AI 服务已启用')
  })

  it('isLlmStub=null 时不显示 tag', async () => {
    const wrapper = mount(EquityMovementDialog, {
      props: defaultProps,
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.isLlmStub = null
    await nextTick()

    expect(wrapper.text()).not.toContain('Stub 模式')
    expect(wrapper.text()).not.toContain('AI 服务已启用')
  })
})
