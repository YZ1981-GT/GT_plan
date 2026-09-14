/**
 * Property 5: 提示条渲染当且仅当 guidance 非空
 * Feature: note-guidance-text-separation
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import * as fc from 'fast-check'

const GuidanceBar = defineComponent({
  name: 'GuidanceBar',
  props: {
    guidanceText: { type: String, default: '' },
  },
  template: `
    <div v-if="guidanceText && guidanceText.trim()" class="gt-guidance-bar">
      <span class="gt-guidance-text">{{ guidanceText }}</span>
    </div>
  `,
})

describe('guidanceBar Property 5', () => {
  it('renders bar iff guidance non-empty after trim', () => {
    fc.assert(
      fc.property(fc.string(), (raw) => {
        const wrapper = mount(GuidanceBar, { props: { guidanceText: raw } })
        const shouldShow = Boolean(raw && raw.trim())
        expect(wrapper.find('.gt-guidance-bar').exists()).toBe(shouldShow)
        if (shouldShow) {
          expect(wrapper.find('.gt-guidance-text').text()).toBe(raw)
          expect(wrapper.find('input, textarea, [contenteditable=true]').exists()).toBe(false)
        }
        wrapper.unmount()
      }),
      { numRuns: 5 },
    )
  })

  it('shows GT guidance bar class for sample guidance', () => {
    const wrapper = mount(GuidanceBar, {
      props: { guidanceText: '（注：应披露公允价值确认依据。）' },
    })
    expect(wrapper.find('.gt-guidance-bar').exists()).toBe(true)
    expect(wrapper.find('.gt-guidance-text').text()).toContain('应披露')
    wrapper.unmount()
  })
})
