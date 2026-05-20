/**
 * TrimReasonDialog.spec.ts — 裁剪理由选择弹窗测试
 *
 * 验证：
 * 1. 理由选项渲染（4 个预设选项）
 * 2. "其他"选项 → 文本输入框显示 + < 5 字符禁用确认
 * 3. 未选择理由 → 确认按钮禁用
 * 4. 确认 emit 正确 payload
 *
 * @see requirements.md Requirement 2.2, 2.3, 2.5
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import TrimReasonDialog from '../TrimReasonDialog.vue'

const globalStubs = {
  'el-dialog': {
    template: '<div class="el-dialog" v-if="modelValue"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title', 'width', 'closeOnClickModal', 'appendToBody'],
    emits: ['update:model-value'],
  },
  'el-alert': { template: '<div class="el-alert"><slot /></div>', props: ['type', 'showIcon', 'closable'] },
  'el-radio-group': {
    template: '<div class="el-radio-group" @change="$emit(\'update:modelValue\', $event)"><slot /></div>',
    props: ['modelValue'],
    emits: ['update:modelValue'],
  },
  'el-radio': {
    template: '<label class="el-radio" @click="$emit(\'click\')"><input type="radio" :value="value" /><slot /></label>',
    props: ['value'],
    emits: ['click'],
  },
  'el-input': {
    template: '<textarea class="el-input" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)"></textarea>',
    props: ['modelValue', 'type', 'rows', 'placeholder', 'maxlength', 'showWordLimit'],
    emits: ['update:modelValue'],
  },
  'el-button': {
    template: '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'disabled'],
    emits: ['click'],
  },
}

describe('TrimReasonDialog — 理由选项渲染', () => {
  it('渲染 4 个预设理由选项', () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: true },
      global: { stubs: globalStubs },
    })

    const radios = wrapper.findAll('.el-radio')
    expect(radios.length).toBe(4)
    expect(wrapper.text()).toContain('无相关业务')
    expect(wrapper.text()).toContain('风险评估为低')
    expect(wrapper.text()).toContain('控制测试有效')
    expect(wrapper.text()).toContain('其他')
  })

  it('弹窗不可见时不渲染内容', () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: false },
      global: { stubs: globalStubs },
    })

    expect(wrapper.find('.el-radio-group').exists()).toBe(false)
  })
})

describe('TrimReasonDialog — "其他"选项文本输入', () => {
  it('选择"其他"时显示文本输入框', async () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: true },
      global: { stubs: globalStubs },
    })

    // 模拟选择 "other"
    const vm = wrapper.vm as any
    vm.selectedReason = 'other'
    await nextTick()

    expect(wrapper.find('.gt-trim-reason-text').exists()).toBe(true)
  })

  it('选择非"其他"选项时不显示文本输入框', async () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: true },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.selectedReason = 'no_related_business'
    await nextTick()

    expect(wrapper.find('.gt-trim-reason-text').exists()).toBe(false)
  })

  it('"其他"理由文本 < 5 字符时显示错误提示', async () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: true },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.selectedReason = 'other'
    vm.reasonText = '短'
    await nextTick()

    expect(wrapper.find('.gt-trim-reason-error').exists()).toBe(true)
    expect(wrapper.text()).toContain('至少需要 5 个字符')
  })

  it('"其他"理由文本 ≥ 5 字符时不显示错误', async () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: true },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.selectedReason = 'other'
    vm.reasonText = '客户无海外业务'
    await nextTick()

    const errors = wrapper.findAll('.gt-trim-reason-error')
    // 不应有"至少需要 5 个字符"的错误
    const textError = errors.filter((e) => e.text().includes('至少需要 5 个字符'))
    expect(textError.length).toBe(0)
  })
})

describe('TrimReasonDialog — 确认按钮禁用逻辑', () => {
  it('未选择理由时确认按钮禁用', async () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: true },
      global: { stubs: globalStubs },
    })

    const buttons = wrapper.findAll('.el-button')
    const confirmBtn = buttons.find((b) => b.text().includes('确认裁剪'))
    expect(confirmBtn).toBeDefined()
    expect(confirmBtn!.attributes('disabled')).toBeDefined()
  })

  it('选择预设理由后确认按钮启用', async () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: true },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.selectedReason = 'no_related_business'
    await nextTick()

    const buttons = wrapper.findAll('.el-button')
    const confirmBtn = buttons.find((b) => b.text().includes('确认裁剪'))
    expect(confirmBtn!.attributes('disabled')).toBeUndefined()
  })

  it('选择"其他"但文本 < 5 字符时确认按钮禁用', async () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: true },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.selectedReason = 'other'
    vm.reasonText = '短文'
    await nextTick()

    const buttons = wrapper.findAll('.el-button')
    const confirmBtn = buttons.find((b) => b.text().includes('确认裁剪'))
    expect(confirmBtn!.attributes('disabled')).toBeDefined()
  })

  it('选择"其他"且文本 ≥ 5 字符时确认按钮启用', async () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: true },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.selectedReason = 'other'
    vm.reasonText = '客户无海外业务外币不适用'
    await nextTick()

    const buttons = wrapper.findAll('.el-button')
    const confirmBtn = buttons.find((b) => b.text().includes('确认裁剪'))
    expect(confirmBtn!.attributes('disabled')).toBeUndefined()
  })
})

describe('TrimReasonDialog — emit 事件', () => {
  it('确认时 emit confirm 带正确 payload（预设理由）', async () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: true },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.selectedReason = 'low_risk_assessment'
    await nextTick()

    const buttons = wrapper.findAll('.el-button')
    const confirmBtn = buttons.find((b) => b.text().includes('确认裁剪'))
    await confirmBtn!.trigger('click')

    const emitted = wrapper.emitted('confirm')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toEqual({
      reason_code: 'low_risk_assessment',
      reason_text: null,
    })
  })

  it('确认时 emit confirm 带正确 payload（"其他"理由）', async () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: true },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.selectedReason = 'other'
    vm.reasonText = '客户无海外业务，外币程序不适用'
    await nextTick()

    const buttons = wrapper.findAll('.el-button')
    const confirmBtn = buttons.find((b) => b.text().includes('确认裁剪'))
    await confirmBtn!.trigger('click')

    const emitted = wrapper.emitted('confirm')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toEqual({
      reason_code: 'other',
      reason_text: '客户无海外业务，外币程序不适用',
    })
  })

  it('取消时 emit cancel', async () => {
    const wrapper = mount(TrimReasonDialog, {
      props: { visible: true },
      global: { stubs: globalStubs },
    })

    const buttons = wrapper.findAll('.el-button')
    const cancelBtn = buttons.find((b) => b.text().includes('取消'))
    await cancelBtn!.trigger('click')

    expect(wrapper.emitted('cancel')).toBeDefined()
    expect(wrapper.emitted('update:visible')).toBeDefined()
    expect(wrapper.emitted('update:visible')![0][0]).toBe(false)
  })
})
