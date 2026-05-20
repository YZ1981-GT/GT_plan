/**
 * FairValueTestDialog.spec.ts — G-investment-cycle G-F4 Task 2.6
 *
 * 烟测目标：
 * 1. visible=true 时组件可挂载
 * 2. 表单默认值 + level=1 默认
 * 3. isFormValid 校验逻辑（Level 1/2/3 各自）
 * 4. buildRequestBody 按 level 序列化对应字段
 * 5. 调用 fair-value-test API 后渲染 result 区
 * 6. onApplyToSheet 写回联动 + emit applied
 * 7. result 在弹窗关闭时重置
 * 8. addCashFlowYear / removeCashFlowYear / addRateCurvePeriod / removeRateCurvePeriod 操作
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

import FairValueTestDialog from '../FairValueTestDialog.vue'

beforeEach(() => {
  mockPost.mockReset()
})

const PROPS_BASE = {
  visible: true,
  projectId: 'proj-1',
  wpId: 'wp-1',
  targetSheet: '公允价值测试表G1-6',
  instrumentType: '交易性金融资产',
}

const STUBS = {
  'el-dialog': true, 'el-form': true, 'el-form-item': true,
  'el-radio-group': true, 'el-radio': true, 'el-radio-button': true,
  'el-input-number': true, 'el-input': true, 'el-divider': true,
  'el-table': true, 'el-table-column': true, 'el-button': true,
  'el-alert': true, 'el-descriptions': true, 'el-descriptions-item': true,
  'el-tag': true,
}

describe('FairValueTestDialog (G-F4)', () => {
  it('1. visible=true 时组件可挂载', () => {
    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('2. 表单默认值正确（Level 1 默认）', () => {
    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    expect(vm.form.level).toBe(1)
    expect(vm.form.instrument_type).toBe('交易性金融资产')
    expect(vm.form.face_value).toBe(1000000)
    expect(vm.form.market_price).toBe(1.0)
    expect(vm.form.interest_rate_curve).toHaveLength(5)
    expect(vm.form.cash_flow_projections).toHaveLength(5)
    expect(vm.result).toBeNull()
  })

  it('3a. Level 1 isFormValid：缺 market_price 时无效', () => {
    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.level = 1
    vm.form.market_price = null
    expect(vm.isFormValid).toBe(false)
    vm.form.market_price = 1.5
    expect(vm.isFormValid).toBe(true)
  })

  it('3b. Level 2 isFormValid：credit_spread 越界时无效', () => {
    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.level = 2
    vm.form.credit_spread = 1.5
    expect(vm.isFormValid).toBe(false)
    vm.form.credit_spread = 0.02
    expect(vm.isFormValid).toBe(true)
  })

  it('3c. Level 3 isFormValid：discount_rate 超 0~1 时无效', () => {
    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.level = 3
    vm.form.discount_rate = 0
    expect(vm.isFormValid).toBe(false)
    vm.form.discount_rate = 1
    expect(vm.isFormValid).toBe(false)
    vm.form.discount_rate = 0.10
    expect(vm.isFormValid).toBe(true)
  })

  it('3d. Level 3 isFormValid：所有现金流为 0 时无效', () => {
    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.level = 3
    vm.form.cash_flow_projections = [0, 0, 0, 0, 0]
    expect(vm.isFormValid).toBe(false)
  })

  it('4a. buildRequestBody Level 1：含 market_price + price_date', () => {
    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.level = 1
    vm.form.market_price = 2.5
    vm.form.price_date = '2026-05-19'
    const body = vm.buildRequestBody()
    expect(body.level).toBe(1)
    expect(body.market_price).toBe(2.5)
    expect(body.price_date).toBe('2026-05-19')
    expect(body.cash_flow_projections).toBeUndefined()
    expect(body.discount_rate).toBeUndefined()
    expect(body.credit_spread).toBeUndefined()
  })

  it('4b. buildRequestBody Level 2：含 interest_rate_curve + credit_spread + volatility', () => {
    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.level = 2
    const body = vm.buildRequestBody()
    expect(body.level).toBe(2)
    expect(body.interest_rate_curve).toHaveLength(5)
    expect(body.credit_spread).toBe(0.02)
    expect(body.volatility).toBe(0.15)
    expect(body.market_price).toBeUndefined()
  })

  it('4c. buildRequestBody Level 3：含 cash_flow_projections + discount_rate + terminal_value', () => {
    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.level = 3
    const body = vm.buildRequestBody()
    expect(body.level).toBe(3)
    expect(body.cash_flow_projections).toHaveLength(5)
    expect(body.discount_rate).toBe(0.10)
    expect(body.terminal_value).toBe(0)
    expect(body.market_price).toBeUndefined()
  })

  it('4d. buildRequestBody 含 apply_to_sheet 时序列化该字段', () => {
    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    const body = vm.buildRequestBody('公允价值测试表G1-6')
    expect(body.apply_to_sheet).toBe('公允价值测试表G1-6')
  })

  it('5. onAnalyze 调用正确 endpoint 并存储 result', async () => {
    const fakeResp = {
      level: 1,
      instrument_type: '交易性金融资产',
      face_value: '1000000',
      fair_value: '1500000.00',
      valuation_method: 'Level 1（活跃市场报价）',
      conclusion: '公允价值与面值偏离 50%，存在重大偏差需进一步核查',
      dcf_details: null,
      is_llm_stub: true,
      applied_to_sheet: null,
    }
    mockPost.mockResolvedValueOnce(fakeResp)

    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onAnalyze()

    expect(mockPost).toHaveBeenCalledWith(
      `/api/projects/proj-1/workpapers/wp-1/g/fair-value-test`,
      expect.objectContaining({
        level: 1,
        instrument_type: '交易性金融资产',
        face_value: 1000000,
      }),
    )
    expect(vm.result).toEqual(fakeResp)
  })

  it('6. onApplyToSheet 写回联动 + emit applied', async () => {
    const fakeResp = {
      level: 3,
      instrument_type: '交易性金融资产',
      face_value: '1000000',
      fair_value: '758157.35',
      valuation_method: 'Level 3 DCF',
      conclusion: 'OK',
      dcf_details: [],
      is_llm_stub: true,
      applied_to_sheet: '公允价值测试表G1-6',
    }
    mockPost.mockResolvedValueOnce(fakeResp)

    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onApplyToSheet()

    expect(mockPost).toHaveBeenCalledWith(
      `/api/projects/proj-1/workpapers/wp-1/g/fair-value-test`,
      expect.objectContaining({
        apply_to_sheet: '公允价值测试表G1-6',
      }),
    )
    const emitted = wrapper.emitted('applied')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual(['公允价值测试表G1-6'])
  })

  it('7. result 在弹窗关闭时重置', async () => {
    const wrapper = mount(FairValueTestDialog, {
      props: { ...PROPS_BASE, visible: true },
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.result = { level: 1, fair_value: '1.0' }
    await wrapper.setProps({ visible: false })
    expect(vm.result).toBeNull()
  })

  it('8a. addCashFlowYear / removeCashFlowYear 操作', () => {
    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    expect(vm.form.cash_flow_projections).toHaveLength(5)

    vm.addCashFlowYear()
    expect(vm.form.cash_flow_projections).toHaveLength(6)

    vm.removeCashFlowYear(5)
    expect(vm.form.cash_flow_projections).toHaveLength(5)

    // Cannot remove below 1
    vm.form.cash_flow_projections = [200000]
    vm.removeCashFlowYear(0)
    expect(vm.form.cash_flow_projections).toHaveLength(1)
  })

  it('8b. addRateCurvePeriod / removeRateCurvePeriod 操作', () => {
    const wrapper = mount(FairValueTestDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    expect(vm.form.interest_rate_curve).toHaveLength(5)

    vm.addRateCurvePeriod()
    expect(vm.form.interest_rate_curve).toHaveLength(6)

    vm.removeRateCurvePeriod(5)
    expect(vm.form.interest_rate_curve).toHaveLength(5)

    // Cannot remove below 1
    vm.form.interest_rate_curve = [0.025]
    vm.removeRateCurvePeriod(0)
    expect(vm.form.interest_rate_curve).toHaveLength(1)
  })

  it('9. onApplyToSheet 无 targetSheet 时不调 API', async () => {
    const wrapper = mount(FairValueTestDialog, {
      props: { ...PROPS_BASE, targetSheet: '' },
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onApplyToSheet()
    expect(mockPost).not.toHaveBeenCalled()
  })
})
