import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GtSimpleToolbar from '../GtSimpleToolbar.vue'

describe('GtSimpleToolbar', () => {
  it('renders title in left section', () => {
    const wrapper = mount(GtSimpleToolbar, {
      props: { title: '人员档案' },
    })
    expect(wrapper.text()).toContain('人员档案')
    expect(wrapper.find('.gt-st-title').text()).toBe('人员档案')
  })

  it('does not render back button by default', () => {
    const wrapper = mount(GtSimpleToolbar, {
      props: { title: '校验规则' },
    })
    expect(wrapper.find('.gt-st-back').exists()).toBe(false)
  })

  it('renders back button when showBack is true', () => {
    const wrapper = mount(GtSimpleToolbar, {
      props: { title: '知识库', showBack: true },
    })
    expect(wrapper.find('.gt-st-back').exists()).toBe(true)
  })

  it('emits back event when back button is clicked', async () => {
    const wrapper = mount(GtSimpleToolbar, {
      props: { title: '知识库', showBack: true },
    })
    await wrapper.find('.gt-st-back').trigger('click')
    expect(wrapper.emitted('back')).toBeTruthy()
    expect(wrapper.emitted('back')!.length).toBe(1)
  })

  it('renders actions slot in right section', () => {
    const wrapper = mount(GtSimpleToolbar, {
      props: { title: '附件管理' },
      slots: {
        actions: '<button class="test-action">新增</button>',
      },
    })
    expect(wrapper.find('.gt-st-actions .test-action').exists()).toBe(true)
  })

  it('renders title-extra slot next to title', () => {
    const wrapper = mount(GtSimpleToolbar, {
      props: { title: '模板管理' },
      slots: {
        'title-extra': '<span class="test-tag">v2.0</span>',
      },
    })
    expect(wrapper.find('.gt-st-left .test-tag').exists()).toBe(true)
  })

  it('uses semantic structure: white toolbar (not purple banner)', () => {
    const wrapper = mount(GtSimpleToolbar, {
      props: { title: '回收站' },
    })
    // 简洁工具栏应使用 .gt-simple-toolbar 容器，而不是 GtPageHeader 的紫色渐变结构
    expect(wrapper.find('.gt-simple-toolbar').exists()).toBe(true)
    // 不应包含紫色渐变 banner 类
    expect(wrapper.find('.gt-page-header').exists()).toBe(false)
  })
})
