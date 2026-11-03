import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import BundleAssigneeDisplay from '../BundleAssigneeDisplay.vue'
import { buildBundleAssigneeMap } from '../bundleAssignee'

describe('BundleAssigneeDisplay', () => {
  it('展示 staff name', () => {
    const assignment = buildBundleAssigneeMap([
      {
        wp_code: 'S32-1',
        assigned_to: 'user-staff',
        assigned_to_name: '张三',
        assigned_to_username: 'zhangsan',
      },
    ])['S32-1']
    const wrapper = mount(BundleAssigneeDisplay, {
      props: { tabCode: 'S32-1', assignment },
    })

    expect(wrapper.find('[data-testid="bundle-assignee-S32-1"]').text()).toContain('张三')
    expect(wrapper.find('.gt-bundle-assignee--empty').exists()).toBe(false)
  })

  it('staff name 缺失时回退 username', () => {
    const assignment = buildBundleAssigneeMap([
      {
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
    expect(wrapper.text()).not.toContain('暂无负责人')
  })

  it('无负责人时显示空态', () => {
    const assignment = buildBundleAssigneeMap([
      { wp_code: 'S34-1', assigned_to: null, assigned_to_name: null, assigned_to_username: null },
    ])['S34-1']
    const wrapper = mount(BundleAssigneeDisplay, {
      props: { tabCode: 'S34-1', assignment },
    })

    expect(wrapper.find('[data-testid="bundle-assignee-S34-1"]').text()).toContain('暂无负责人')
    expect(wrapper.find('.gt-bundle-assignee--empty').exists()).toBe(true)
  })
})
