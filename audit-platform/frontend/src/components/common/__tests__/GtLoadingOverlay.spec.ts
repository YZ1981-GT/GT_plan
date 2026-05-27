/**
 * GtLoadingOverlay — 加载蒙层组件单测
 *
 * 验证：
 * - visible=false 时不渲染
 * - visible=true 时渲染蒙层 + 图标
 * - 5s 超时后显示「加载较慢」提示
 * - visible 变为 false 时清除 timer + 隐藏慢提示
 * - 自定义 slowThresholdMs + slowHintText
 *
 * Validates: Requirements 8.2.3
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtLoadingOverlay from '../GtLoadingOverlay.vue'

// Stub el-icon to avoid element-plus rendering issues
const STUBS = {
  'el-icon': {
    name: 'ElIcon',
    template: '<span class="el-icon-stub"><slot /></span>',
    props: ['size', 'color'],
  },
  Loading: {
    name: 'Loading',
    template: '<i class="loading-icon-stub" />',
  },
}

describe('GtLoadingOverlay', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('visible=false 时不渲染', () => {
    const wrapper = mount(GtLoadingOverlay, {
      props: { visible: false },
      global: { stubs: STUBS },
    })
    expect(wrapper.find('.gt-loading-overlay').exists()).toBe(false)
  })

  it('visible=true 时渲染蒙层', () => {
    const wrapper = mount(GtLoadingOverlay, {
      props: { visible: true, text: '加载中...' },
      global: { stubs: STUBS },
    })
    expect(wrapper.find('.gt-loading-overlay').exists()).toBe(true)
    expect(wrapper.find('.gt-loading-overlay__text').text()).toBe('加载中...')
  })

  it('5s 超时后显示慢加载提示', async () => {
    const wrapper = mount(GtLoadingOverlay, {
      props: { visible: true },
      global: { stubs: STUBS },
    })

    // 初始不显示慢提示
    expect(wrapper.find('.gt-loading-overlay__slow-hint').exists()).toBe(false)

    // 4.9s 后仍不显示
    vi.advanceTimersByTime(4900)
    await nextTick()
    expect(wrapper.find('.gt-loading-overlay__slow-hint').exists()).toBe(false)

    // 5s 后显示
    vi.advanceTimersByTime(100)
    await nextTick()
    expect(wrapper.find('.gt-loading-overlay__slow-hint').exists()).toBe(true)
    expect(wrapper.find('.gt-loading-overlay__slow-hint').text()).toBe('加载较慢，请耐心等待')
  })

  it('visible 变为 false 时清除 timer 并隐藏慢提示', async () => {
    const wrapper = mount(GtLoadingOverlay, {
      props: { visible: true },
      global: { stubs: STUBS },
    })

    // 先触发慢提示
    vi.advanceTimersByTime(5000)
    await nextTick()
    expect(wrapper.find('.gt-loading-overlay__slow-hint').exists()).toBe(true)

    // 隐藏蒙层
    await wrapper.setProps({ visible: false })
    await nextTick()

    // 整个蒙层不渲染
    expect(wrapper.find('.gt-loading-overlay').exists()).toBe(false)

    // 重新显示时慢提示应重置
    await wrapper.setProps({ visible: true })
    await nextTick()
    expect(wrapper.find('.gt-loading-overlay').exists()).toBe(true)
    expect(wrapper.find('.gt-loading-overlay__slow-hint').exists()).toBe(false)
  })

  it('自定义 slowThresholdMs 和 slowHintText', async () => {
    const wrapper = mount(GtLoadingOverlay, {
      props: {
        visible: true,
        slowThresholdMs: 3000,
        slowHintText: '网络较慢，请稍候',
      },
      global: { stubs: STUBS },
    })

    // 2.9s 后不显示
    vi.advanceTimersByTime(2900)
    await nextTick()
    expect(wrapper.find('.gt-loading-overlay__slow-hint').exists()).toBe(false)

    // 3s 后显示自定义文本
    vi.advanceTimersByTime(100)
    await nextTick()
    expect(wrapper.find('.gt-loading-overlay__slow-hint').exists()).toBe(true)
    expect(wrapper.find('.gt-loading-overlay__slow-hint').text()).toBe('网络较慢，请稍候')
  })
})
