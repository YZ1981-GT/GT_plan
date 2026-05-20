/**
 * AssetImpairmentDialog.spec.ts — Sprint 3 Task 3.4 (H-F12)
 *
 * 烟测目标：
 * 1. visible=true 时组件可挂载
 * 2. 表单默认值（asset_group_id / book_value / discount_rate / cash_flows 5 年）
 * 3. isFormValid 校验逻辑
 * 4. 调用 impairment-analysis API 后渲染 result 区
 * 5. onApplyToSheet 写回联动
 * 6. result 在弹窗关闭时重置
 * 7. addCashFlowYear / removeCashFlowYear 操作
 * 8. buildRequestBody 正确构建请求体
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const mockPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: (...args: any[]) => mockPost(...args),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import AssetImpairmentDialog from '../AssetImpairmentDialog.vue'

beforeEach(() => {
  mockPost.mockReset()
})

const PROPS_BASE = {
  visible: true,
  projectId: 'proj-1',
  wpId: 'wp-1',
  targetSheet: '减值测算表H1-14',
}

const STUBS = {
  'el-dialog': true, 'el-form': true, 'el-form-item': true,
  'el-radio-group': true, 'el-radio': true, 'el-input-number': true,
  'el-input': true, 'el-divider': true, 'el-table': true,
  'el-table-column': true, 'el-button': true, 'el-alert': true,
  'el-descriptions': true, 'el-descriptions-item': true, 'el-tag': true,
}

describe('AssetImpairmentDialog (H-F12)', () => {
  it('1. visible=true 时组件可挂载', () => {
    const wrapper = mount(AssetImpairmentDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('2. 表单默认值正确', () => {
    const wrapper = mount(AssetImpairmentDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    expect(vm.form.asset_group_id).toBe('CGU-001')
    expect(vm.form.book_value).toBe(1000000)
    expect(vm.form.discount_rate).toBe(0.10)
    expect(vm.form.terminal_value).toBe(0)
    expect(vm.form.cash_flows).toHaveLength(5)
    expect(vm.form.cash_flows[0]).toBe(200000)
    expect(vm.result).toBeNull()
  })

  it('3. isFormValid 校验：asset_group_id 为空时无效', () => {
    const wrapper = mount(AssetImpairmentDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.asset_group_id = ''
    expect(vm.isFormValid).toBe(false)
    vm.form.asset_group_id = 'CGU-001'
    expect(vm.isFormValid).toBe(true)
  })

  it('3b. isFormValid 校验：book_value <= 0 时无效', () => {
    const wrapper = mount(AssetImpairmentDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.book_value = 0
    expect(vm.isFormValid).toBe(false)
  })

  it('3c. isFormValid 校验：discount_rate 超范围时无效', () => {
    const wrapper = mount(AssetImpairmentDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.discount_rate = 0
    expect(vm.isFormValid).toBe(false)
    vm.form.discount_rate = 1
    expect(vm.isFormValid).toBe(false)
    vm.form.discount_rate = 0.10
    expect(vm.isFormValid).toBe(true)
  })

  it('3d. isFormValid 校验：所有现金流为 0 时无效', () => {
    const wrapper = mount(AssetImpairmentDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.cash_flows = [0, 0, 0, 0, 0]
    expect(vm.isFormValid).toBe(false)
  })

  it('4. onAnalyze 调用 API 并存储 result', async () => {
    const fakeResp = {
      asset_group_id: 'CGU-001',
      book_value: '1000000',
      present_value_of_cash_flows: '758157.35',
      fair_value_less_costs: null,
      recoverable_amount: '758157.35',
      impairment_loss: '241842.65',
      is_impaired: true,
      dcf_details: [
        { year: 1, cash_flow: '200000', discount_factor: '1.10', present_value: '181818.18' },
      ],
      summary: '资产组 CGU-001：需计提减值',
      is_llm_stub: true,
      applied_to_sheet: null,
    }
    mockPost.mockResolvedValueOnce(fakeResp)

    const wrapper = mount(AssetImpairmentDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onAnalyze()

    expect(mockPost).toHaveBeenCalledWith(
      `/api/projects/proj-1/workpapers/wp-1/h1/impairment-analysis`,
      expect.objectContaining({
        asset_group_id: 'CGU-001',
        book_value: 1000000,
        discount_rate: 0.10,
        cash_flows: [200000, 220000, 240000, 260000, 280000],
      }),
    )
    expect(vm.result).toEqual(fakeResp)
  })

  it('5. onApplyToSheet 写回联动 + emit applied', async () => {
    const fakeResp = {
      asset_group_id: 'CGU-001',
      book_value: '1000000',
      present_value_of_cash_flows: '758157.35',
      fair_value_less_costs: null,
      recoverable_amount: '758157.35',
      impairment_loss: '241842.65',
      is_impaired: true,
      dcf_details: [],
      summary: 'test',
      is_llm_stub: true,
      applied_to_sheet: '减值测算表H1-14',
    }
    mockPost.mockResolvedValueOnce(fakeResp)

    const wrapper = mount(AssetImpairmentDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onApplyToSheet()

    expect(mockPost).toHaveBeenCalledWith(
      `/api/projects/proj-1/workpapers/wp-1/h1/impairment-analysis`,
      expect.objectContaining({
        apply_to_sheet: '减值测算表H1-14',
        asset_group_id: 'CGU-001',
      }),
    )
    const emitted = wrapper.emitted('applied')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual(['减值测算表H1-14'])
  })

  it('6. result 在弹窗关闭时重置', async () => {
    const wrapper = mount(AssetImpairmentDialog, {
      props: { ...PROPS_BASE, visible: true },
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.result = { asset_group_id: 'CGU-001', is_impaired: false }
    await wrapper.setProps({ visible: false })
    expect(vm.result).toBeNull()
  })

  it('7. addCashFlowYear / removeCashFlowYear 操作', () => {
    const wrapper = mount(AssetImpairmentDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    expect(vm.form.cash_flows).toHaveLength(5)

    // Add year
    vm.addCashFlowYear()
    expect(vm.form.cash_flows).toHaveLength(6)

    // Remove year
    vm.removeCashFlowYear(5)
    expect(vm.form.cash_flows).toHaveLength(5)

    // Cannot remove below 1
    vm.form.cash_flows = [200000]
    vm.removeCashFlowYear(0)
    // Should not go below 1 (the function checks length > 1)
    expect(vm.form.cash_flows).toHaveLength(1)
  })

  it('8. onApplyToSheet 无 targetSheet 时不调 API', async () => {
    const wrapper = mount(AssetImpairmentDialog, {
      props: { ...PROPS_BASE, targetSheet: '' },
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onApplyToSheet()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('9. buildRequestBody 含 fair_value_less_costs 时包含该字段', () => {
    const wrapper = mount(AssetImpairmentDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.fair_value_less_costs = 500000
    const body = vm.buildRequestBody()
    expect(body.fair_value_less_costs).toBe(500000)
  })

  it('10. buildRequestBody 不含 fair_value_less_costs 时不包含该字段', () => {
    const wrapper = mount(AssetImpairmentDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.fair_value_less_costs = null
    const body = vm.buildRequestBody()
    expect(body.fair_value_less_costs).toBeUndefined()
  })
})
