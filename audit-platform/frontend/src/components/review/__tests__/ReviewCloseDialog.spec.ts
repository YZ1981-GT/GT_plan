/**
 * P1-1.3: ReviewCloseDialog 组件测试
 *
 * 验证：
 * - 重大问题（must_fix）无依据时不可提交
 * - 重大问题有关闭说明时可提交
 * - 普通问题（suggest）无需依据可直接提交
 *
 * Validates: Requirements 3.2
 * Property 5：复核关闭有依据
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import ReviewCloseDialog from '../ReviewCloseDialog.vue'

// Minimal stubs for Element Plus
const ElDialog = {
  template: '<div v-if="modelValue" class="el-dialog"><slot /><slot name="footer" /></div>',
  props: ['modelValue', 'title', 'width', 'appendToBody'],
  emits: ['update:modelValue'],
}
const ElAlert = {
  template: '<div class="el-alert" :class="type"><slot /></div>',
  props: ['type', 'closable', 'showIcon'],
}
const ElForm = { template: '<div class="el-form"><slot /></div>', props: ['labelWidth'] }
const ElFormItem = { template: '<div class="el-form-item"><slot /></div>', props: ['label', 'required'] }
const ElInput = {
  template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  props: ['modelValue', 'type', 'rows', 'placeholder'],
  emits: ['update:modelValue'],
}
const ElButton = {
  template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  props: ['type', 'disabled'],
  emits: ['click'],
}

// Stub ReviewEvidencePicker
const ReviewEvidencePicker = {
  template: '<div class="evidence-picker"></div>',
  props: ['modelValue', 'projectId'],
  emits: ['update:modelValue'],
}

const globalStubs = {
  ElDialog,
  ElAlert,
  ElForm,
  ElFormItem,
  ElInput,
  ElButton,
  ReviewEvidencePicker,
}

describe('ReviewCloseDialog', () => {
  const baseProps = {
    modelValue: true,
    priority: 'must_fix',
    projectId: 'proj-001',
  }

  it('must_fix 时显示警告信息', () => {
    const wrapper = mount(ReviewCloseDialog, {
      props: baseProps,
      global: { stubs: globalStubs },
    })

    expect(wrapper.find('.el-alert').exists()).toBe(true)
    expect(wrapper.text()).toContain('重大问题')
  })

  it('must_fix 无依据时确认按钮禁用', () => {
    const wrapper = mount(ReviewCloseDialog, {
      props: baseProps,
      global: { stubs: globalStubs },
    })

    const buttons = wrapper.findAll('button')
    const confirmBtn = buttons.find((b) => b.text().includes('确认关闭'))
    expect(confirmBtn).toBeTruthy()
    expect(confirmBtn!.attributes('disabled')).toBeDefined()
  })

  it('must_fix 填写关闭说明后可提交', async () => {
    const wrapper = mount(ReviewCloseDialog, {
      props: baseProps,
      global: { stubs: globalStubs },
    })

    const textarea = wrapper.find('textarea')
    await textarea.setValue('已修正差异并重新核对一致')

    const buttons = wrapper.findAll('button')
    const confirmBtn = buttons.find((b) => b.text().includes('确认关闭'))
    // After setting value, button should be enabled
    expect(confirmBtn!.attributes('disabled')).toBeUndefined()
  })

  it('suggest 优先级不显示警告', () => {
    const wrapper = mount(ReviewCloseDialog, {
      props: { ...baseProps, priority: 'suggest' },
      global: { stubs: globalStubs },
    })

    expect(wrapper.find('.el-alert').exists()).toBe(false)
  })

  it('suggest 优先级确认按钮默认可用', () => {
    const wrapper = mount(ReviewCloseDialog, {
      props: { ...baseProps, priority: 'suggest' },
      global: { stubs: globalStubs },
    })

    const buttons = wrapper.findAll('button')
    const confirmBtn = buttons.find((b) => b.text().includes('确认关闭'))
    expect(confirmBtn!.attributes('disabled')).toBeUndefined()
  })
})
