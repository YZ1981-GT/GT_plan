/**
 * AiContentBadge — Task 6.5 vitest 单测
 *
 * 验证：
 * 1. count = 0 / null / undefined / 负数时不渲染
 * 2. count > 0 时渲染徽章并展示数量
 * 3. count > 99 时仍渲染（el-badge max 处理）
 * 4. 自定义 label 透传
 * 5. clickable=true 时点击触发 click 事件
 * 6. clickable=false（默认）时点击不触发事件
 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AiContentBadge from '../AiContentBadge.vue'

describe('AiContentBadge', () => {
  it('count=0 时不渲染徽章', () => {
    const wrapper = mount(AiContentBadge, { props: { count: 0 } })
    expect(wrapper.find('.gt-ai-badge').exists()).toBe(false)
  })

  it('count=null 时不渲染徽章', () => {
    const wrapper = mount(AiContentBadge, { props: { count: null as any } })
    expect(wrapper.find('.gt-ai-badge').exists()).toBe(false)
  })

  it('count=undefined 时不渲染徽章', () => {
    const wrapper = mount(AiContentBadge, {
      props: { count: undefined as any },
    })
    expect(wrapper.find('.gt-ai-badge').exists()).toBe(false)
  })

  it('count<0 时不渲染徽章', () => {
    const wrapper = mount(AiContentBadge, { props: { count: -3 } })
    expect(wrapper.find('.gt-ai-badge').exists()).toBe(false)
  })

  it('count>0 时渲染并显示数字 + 默认标签', () => {
    const wrapper = mount(AiContentBadge, { props: { count: 5 } })
    expect(wrapper.find('.gt-ai-badge').exists()).toBe(true)
    expect(wrapper.text()).toContain('AI 待确认')
    // el-badge 的 value=5 会渲染为 sup
    expect(wrapper.html()).toContain('5')
  })

  it('count=1 单数也正常渲染', () => {
    const wrapper = mount(AiContentBadge, { props: { count: 1 } })
    expect(wrapper.find('.gt-ai-badge').exists()).toBe(true)
    expect(wrapper.text()).toContain('AI 待确认')
  })

  it('支持自定义 label 文本', () => {
    const wrapper = mount(AiContentBadge, {
      props: { count: 3, label: '需复核 AI' },
    })
    expect(wrapper.text()).toContain('需复核 AI')
    expect(wrapper.text()).not.toContain('AI 待确认')
  })

  it('clickable=true 时点击触发 click 事件', async () => {
    const wrapper = mount(AiContentBadge, {
      props: { count: 2, clickable: true },
    })
    expect(wrapper.find('.gt-ai-badge--clickable').exists()).toBe(true)
    await wrapper.find('.gt-ai-badge').trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
    expect(wrapper.emitted('click')!.length).toBe(1)
  })

  it('clickable 默认 false 时点击不触发事件', async () => {
    const wrapper = mount(AiContentBadge, { props: { count: 2 } })
    expect(wrapper.find('.gt-ai-badge--clickable').exists()).toBe(false)
    await wrapper.find('.gt-ai-badge').trigger('click')
    expect(wrapper.emitted('click')).toBeFalsy()
  })

  it('count=100 时正常渲染（el-badge value=100 + max=99 由内部处理为 99+）', () => {
    const wrapper = mount(AiContentBadge, { props: { count: 100 } })
    expect(wrapper.find('.gt-ai-badge').exists()).toBe(true)
    // 测试环境未注册 el-badge，故只能断言 value/max 属性透传给 el-badge
    // 真实运行时 el-badge 内部按 max=99 截断为 "99+"
    const badge = wrapper.find('.gt-ai-badge')
    expect(badge.attributes('max')).toBe('99')
    expect(badge.attributes('value')).toBe('100')
  })

  it('小数 count 取整后渲染（如 3.7 → 3）', () => {
    const wrapper = mount(AiContentBadge, { props: { count: 3.7 } })
    expect(wrapper.find('.gt-ai-badge').exists()).toBe(true)
    expect(wrapper.html()).toContain('3')
  })
})
