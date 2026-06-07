/**
 * CompletenessBanner — Task 10.4 vitest 单测
 * Spec: .kiro/specs/audit-report-deliverable-center/ Task 10.4
 *
 * 验证（需求 3.7 / 8.2 / 19.3）：
 * 1. passed=true → 渲染成功态 + 通过文案
 * 2. passed=false 且有缺失/不一致 warnings → 渲染警告态并展示 warnings
 * 3. 三件套不一致（trio_consistent=false）→ 警告文案包含一致性提示
 * 4. API 失败 → 静默不崩、不显示成功态
 * 5. 不通过时点击「重新检查」触发再次拉取
 * 6. projectId/year 切换触发重新加载
 * 7. expose refresh() 可主动刷新
 */
import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockFetchCompleteness } = vi.hoisted(() => ({
  mockFetchCompleteness: vi.fn(),
}))

vi.mock('@/services/deliverableApi', () => ({
  fetchCompleteness: (...args: any[]) => mockFetchCompleteness(...args),
}))

import CompletenessBanner from '../CompletenessBanner.vue'

const stubAlert = {
  template:
    '<div class="cmp-banner-stub" :data-type="type"><slot name="title" /></div>',
  props: ['type', 'showIcon', 'closable'],
}

const stubButton = {
  template: '<button class="cmp-recheck" @click="$emit(\'click\', $event)"><slot /></button>',
  props: ['type', 'size', 'text'],
  emits: ['click'],
}

function makeBanner(props: Record<string, any> = {}) {
  return mount(CompletenessBanner, {
    props: { projectId: 'p1', year: 2024, ...props },
    global: {
      stubs: {
        'el-alert': stubAlert,
        'el-button': stubButton,
      },
    },
  })
}

function passedResult() {
  return {
    passed: true,
    missing_doc_types: [],
    missing_financial_reports: [],
    has_confirmed: true,
    trio_consistent: true,
    trio_message: null,
    warnings: [],
  }
}

function failedResult(overrides: Record<string, any> = {}) {
  return {
    passed: false,
    missing_doc_types: ['disclosure_notes'],
    missing_financial_reports: [],
    has_confirmed: false,
    trio_consistent: true,
    trio_message: null,
    warnings: ['缺失交付物类型: disclosure_notes'],
    ...overrides,
  }
}

describe('CompletenessBanner', () => {
  beforeEach(() => {
    mockFetchCompleteness.mockReset()
  })

  it('passed=true 渲染成功态与通过文案', async () => {
    mockFetchCompleteness.mockResolvedValue(passedResult())
    const wrapper = makeBanner()
    await flushPromises()
    expect(mockFetchCompleteness).toHaveBeenCalledWith('p1', 2024)
    const banner = wrapper.find('.cmp-banner-stub')
    expect(banner.exists()).toBe(true)
    expect(banner.attributes('data-type')).toBe('success')
    expect(wrapper.text()).toContain('通过')
  })

  it('passed=false 渲染警告态并展示缺失 warnings', async () => {
    mockFetchCompleteness.mockResolvedValue(failedResult())
    const wrapper = makeBanner()
    await flushPromises()
    const banner = wrapper.find('.cmp-banner-stub')
    expect(banner.attributes('data-type')).toBe('warning')
    expect(wrapper.text()).toContain('未通过')
    expect(wrapper.text()).toContain('disclosure_notes')
  })

  it('三件套不一致时展示一致性警告（需求 19.3）', async () => {
    mockFetchCompleteness.mockResolvedValue(
      failedResult({
        missing_doc_types: [],
        trio_consistent: false,
        trio_message: '三件套绑定的数据快照不一致，请重新生成滞后的交付物',
        warnings: ['三件套绑定的数据快照不一致，请重新生成滞后的交付物'],
      }),
    )
    const wrapper = makeBanner()
    await flushPromises()
    expect(wrapper.find('.cmp-banner-stub').attributes('data-type')).toBe('warning')
    expect(wrapper.text()).toContain('数据快照不一致')
  })

  it('API 失败时静默不崩、不显示成功态', async () => {
    mockFetchCompleteness.mockRejectedValue(new Error('500'))
    const wrapper = makeBanner()
    await flushPromises()
    // loaded 为 true 但 result 为 null → 渲染 warning 态（非 success）
    const banner = wrapper.find('.cmp-banner-stub')
    expect(banner.exists()).toBe(true)
    expect(banner.attributes('data-type')).toBe('warning')
  })

  it('不通过时点击「重新检查」触发再次拉取', async () => {
    mockFetchCompleteness.mockResolvedValue(failedResult())
    const wrapper = makeBanner()
    await flushPromises()
    expect(mockFetchCompleteness).toHaveBeenCalledTimes(1)

    const btn = wrapper.find('.cmp-recheck')
    expect(btn.exists()).toBe(true)
    await btn.trigger('click')
    await flushPromises()
    expect(mockFetchCompleteness).toHaveBeenCalledTimes(2)
  })

  it('projectId/year 切换触发重新加载', async () => {
    mockFetchCompleteness.mockResolvedValue(passedResult())
    const wrapper = makeBanner({ projectId: 'p1', year: 2024 })
    await flushPromises()
    expect(mockFetchCompleteness).toHaveBeenLastCalledWith('p1', 2024)

    await wrapper.setProps({ projectId: 'p2', year: 2025 })
    await flushPromises()
    expect(mockFetchCompleteness).toHaveBeenLastCalledWith('p2', 2025)
  })

  it('expose refresh() 主动刷新', async () => {
    mockFetchCompleteness.mockResolvedValueOnce(failedResult())
    const wrapper = makeBanner()
    await flushPromises()
    expect(wrapper.find('.cmp-banner-stub').attributes('data-type')).toBe('warning')

    mockFetchCompleteness.mockResolvedValueOnce(passedResult())
    await (wrapper.vm as any).refresh()
    await flushPromises()
    expect(wrapper.find('.cmp-banner-stub').attributes('data-type')).toBe('success')
  })
})
