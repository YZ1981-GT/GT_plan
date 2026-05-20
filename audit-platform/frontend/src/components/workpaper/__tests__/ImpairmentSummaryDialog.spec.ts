/**
 * ImpairmentSummaryDialog.spec.ts — k-admin-cycle-post-review-fix Task 3.3
 *
 * 烟测目标（参照 ExpenseAnalysisDialog.spec.ts 模式）：
 * 1. mount — visible=true 时组件可挂载
 * 2. form 默认值 — year 默认为当前年份，result 初始为 null
 * 3. onCalc — 调用正确的 k11/impairment-summary endpoint
 * 4. result 显示 — 4 类来源（H1/I3/G14/F2）可从 result 状态访问
 * 5. onApplyToSheet — 后端返回 applied_to_sheet 时 emit applied
 * 6. visible=false 时 result 重置（watch on visible）
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

import ImpairmentSummaryDialog from '../ImpairmentSummaryDialog.vue'

beforeEach(() => {
  mockPost.mockReset()
})

const PROPS_BASE = {
  visible: true,
  projectId: 'proj-1',
  wpId: 'wp-1',
  targetSheet: '审定表K11-1',
}

const STUBS = {
  'el-dialog': true, 'el-form': true, 'el-form-item': true,
  'el-input-number': true, 'el-divider': true,
  'el-table': true, 'el-table-column': true, 'el-button': true,
  'el-alert': true, 'el-descriptions': true, 'el-descriptions-item': true,
  'el-tag': true,
}

const FAKE_RESP_FULL = {
  impairment_by_type: [
    { asset_type: '固定资产', amount: 100000, source_wp: 'H1', source_sheet: '减值测试表H1-14' },
    { asset_type: '商誉', amount: 200000, source_wp: 'I3', source_sheet: '商誉减值测试表I3-1' },
    { asset_type: '应收款项（信用减值）', amount: 50000, source_wp: 'G14', source_sheet: '应收款项-信用减值表G14' },
    { asset_type: '存货跌价', amount: 30000, source_wp: 'F2', source_sheet: '存货跌价测试表F2-12' },
  ],
  total_impairment: 380000,
  sources_found: ['H1', 'I3', 'G14', 'F2'],
  sources_missing: [],
  summary: '4 个来源全部命中，合计 ¥380,000.00',
  is_llm_stub: true,
  applied_to_sheet: null,
}

describe('ImpairmentSummaryDialog (K-F8)', () => {
  it('1. visible=true 时组件可挂载', () => {
    const wrapper = mount(ImpairmentSummaryDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('2. 表单默认值正确（year=当前年份，result=null）', () => {
    const wrapper = mount(ImpairmentSummaryDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    expect(vm.form.year).toBe(new Date().getFullYear())
    expect(vm.result).toBeNull()
  })

  it('3. onCalc 调用正确 k11/impairment-summary endpoint', async () => {
    mockPost.mockResolvedValueOnce(FAKE_RESP_FULL)

    const wrapper = mount(ImpairmentSummaryDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onCalc()

    expect(mockPost).toHaveBeenCalledWith(
      '/api/projects/proj-1/workpapers/wp-1/k11/impairment-summary',
      expect.objectContaining({
        year: expect.any(Number),
        apply_to_sheet: null,
      }),
    )
    expect(vm.result).toEqual(FAKE_RESP_FULL)
  })

  it('4. result 中 4 类来源（H1/I3/G14/F2）数据可访问', async () => {
    mockPost.mockResolvedValueOnce(FAKE_RESP_FULL)

    const wrapper = mount(ImpairmentSummaryDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onCalc()

    expect(vm.result.sources_found).toEqual(['H1', 'I3', 'G14', 'F2'])
    expect(vm.result.total_impairment).toBe(380000)
    const sourceWps = vm.result.impairment_by_type.map((r: any) => r.source_wp)
    expect(sourceWps).toEqual(['H1', 'I3', 'G14', 'F2'])
    expect(vm.result.is_llm_stub).toBe(true)
  })

  it('5. onApplyToSheet：返回 applied_to_sheet 时 emit applied', async () => {
    const fakeRespApplied = { ...FAKE_RESP_FULL, applied_to_sheet: '审定表K11-1' }
    mockPost.mockResolvedValueOnce(fakeRespApplied)

    const wrapper = mount(ImpairmentSummaryDialog, {
      props: PROPS_BASE,
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    await vm.onApplyToSheet()

    expect(mockPost).toHaveBeenCalledWith(
      '/api/projects/proj-1/workpapers/wp-1/k11/impairment-summary',
      expect.objectContaining({ apply_to_sheet: '审定表K11-1' }),
    )
    const emitted = wrapper.emitted('applied')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual(['审定表K11-1'])
  })

  it('6. result 在弹窗关闭（visible=false）时重置', async () => {
    const wrapper = mount(ImpairmentSummaryDialog, {
      props: { ...PROPS_BASE, visible: true },
      global: { stubs: STUBS },
    })
    const vm = wrapper.vm as any
    vm.result = FAKE_RESP_FULL
    expect(vm.result).not.toBeNull()
    await wrapper.setProps({ visible: false })
    expect(vm.result).toBeNull()
  })
})
