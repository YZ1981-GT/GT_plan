/**
 * DepreciationCalcDialog.spec.ts — Sprint 3 Task 3.2 (H-F11)
 *
 * 烟测目标：
 * 1. visible=true 时组件可挂载
 * 2. 表单默认值（method=straight_line / original_cost=100000 / residual_rate=0.05 / useful_life_months=60）
 * 3. isFormValid 校验逻辑
 * 4. 调用 depreciation-calc API 后渲染 result 区
 * 5. onApplyToSheet 写回联动
 * 6. result 在弹窗关闭时重置
 * 7. 工作量法字段校验
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

import DepreciationCalcDialog from '../DepreciationCalcDialog.vue'

beforeEach(() => {
  mockPost.mockReset()
})

const PROPS_BASE = {
  visible: true,
  projectId: 'proj-1',
  wpId: 'wp-1',
  targetSheet: '折旧测算表（不含减值）-直线法H1-12',
}

const STUBS = {
  'el-dialog': true, 'el-form': true, 'el-form-item': true,
  'el-radio-group': true, 'el-radio': true, 'el-input-number': true,
  'el-input': true, 'el-divider': true, 'el-table': true,
  'el-table-column': true, 'el-button': true, 'el-alert': true,
  'el-descriptions': true, 'el-descriptions-item': true,
}

describe('DepreciationCalcDialog (H-F11)', () => {
  it('1. visible=true 时组件可挂载', () => {
    const wrapper = mount(DepreciationCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('2. 表单默认值正确', () => {
    const wrapper = mount(DepreciationCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    expect(vm.form.method).toBe('straight_line')
    expect(vm.form.original_cost).toBe(100000)
    expect(vm.form.residual_rate).toBe(0.05)
    expect(vm.form.useful_life_months).toBe(60)
    expect(vm.form.start_month).toBe(1)
    expect(vm.form.already_depreciated_months).toBe(0)
    expect(vm.result).toBeNull()
  })

  it('3. isFormValid 校验：原值 <= 0 时无效', () => {
    const wrapper = mount(DepreciationCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.original_cost = 0
    expect(vm.isFormValid).toBe(false)
    vm.form.original_cost = 100000
    expect(vm.isFormValid).toBe(true)
  })

  it('4. onCalc 调用 API 并存储 result', async () => {
    const fakeResp = {
      method: 'straight_line',
      monthly_schedule: [
        { month: 1, depreciation: '1583.33', accumulated: '1583.33' },
        { month: 2, depreciation: '1583.33', accumulated: '3166.66' },
      ],
      total_depreciation: '95000.00',
      remaining_book_value: '0.00',
      applied_to_sheet: null,
    }
    mockPost.mockResolvedValueOnce(fakeResp)

    const wrapper = mount(DepreciationCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onCalc()

    expect(mockPost).toHaveBeenCalledWith(
      `/api/projects/proj-1/workpapers/wp-1/h1/depreciation-calc`,
      expect.objectContaining({
        method: 'straight_line',
        original_cost: 100000,
        residual_rate: 0.05,
        useful_life_months: 60,
        start_month: 1,
        already_depreciated_months: 0,
      }),
    )
    expect(vm.result).toEqual(fakeResp)
  })

  it('5. onApplyToSheet 写回联动 + emit applied', async () => {
    const fakeResp = {
      method: 'straight_line',
      monthly_schedule: [{ month: 1, depreciation: '1583.33', accumulated: '1583.33' }],
      total_depreciation: '95000.00',
      remaining_book_value: '0.00',
      applied_to_sheet: '折旧测算表（不含减值）-直线法H1-12',
    }
    mockPost.mockResolvedValueOnce(fakeResp)

    const wrapper = mount(DepreciationCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onApplyToSheet()

    expect(mockPost).toHaveBeenCalledWith(
      `/api/projects/proj-1/workpapers/wp-1/h1/depreciation-calc`,
      expect.objectContaining({
        apply_to_sheet: '折旧测算表（不含减值）-直线法H1-12',
        method: 'straight_line',
      }),
    )
    const emitted = wrapper.emitted('applied')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual(['折旧测算表（不含减值）-直线法H1-12'])
  })

  it('6. result 在弹窗关闭时重置', async () => {
    const wrapper = mount(DepreciationCalcDialog, {
      props: { ...PROPS_BASE, visible: true },
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.result = { method: 'straight_line', monthly_schedule: [], total_depreciation: '0', remaining_book_value: '0' }
    await wrapper.setProps({ visible: false })
    expect(vm.result).toBeNull()
  })

  it('7. 工作量法字段校验：total_units=0 时 isFormValid=false', () => {
    const wrapper = mount(DepreciationCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.method = 'units_of_production'
    vm.form.total_units = 0
    expect(vm.isFormValid).toBe(false)
    vm.form.total_units = 10000
    vm.form.current_period_units = 500
    expect(vm.isFormValid).toBe(true)
  })

  it('8. onApplyToSheet 无 targetSheet 时不调 API', async () => {
    const wrapper = mount(DepreciationCalcDialog, {
      props: { ...PROPS_BASE, targetSheet: '' },
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onApplyToSheet()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('9. methodLabel 映射正确', () => {
    const wrapper = mount(DepreciationCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    expect(vm.methodLabel('straight_line')).toBe('直线法')
    expect(vm.methodLabel('double_declining')).toBe('双倍余额递减法')
    expect(vm.methodLabel('sum_of_years')).toBe('年数总和法')
    expect(vm.methodLabel('units_of_production')).toBe('工作量法')
  })

  it('10. schedulePreview 最多显示 12 条', () => {
    const wrapper = mount(DepreciationCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    // 模拟 60 条 schedule
    vm.result = {
      method: 'straight_line',
      monthly_schedule: Array.from({ length: 60 }, (_, i) => ({
        month: i + 1,
        depreciation: '1583.33',
        accumulated: String((i + 1) * 1583.33),
      })),
      total_depreciation: '95000.00',
      remaining_book_value: '0.00',
    }
    expect(vm.schedulePreview).toHaveLength(12)
  })
})
