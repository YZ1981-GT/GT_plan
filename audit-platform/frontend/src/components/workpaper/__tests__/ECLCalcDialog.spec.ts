/**
 * ECLCalcDialog.spec.ts — G-investment-cycle G-F5 Task 2.9
 *
 * 烟测目标：
 * 1. visible=true 时组件可挂载
 * 2. 表单默认值（stage=1 默认 + 默认 PD/LGD）
 * 3. isFormValid 校验逻辑（含 pd_12m ≤ pd_lifetime 约束）
 * 4. buildRequestBody 序列化 stage / book_value / pd_12m / pd_lifetime / lgd
 * 5. 调用 ecl-calc API 后渲染 result 区
 * 6. onApplyToSheet 写回联动 + emit applied
 * 7. result 在弹窗关闭时重置
 * 8. stagePreview 三阶段客户端预估 + 单调性预检
 * 9. onApplyToSheet 无 targetSheet 时不调 API
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

import ECLCalcDialog from '../ECLCalcDialog.vue'

beforeEach(() => {
  mockPost.mockReset()
})

const PROPS_BASE = {
  visible: true,
  projectId: 'proj-1',
  wpId: 'wp-1',
  targetSheet: '减值测试G4-3',
  instrumentType: '债权投资',
}

const STUBS = {
  'el-dialog': true, 'el-form': true, 'el-form-item': true,
  'el-radio-group': true, 'el-radio': true, 'el-radio-button': true,
  'el-input-number': true, 'el-input': true, 'el-divider': true,
  'el-table': true, 'el-table-column': true, 'el-button': true,
  'el-alert': true, 'el-descriptions': true, 'el-descriptions-item': true,
  'el-tag': true,
}

describe('ECLCalcDialog (G-F5)', () => {
  it('1. visible=true 时组件可挂载', () => {
    const wrapper = mount(ECLCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('2. 表单默认值正确（stage=1 默认）', () => {
    const wrapper = mount(ECLCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    expect(vm.form.stage).toBe(1)
    expect(vm.form.instrument_type).toBe('债权投资')
    expect(vm.form.book_value).toBe(1000000)
    expect(vm.form.pd_12m).toBe(0.02)
    expect(vm.form.pd_lifetime).toBe(0.10)
    expect(vm.form.lgd).toBe(0.45)
    expect(vm.result).toBeNull()
  })

  it('3a. isFormValid：合法输入返回 true', () => {
    const wrapper = mount(ECLCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    expect(vm.isFormValid).toBe(true)
  })

  it('3b. isFormValid：pd_12m > pd_lifetime 时无效', () => {
    const wrapper = mount(ECLCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.pd_12m = 0.5
    vm.form.pd_lifetime = 0.1
    expect(vm.isFormValid).toBe(false)
  })

  it('3c. isFormValid：lgd 越界时无效', () => {
    const wrapper = mount(ECLCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.lgd = 1.5
    expect(vm.isFormValid).toBe(false)
    vm.form.lgd = -0.1
    expect(vm.isFormValid).toBe(false)
    vm.form.lgd = 0.45
    expect(vm.isFormValid).toBe(true)
  })

  it('3d. isFormValid：book_value <= 0 时无效', () => {
    const wrapper = mount(ECLCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.book_value = 0
    expect(vm.isFormValid).toBe(false)
  })

  it('4. buildRequestBody 序列化所有字段', () => {
    const wrapper = mount(ECLCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.stage = 2
    vm.form.book_value = 500000
    vm.form.pd_12m = 0.03
    vm.form.pd_lifetime = 0.15
    vm.form.lgd = 0.50

    const body = vm.buildRequestBody()
    expect(body.stage).toBe(2)
    expect(body.book_value).toBe(500000)
    expect(body.pd_12m).toBe(0.03)
    expect(body.pd_lifetime).toBe(0.15)
    expect(body.lgd).toBe(0.50)
    expect(body.apply_to_sheet).toBeUndefined()

    const bodyWithSheet = vm.buildRequestBody('减值测试G4-3')
    expect(bodyWithSheet.apply_to_sheet).toBe('减值测试G4-3')
  })

  it('5. onAnalyze 调用正确 endpoint 并存储 result', async () => {
    const fakeResp = {
      stage: 1,
      ecl_amount: '900.00',
      formula_used: 'Stage 1: ECL = EAD × PD_12m × LGD = 1000000 × 0.02 × 0.45',
      monotonicity_check: true,
      is_llm_stub: false,
      applied_to_sheet: null,
    }
    mockPost.mockResolvedValueOnce(fakeResp)

    const wrapper = mount(ECLCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onAnalyze()

    expect(mockPost).toHaveBeenCalledWith(
      `/api/projects/proj-1/workpapers/wp-1/g/ecl-calc`,
      expect.objectContaining({
        stage: 1,
        book_value: 1000000,
        pd_12m: 0.02,
        pd_lifetime: 0.10,
        lgd: 0.45,
      }),
    )
    expect(vm.result).toEqual(fakeResp)
  })

  it('6. onApplyToSheet 写回联动 + emit applied', async () => {
    const fakeResp = {
      stage: 2,
      ecl_amount: '4500.00',
      formula_used: 'Stage 2: ECL = EAD × PD_lifetime × LGD = 1000000 × 0.10 × 0.045',
      monotonicity_check: true,
      is_llm_stub: false,
      applied_to_sheet: '减值测试G4-3',
    }
    mockPost.mockResolvedValueOnce(fakeResp)

    const wrapper = mount(ECLCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.form.stage = 2
    await vm.onApplyToSheet()

    expect(mockPost).toHaveBeenCalledWith(
      `/api/projects/proj-1/workpapers/wp-1/g/ecl-calc`,
      expect.objectContaining({
        stage: 2,
        apply_to_sheet: '减值测试G4-3',
      }),
    )
    const emitted = wrapper.emitted('applied')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual(['减值测试G4-3'])
  })

  it('7. result 在弹窗关闭时重置', async () => {
    const wrapper = mount(ECLCalcDialog, {
      props: { ...PROPS_BASE, visible: true },
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.result = { stage: 1, ecl_amount: '900.00' }
    await wrapper.setProps({ visible: false })
    expect(vm.result).toBeNull()
  })

  it('8a. stagePreview 三阶段客户端估算正确', () => {
    const wrapper = mount(ECLCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    // 默认值：1000000 × 0.02 × 0.45 = 9000；1000000 × 0.10 × 0.45 = 45000
    const preview = vm.stagePreview
    expect(preview).toHaveLength(3)
    expect(preview[0].stage).toBe(1)
    expect(preview[0].ecl).toBeCloseTo(9000, 2)
    expect(preview[1].stage).toBe(2)
    expect(preview[1].ecl).toBeCloseTo(45000, 2)
    expect(preview[2].stage).toBe(3)
    expect(preview[2].ecl).toBeCloseTo(45000, 2)
  })

  it('8b. previewMonotonicityOk：pd_12m ≤ pd_lifetime 时 ok', () => {
    const wrapper = mount(ECLCalcDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    expect(vm.previewMonotonicityOk).toBe(true)
    vm.form.pd_12m = 0.5
    vm.form.pd_lifetime = 0.1
    expect(vm.previewMonotonicityOk).toBe(false)
  })

  it('9. onApplyToSheet 无 targetSheet 时不调 API', async () => {
    const wrapper = mount(ECLCalcDialog, {
      props: { ...PROPS_BASE, targetSheet: '' },
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onApplyToSheet()
    expect(mockPost).not.toHaveBeenCalled()
  })
})
