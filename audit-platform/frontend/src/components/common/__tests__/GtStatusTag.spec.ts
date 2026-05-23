/**
 * GtStatusTag — flip 动画集成单测
 *
 * 对应 [proposal-remaining-18 task 5.5 UI-8]：
 * gt-polish.css 已定义 `.gt-tag-flip` / `.is-flipping` keyframe（400ms），
 * 此处验证业务组件 GtStatusTag 在 value 变化时正确添加/移除 .is-flipping 类。
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import GtStatusTag from '../GtStatusTag.vue'

// el-tag stub：保留 class binding（含 is-flipping）+ slot 内容
const STUBS = {
  'el-tag': {
    name: 'ElTag',
    inheritAttrs: true,
    template: '<span class="el-tag-stub"><slot /></span>',
    props: ['type', 'size', 'effect'],
  },
}

describe('GtStatusTag - flip 动画', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('首次挂载不触发 flip（oldVal === undefined）', async () => {
    const wrapper = mount(GtStatusTag, {
      props: { dictKey: 'wp_status', value: 'draft' },
      global: { stubs: STUBS },
    })
    await nextTick()
    expect(wrapper.find('.el-tag-stub').classes()).not.toContain('is-flipping')
  })

  it('value 变化后立即添加 is-flipping 类', async () => {
    const wrapper = mount(GtStatusTag, {
      props: { dictKey: 'wp_status', value: 'draft' },
      global: { stubs: STUBS },
    })
    await nextTick()
    await wrapper.setProps({ value: 'edit_complete' })
    await nextTick()
    expect(wrapper.find('.el-tag-stub').classes()).toContain('is-flipping')
  })

  it('400ms 后 is-flipping 类自动移除', async () => {
    const wrapper = mount(GtStatusTag, {
      props: { dictKey: 'wp_status', value: 'draft' },
      global: { stubs: STUBS },
    })
    await nextTick()
    await wrapper.setProps({ value: 'edit_complete' })
    await nextTick()
    expect(wrapper.find('.el-tag-stub').classes()).toContain('is-flipping')

    // 推进 200ms：仍保留 is-flipping
    vi.advanceTimersByTime(200)
    await nextTick()
    expect(wrapper.find('.el-tag-stub').classes()).toContain('is-flipping')

    // 推进至 400ms：is-flipping 已移除
    vi.advanceTimersByTime(200)
    await nextTick()
    expect(wrapper.find('.el-tag-stub').classes()).not.toContain('is-flipping')
  })

  it('value 相同时不重新触发动画', async () => {
    const wrapper = mount(GtStatusTag, {
      props: { dictKey: 'wp_status', value: 'draft' },
      global: { stubs: STUBS },
    })
    await nextTick()
    // 设为相同值不应触发
    await wrapper.setProps({ value: 'draft' })
    await nextTick()
    expect(wrapper.find('.el-tag-stub').classes()).not.toContain('is-flipping')
  })

  it('快速连续切换：旧 timer 被清理，新 timer 重新计时', async () => {
    const wrapper = mount(GtStatusTag, {
      props: { dictKey: 'wp_status', value: 'draft' },
      global: { stubs: STUBS },
    })
    await nextTick()

    // 第一次切换
    await wrapper.setProps({ value: 'edit_complete' })
    await nextTick()
    vi.advanceTimersByTime(200)

    // 第二次切换（200ms 后），timer 重置
    await wrapper.setProps({ value: 'reviewed' })
    await nextTick()
    expect(wrapper.find('.el-tag-stub').classes()).toContain('is-flipping')

    // 再过 300ms（距第一次 500ms / 距第二次 300ms），仍应保留
    vi.advanceTimersByTime(300)
    await nextTick()
    expect(wrapper.find('.el-tag-stub').classes()).toContain('is-flipping')

    // 再过 100ms（距第二次 400ms），移除
    vi.advanceTimersByTime(100)
    await nextTick()
    expect(wrapper.find('.el-tag-stub').classes()).not.toContain('is-flipping')
  })

  it(':flip="false" 关闭动画', async () => {
    const wrapper = mount(GtStatusTag, {
      props: { dictKey: 'wp_status', value: 'draft', flip: false },
      global: { stubs: STUBS },
    })
    await nextTick()
    await wrapper.setProps({ value: 'edit_complete' })
    await nextTick()
    expect(wrapper.find('.el-tag-stub').classes()).not.toContain('is-flipping')
  })
})
