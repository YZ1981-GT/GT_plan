import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import BundleAssigneeDisplay from '../BundleAssigneeDisplay.vue'
import { buildBundleAssigneeMap } from '../bundleAssignee'

// 组件契约（BundleAssigneeDisplay.vue，自 30afe3a25 起未变）：有负责人时显示「编制人 + 名称」，
// 无负责人时整块不渲染（v-if），没有「暂无负责人」空态。
// buildBundleAssigneeMap 只收带 wp_id 与 assigned_to 的条目，夹具须带 wp_id。
describe('BundleAssigneeDisplay', () => {
  it('展示 staff name', () => {
    const assignment = buildBundleAssigneeMap([
      {
        wp_id: 'wp-s32-1',
        wp_code: 'S32-1',
        assigned_to: 'user-staff',
        assigned_to_name: '张三',
        assigned_to_username: 'zhangsan',
      },
    ])['S32-1']
    const wrapper = mount(BundleAssigneeDisplay, {
      props: { tabCode: 'S32-1', assignment },
    })

    const box = wrapper.find('.gt-bundle-assignee')
    expect(box.exists()).toBe(true)
    expect(box.text()).toContain('张三')
    expect(box.attributes('aria-label')).toBe('S32-1 编制人：张三')
  })

  it('staff name 缺失时回退 username', () => {
    const assignment = buildBundleAssigneeMap([
      {
        wp_id: 'wp-s33-1',
        wp_code: 'S33-1',
        assigned_to: 'user-fallback',
        assigned_to_name: null,
        assigned_to_username: 'fallback-user',
      },
    ])['S33-1']
    const wrapper = mount(BundleAssigneeDisplay, {
      props: { tabCode: 'S33-1', assignment },
    })

    expect(wrapper.text()).toContain('fallback-user')
  })

  it('无负责人时不渲染（无空态文案）', () => {
    const assignment = buildBundleAssigneeMap([
      { wp_id: 'wp-s34-1', wp_code: 'S34-1', assigned_to: null, assigned_to_name: null, assigned_to_username: null },
    ])['S34-1']
    expect(assignment).toBeUndefined()
    const wrapper = mount(BundleAssigneeDisplay, {
      props: { tabCode: 'S34-1', assignment },
    })

    expect(wrapper.find('.gt-bundle-assignee').exists()).toBe(false)
    expect(wrapper.text()).toBe('')
  })
})
