import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: mockGet } }))

import ReportProvenanceTooltip from '../ReportProvenanceTooltip.vue'

const ElTooltipStub = defineComponent({
  name: 'ElTooltip',
  emits: ['before-show'],
  template: '<div class="tooltip-stub"><div class="content"><slot name="content" /></div><slot /></div>',
})

describe('ReportProvenanceTooltip', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  function mountTooltip(extraProps: Record<string, unknown> = {}) {
    return mount(ReportProvenanceTooltip, {
      props: {
        projectId: 'p1', year: 2025, reportType: 'balance_sheet', rowCode: 'BS-001',
        formula: "TB('1001','期末余额')", ...extraProps,
      },
      slots: { default: '<span class="amount">12.30</span>' },
      global: { stubs: { ElTooltip: ElTooltipStub } },
    })
  }

  it('首次展开只请求一次并显示已应用来源、定义和输入摘要', async () => {
    mockGet.mockResolvedValue({
      value: '12.30',
      envelope: {
        value_state: 'auto',
        calculation_applied: true,
        last_calculation: {
          calculation_status: 'succeeded',
          computed_at: '2026-01-01T00:00:00Z',
          definition_ref: { kind: 'report_config', id: 'cfg-1' },
          definition_version: 3,
          definition_layer: 'project',
          input_count: 2,
          input_digest: 'abcdef1234567890',
        },
      },
      stale: false,
      legacy: false,
      inputs_redacted: false,
    })
    const wrapper = mountTooltip()
    wrapper.findComponent(ElTooltipStub).vm.$emit('before-show')
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.content').text()).toContain('自动计算并已采用')
    expect(wrapper.find('.content').text()).toContain('report_config · cfg-1')
    expect(wrapper.find('.content').text()).toContain('2 项')
    expect(wrapper.find('.content').text()).toContain("TB('1001','期末余额')")

    wrapper.findComponent(ElTooltipStub).vm.$emit('before-show')
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('显示未采用计算、过期和输入脱敏状态', async () => {
    mockGet.mockResolvedValue({
      value: '10.00',
      envelope: {
        value_state: 'locked',
        calculation_applied: false,
        last_calculation: { calculation_status: 'succeeded', input_count: 1, input_digest: 'digest' },
      },
      stale: true,
      legacy: false,
      inputs_redacted: true,
    })
    const wrapper = mountTooltip({ rowCode: 'BS-002' })
    wrapper.findComponent(ElTooltipStub).vm.$emit('before-show')
    await flushPromises()
    const text = wrapper.find('.content').text()
    expect(text).toContain('已锁定')
    expect(text).toContain('部分跨项目输入因权限已脱敏')
    expect(text).toContain('当前定义或计算版本已变化')
  })
})


describe('ReportProvenanceTooltip 缓存代际', () => {
  beforeEach(() => {
    mockGet.mockReset()
  })

  it('同一报表行出现新的 attempt_id 后重新读取，不显示旧运行信封', async () => {
    mockGet
      .mockResolvedValueOnce({ value: '1.00', legacy: false, envelope: { value_state: 'auto', last_calculation: { input_count: 1 } } })
      .mockResolvedValueOnce({ value: '1.00', legacy: false, envelope: { value_state: 'auto', last_calculation: { input_count: 2 } } })
    const wrapper = mount(ReportProvenanceTooltip, {
      props: {
        projectId: 'p1', year: 2025, reportType: 'balance_sheet', rowCode: 'BS-003', attemptId: 'attempt-a',
      },
      global: { stubs: { ElTooltip: ElTooltipStub } },
    })
    wrapper.findComponent(ElTooltipStub).vm.$emit('before-show')
    await flushPromises()
    expect(wrapper.find('.content').text()).toContain('1 项')

    await wrapper.setProps({ attemptId: 'attempt-b' })
    wrapper.findComponent(ElTooltipStub).vm.$emit('before-show')
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(2)
    expect(wrapper.find('.content').text()).toContain('2 项')
  })
})
