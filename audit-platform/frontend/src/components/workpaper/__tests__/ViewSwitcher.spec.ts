/**
 * ViewSwitcher.spec.ts — 视图切换下拉组件测试
 *
 * spec role-based-view-switching Task 1.8
 *
 * 验证：
 * 1. 渲染 4 个选项（助理/经理/合伙人/质控）
 * 2. 选择事件 emit update:modelValue
 * 3. disabled 状态
 * 4. 默认选中值正确
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ViewSwitcher from '../ViewSwitcher.vue'

// Define stubs that properly register component names
const ElSelect = {
  name: 'ElSelect',
  template: '<div class="el-select-stub" :data-disabled="disabled" :data-model-value="modelValue"><slot /></div>',
  props: ['modelValue', 'disabled', 'size', 'placeholder'],
  emits: ['change', 'update:modelValue'],
}

const ElOption = {
  name: 'ElOption',
  template: '<div class="el-option-stub" :data-value="value">{{ label }}</div>',
  props: ['value', 'label'],
}

const globalConfig = {
  components: {
    'el-select': ElSelect,
    'el-option': ElOption,
  },
}

describe('ViewSwitcher — 渲染', () => {
  it('组件可正常挂载', () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'assistant' },
      global: globalConfig,
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('渲染 4 个选项', () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'assistant' },
      global: globalConfig,
    })
    const options = wrapper.findAll('.el-option-stub')
    expect(options.length).toBe(4)
  })

  it('选项包含正确的标签文本', () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'assistant' },
      global: globalConfig,
    })
    const text = wrapper.text()
    expect(text).toContain('助理视图')
    expect(text).toContain('经理视图')
    expect(text).toContain('合伙人视图')
    expect(text).toContain('质控视图')
  })

  it('选项包含图标前缀', () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'assistant' },
      global: globalConfig,
    })
    const text = wrapper.text()
    expect(text).toContain('👤')
    expect(text).toContain('📊')
    expect(text).toContain('🔍')
    expect(text).toContain('✅')
  })

  it('选项值正确', () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'assistant' },
      global: globalConfig,
    })
    const options = wrapper.findAll('.el-option-stub')
    const values = options.map(o => o.attributes('data-value'))
    expect(values).toEqual(['assistant', 'manager', 'partner', 'qc'])
  })
})

describe('ViewSwitcher — 事件', () => {
  it('选择变更时 emit update:modelValue', async () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'assistant' },
      global: globalConfig,
    })
    // Simulate the el-select emitting change event
    const selectStub = wrapper.findComponent(ElSelect)
    await selectStub.vm.$emit('change', 'partner')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')![0]).toEqual(['partner'])
  })

  it('切换到 qc 视图', async () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'assistant' },
      global: globalConfig,
    })
    const selectStub = wrapper.findComponent(ElSelect)
    await selectStub.vm.$emit('change', 'qc')
    expect(wrapper.emitted('update:modelValue')![0]).toEqual(['qc'])
  })
})

describe('ViewSwitcher — disabled 状态', () => {
  it('disabled=false 时 select 不禁用', () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'assistant', disabled: false },
      global: globalConfig,
    })
    const selectEl = wrapper.find('.el-select-stub')
    expect(selectEl.attributes('data-disabled')).toBe('false')
  })

  it('disabled=true 时 select 禁用', () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'assistant', disabled: true },
      global: globalConfig,
    })
    const selectEl = wrapper.find('.el-select-stub')
    expect(selectEl.attributes('data-disabled')).toBe('true')
  })

  it('disabled 默认为 false', () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'manager' },
      global: globalConfig,
    })
    const selectEl = wrapper.find('.el-select-stub')
    expect(selectEl.attributes('data-disabled')).toBe('false')
  })
})

describe('ViewSwitcher — modelValue 绑定', () => {
  it('modelValue=assistant 时传递正确', () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'assistant' },
      global: globalConfig,
    })
    const selectEl = wrapper.find('.el-select-stub')
    expect(selectEl.attributes('data-model-value')).toBe('assistant')
  })

  it('modelValue=qc 时传递正确', () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'qc' },
      global: globalConfig,
    })
    const selectEl = wrapper.find('.el-select-stub')
    expect(selectEl.attributes('data-model-value')).toBe('qc')
  })

  it('modelValue=partner 时传递正确', () => {
    const wrapper = mount(ViewSwitcher, {
      props: { modelValue: 'partner' },
      global: globalConfig,
    })
    const selectEl = wrapper.find('.el-select-stub')
    expect(selectEl.attributes('data-model-value')).toBe('partner')
  })
})
