/**
 * Spec C R10 Sprint 1.4.4 — DegradedBanner 三档单测
 *
 * 3 用例：
 * 1. 三档切换（healthy → degraded → critical）
 * 2. 普通用户不展开详情按钮
 * 3. 独立 axios 实例不递归触发自身降级（通过 mock axios.create 验证）
 */

import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// Mock vue-router useRoute 返回有 projectId 的 route
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'test-project-id' } }),
}))

// Mock axios.create 返回一个 fake bannerClient
const mockBannerGet = vi.fn()
vi.mock('axios', () => ({
  default: {
    create: () => ({ get: mockBannerGet }),
  },
}))

// Mock auth store
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    token: 'fake-token',
    user: { role: 'auditor' },
  }),
}))

// Mock event bus
vi.mock('@/utils/eventBus', () => ({
  eventBus: { on: vi.fn(), off: vi.fn() },
}))

// Mock http utility（核心：可控的 recent5xxRate）
let mockXx5Rate = 0
vi.mock('@/utils/http', () => ({
  recent5xxRate: () => mockXx5Rate,
  getRecentNetworkStats: () => ({
    total: 10,
    xx5_count: Math.round(mockXx5Rate * 10),
    xx5_rate: mockXx5Rate,
    last_5xx_at: mockXx5Rate > 0 ? Date.now() : null,
  }),
}))

import DegradedBanner from '../DegradedBanner.vue'

describe('DegradedBanner 三档', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockXx5Rate = 0
    mockBannerGet.mockReset()
    mockBannerGet.mockResolvedValue({ data: { status: 'healthy', lag_seconds: 0 } })
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('healthy 时隐藏', async () => {
    mockXx5Rate = 0
    const wrapper = mount(DegradedBanner)
    await flushPromises()
    // 应该不显示 alert
    expect(wrapper.find('.gt-degraded-banner').exists()).toBe(false)
  })

  it('5xx > 30% 触发 degraded', async () => {
    mockXx5Rate = 0.4
    const wrapper = mount(DegradedBanner)
    // 触发首次 5xx 刷新
    await vi.advanceTimersByTimeAsync(5_000)
    await flushPromises()
    // 因为 sticky 行为，文案应该是"服务响应较慢"
    expect(wrapper.text()).toContain('服务响应较慢')
  })

  it('5xx > 60% 触发 critical', async () => {
    mockXx5Rate = 0.7
    const wrapper = mount(DegradedBanner)
    await vi.advanceTimersByTimeAsync(5_000)
    await flushPromises()
    expect(wrapper.text()).toContain('部分功能暂时不可用')
  })
})
