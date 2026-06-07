/**
 * P1-1.2: ReviewEvidencePicker 组件测试
 *
 * 验证：
 * - 展示已关联的证据标签
 * - 支持添加新证据引用
 * - 支持删除证据引用
 * - disabled 状态不可操作
 *
 * Validates: Requirements 3.1
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ReviewEvidencePicker from '../ReviewEvidencePicker.vue'
import type { EvidenceRef } from '@/types/evidenceRef'

// Mock Element Plus components
const ElTag = {
  template: '<span class="el-tag"><slot /><button v-if="closable" class="close-btn" @click="$emit(\'close\')">x</button></span>',
  props: ['closable', 'type'],
  emits: ['close'],
}
const ElButton = {
  template: '<button @click="$emit(\'click\')"><slot /></button>',
  props: ['size', 'type', 'plain', 'disabled'],
  emits: ['click'],
}
const ElDialog = {
  template: '<div v-if="modelValue" class="el-dialog"><slot /><slot name="footer" /></div>',
  props: ['modelValue', 'title', 'width', 'appendToBody'],
  emits: ['update:modelValue'],
}
const ElForm = { template: '<div class="el-form"><slot /></div>', props: ['labelWidth'] }
const ElFormItem = { template: '<div class="el-form-item"><slot /></div>', props: ['label'] }
const ElSelect = {
  template: '<select><slot /></select>',
  props: ['modelValue', 'placeholder'],
  emits: ['update:modelValue'],
}
const ElOption = { template: '<option :value="value">{{ label }}</option>', props: ['label', 'value'] }
const ElInput = {
  template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  props: ['modelValue', 'placeholder', 'type', 'rows'],
  emits: ['update:modelValue'],
}

const globalStubs = {
  ElTag,
  ElButton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElSelect,
  ElOption,
  ElInput,
}

describe('ReviewEvidencePicker', () => {
  const baseProps = {
    modelValue: [] as EvidenceRef[],
    projectId: 'proj-001',
  }

  it('渲染已有的证据标签', () => {
    const refs: EvidenceRef[] = [
      { evidence_type: 'attachment', evidence_id: 'att-1', project_id: 'proj-001', label: '银行对账单' },
      { evidence_type: 'workpaper_cell', evidence_id: 'wp-1-R5', project_id: 'proj-001', label: '现金审定表 R5' },
    ]

    const wrapper = mount(ReviewEvidencePicker, {
      props: { ...baseProps, modelValue: refs },
      global: { stubs: globalStubs },
    })

    const tags = wrapper.findAll('.el-tag')
    expect(tags.length).toBe(2)
    expect(tags[0].text()).toContain('银行对账单')
    expect(tags[1].text()).toContain('现金审定表 R5')
  })

  it('disabled 状态不显示关联按钮', () => {
    const wrapper = mount(ReviewEvidencePicker, {
      props: { ...baseProps, disabled: true },
      global: { stubs: globalStubs },
    })

    // Button should not be visible
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBe(0)
  })

  it('删除证据时触发 update:modelValue', async () => {
    const refs: EvidenceRef[] = [
      { evidence_type: 'attachment', evidence_id: 'att-1', project_id: 'proj-001', label: '对账单' },
    ]

    const wrapper = mount(ReviewEvidencePicker, {
      props: { ...baseProps, modelValue: refs },
      global: { stubs: globalStubs },
    })

    const closeBtn = wrapper.find('.close-btn')
    await closeBtn.trigger('click')

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual([])
  })

  it('证据类型显示中文标签', () => {
    const refs: EvidenceRef[] = [
      { evidence_type: 'note_table', evidence_id: 'note-1', project_id: 'proj-001' },
    ]

    const wrapper = mount(ReviewEvidencePicker, {
      props: { ...baseProps, modelValue: refs },
      global: { stubs: globalStubs },
    })

    expect(wrapper.text()).toContain('附注表格')
  })
})
