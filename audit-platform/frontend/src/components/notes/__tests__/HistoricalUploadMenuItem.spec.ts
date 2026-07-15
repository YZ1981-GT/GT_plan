import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import HistoricalUploadMenuItem from '../HistoricalUploadMenuItem.vue'

const DropdownItemStub = {
  props: ['disabled', 'title'],
  emits: ['click'],
  template: '<button :disabled="disabled" :title="title" @click="$emit(\'click\')"><slot /></button>',
}

describe('Feature: advanced-query-disclosure-integration-hardening, Property P12', () => {
  it('能力关闭时显示中文原因、保持禁用且不发起请求事件', async () => {
    const wrapper = mount(HistoricalUploadMenuItem, {
      props: {
        disabled: true,
        reason: '历史 Word/PDF 解析尚未实现',
      },
      global: { stubs: { 'el-dropdown-item': DropdownItemStub } },
    })

    const button = wrapper.get('button')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('title')).toContain('尚未实现')
    expect(wrapper.text()).toContain('暂不可用')
    await button.trigger('click')
    expect(wrapper.emitted('request')).toBeUndefined()
  })
})
