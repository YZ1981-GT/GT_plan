import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GtToolbar from '../GtToolbar.vue'

describe('GtToolbar compact mode', () => {
  it('renders with gt-toolbar--compact class when variant=compact', () => {
    const wrapper = mount(GtToolbar, {
      props: { variant: 'compact' },
    })
    expect(wrapper.find('.gt-toolbar--compact').exists()).toBe(true)
  })

  it('renders with gt-toolbar--default class when variant=default', () => {
    const wrapper = mount(GtToolbar, {
      props: { variant: 'default' },
    })
    expect(wrapper.find('.gt-toolbar--default').exists()).toBe(true)
  })

  it('renders with gt-toolbar--banner class when variant=banner', () => {
    const wrapper = mount(GtToolbar, {
      props: { variant: 'banner' },
    })
    expect(wrapper.find('.gt-toolbar--banner').exists()).toBe(true)
  })

  it('default variant is banner', () => {
    const wrapper = mount(GtToolbar)
    expect(wrapper.find('.gt-toolbar--banner').exists()).toBe(true)
  })

  it('compact mode has left and right slots', () => {
    const wrapper = mount(GtToolbar, {
      props: { variant: 'compact' },
      slots: {
        left: '<span class="test-left">左侧</span>',
        right: '<span class="test-right">右侧</span>',
      },
    })
    expect(wrapper.find('.test-left').exists()).toBe(true)
    expect(wrapper.find('.test-right').exists()).toBe(true)
  })
})
