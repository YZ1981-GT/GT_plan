import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import InheritOptionsStep, { type InheritOptions } from '../InheritOptionsStep.vue'

const ALL_KEYS: (keyof InheritOptions)[] = [
  'inherit_chart',
  'inherit_mapping',
  'inherit_wp_template',
  'inherit_assignments',
  'inherit_review_chain',
  'inherit_vr_rules',
  'inherit_materiality',
]

describe('InheritOptionsStep — Y-2 跨年继承配置', () => {
  it('渲染 7 个 checkbox（科目表/映射/模板/人员/复核链/VR/重要性）', () => {
    const wrapper = mount(InheritOptionsStep, {
      props: { prevProjectId: 'prev-uuid' },
    })
    for (const key of ALL_KEYS) {
      expect(
        wrapper.find(`[data-test="inherit-${key}"]`).exists(),
        `missing checkbox: ${key}`,
      ).toBe(true)
    }
  })

  it('默认值符合 ADR-7：科目表/映射/模板/VR True，人员/复核链/重要性 False', async () => {
    const wrapper = mount(InheritOptionsStep, {
      props: { prevProjectId: 'prev-uuid' },
    })
    const opts = (wrapper.vm as unknown as { getOptions: () => InheritOptions }).getOptions()
    expect(opts.inherit_chart).toBe(true)
    expect(opts.inherit_mapping).toBe(true)
    expect(opts.inherit_wp_template).toBe(true)
    expect(opts.inherit_vr_rules).toBe(true)
    expect(opts.inherit_assignments).toBe(false)
    expect(opts.inherit_review_chain).toBe(false)
    expect(opts.inherit_materiality).toBe(false)
  })

  it('全选按钮使所有 checkbox 都为 true', async () => {
    const wrapper = mount(InheritOptionsStep, {
      props: { prevProjectId: 'prev-uuid' },
    })
    const vm = wrapper.vm as unknown as {
      selectAll: () => void
      getOptions: () => InheritOptions
    }
    vm.selectAll()
    await wrapper.vm.$nextTick()
    const opts = vm.getOptions()
    for (const k of ALL_KEYS) {
      expect(opts[k]).toBe(true)
    }
  })

  it('全清按钮使所有 checkbox 都为 false', async () => {
    const wrapper = mount(InheritOptionsStep, {
      props: { prevProjectId: 'prev-uuid' },
    })
    const vm = wrapper.vm as unknown as {
      clearAll: () => void
      getOptions: () => InheritOptions
    }
    vm.clearAll()
    await wrapper.vm.$nextTick()
    const opts = vm.getOptions()
    for (const k of ALL_KEYS) {
      expect(opts[k]).toBe(false)
    }
  })

  it('恢复默认按钮恢复 ADR-7 默认值', async () => {
    const wrapper = mount(InheritOptionsStep, {
      props: { prevProjectId: 'prev-uuid' },
    })
    const vm = wrapper.vm as unknown as {
      selectAll: () => void
      resetDefault: () => void
      getOptions: () => InheritOptions
    }
    // 先全选
    vm.selectAll()
    await wrapper.vm.$nextTick()
    // 再恢复默认
    vm.resetDefault()
    await wrapper.vm.$nextTick()
    const opts = vm.getOptions()
    expect(opts.inherit_chart).toBe(true)
    expect(opts.inherit_assignments).toBe(false)
    expect(opts.inherit_review_chain).toBe(false)
    expect(opts.inherit_materiality).toBe(false)
  })

  it('未选择上年项目时显示警告提示（el-alert title prop）', () => {
    const wrapper = mount(InheritOptionsStep, {
      props: { prevProjectId: null },
    })
    // el-alert 在 jsdom 未注册时 title 会以 attribute 形式留在标签上
    const html = wrapper.html()
    expect(html).toContain('未选择上年项目')
  })

  it('emit update:modelValue with InheritOptions when toggled', async () => {
    const wrapper = mount(InheritOptionsStep, {
      props: { prevProjectId: 'prev-uuid' },
    })
    const vm = wrapper.vm as unknown as {
      selectAll: () => void
    }
    vm.selectAll()
    await wrapper.vm.$nextTick()
    const events = wrapper.emitted('update:modelValue')
    expect(events).toBeTruthy()
    const lastPayload = events![events!.length - 1][0] as InheritOptions
    expect(lastPayload.inherit_assignments).toBe(true)
    expect(lastPayload.inherit_review_chain).toBe(true)
    expect(lastPayload.inherit_materiality).toBe(true)
  })

  it('使用 modelValue 初始值覆盖默认', () => {
    const wrapper = mount(InheritOptionsStep, {
      props: {
        prevProjectId: 'prev-uuid',
        modelValue: { inherit_chart: false, inherit_assignments: true },
      },
    })
    const vm = wrapper.vm as unknown as { getOptions: () => InheritOptions }
    const opts = vm.getOptions()
    expect(opts.inherit_chart).toBe(false)
    expect(opts.inherit_assignments).toBe(true)
    // 未指定的字段保持默认
    expect(opts.inherit_mapping).toBe(true)
    expect(opts.inherit_review_chain).toBe(false)
  })
})
