/**
 * WpSection 单元测试
 *
 * Feature: platform-global-hardening
 * Requirements: 4.1
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import WpSection from '../WpSection.vue'

describe('WpSection', () => {
  it('渲染标题', () => {
    const wrapper = mount(WpSection, {
      props: { title: '坏账准备明细表 D2-3' },
    })
    expect(wrapper.find('.wp-section__title').text()).toBe('坏账准备明细表 D2-3')
  })

  it('无 objective 时不渲染 el-alert', () => {
    const wrapper = mount(WpSection, {
      props: { title: '测试标题' },
    })
    expect(wrapper.find('.wp-section__objective').exists()).toBe(false)
  })

  it('有 objective 时渲染 el-alert type=info', () => {
    const wrapper = mount(WpSection, {
      props: {
        title: '测试标题',
        objective: '核实坏账准备计提的完整性',
      },
    })
    const alert = wrapper.find('.wp-section__objective')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toContain('核实坏账准备计提的完整性')
  })

  it('无 guidance 时不渲染 details', () => {
    const wrapper = mount(WpSection, {
      props: { title: '测试标题' },
    })
    expect(wrapper.find('.wp-section__guidance').exists()).toBe(false)
  })

  it('有 guidance 时渲染 details 折叠区', () => {
    const wrapper = mount(WpSection, {
      props: {
        title: '测试标题',
        guidance: '按CAS 22相关规定编制...',
      },
    })
    const details = wrapper.find('.wp-section__guidance')
    expect(details.exists()).toBe(true)
    expect(details.find('summary').text()).toContain('编制提示')
    expect(details.text()).toContain('按CAS 22相关规定编制...')
  })

  it('渲染 #actions slot 在右侧', () => {
    const wrapper = mount(WpSection, {
      props: { title: '测试标题' },
      slots: {
        actions: '<button class="test-btn">AI</button>',
      },
    })
    const actionsSlot = wrapper.find('.wp-section__actions')
    expect(actionsSlot.find('.test-btn').exists()).toBe(true)
  })

  it('渲染 #default slot 作为主体内容', () => {
    const wrapper = mount(WpSection, {
      props: { title: '测试标题' },
      slots: {
        default: '<div class="my-content">表格内容</div>',
      },
    })
    const body = wrapper.find('.wp-section__body')
    expect(body.find('.my-content').exists()).toBe(true)
  })

  it('标题和操作按钮在同一行（flex row）', () => {
    const wrapper = mount(WpSection, {
      props: { title: '测试标题' },
      slots: {
        actions: '<button>复核</button>',
      },
    })
    const header = wrapper.find('.wp-section__header')
    expect(header.exists()).toBe(true)
    // header contains both title and actions
    expect(header.find('.wp-section__title').exists()).toBe(true)
    expect(header.find('.wp-section__actions').exists()).toBe(true)
  })
})
