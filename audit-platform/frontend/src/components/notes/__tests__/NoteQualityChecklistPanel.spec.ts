/**
 * NoteQualityChecklistPanel.spec.ts — 附注质量清单面板测试
 *
 * Spec:    .kiro/specs/disclosure-note-semantic-structure-and-presentation/ Task 9.5, 9.6
 * Design:  质量清单结果 schema
 * Reqs:    9.1, 9.2, 9.3
 *
 * 用例：
 *   1. 渲染清单条目列表
 *   2. 按 level 筛选
 *   3. 按 category 筛选
 *   4. 点击跳转 emit navigate
 *   5. 空列表显示空状态
 *   6. blocking 计数准确
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import NoteQualityChecklistPanel from '../NoteQualityChecklistPanel.vue'
import type { QualityChecklistItem } from '../NoteQualityChecklistPanel.vue'

// Element Plus stubs
const ElRadioGroupStub = {
  name: 'ElRadioGroup',
  template: '<div data-test="radio-group"><slot /></div>',
  props: ['modelValue', 'size'],
  emits: ['update:modelValue'],
}

const ElRadioButtonStub = {
  name: 'ElRadioButton',
  template: '<button data-test="radio-button" :data-value="value" @click="$parent.$emit(\'update:modelValue\', value)"><slot /></button>',
  props: ['value'],
}

const ElSelectStub = {
  name: 'ElSelect',
  template: '<div data-test="select"><slot /></div>',
  props: ['modelValue', 'placeholder', 'size', 'clearable'],
  emits: ['update:modelValue'],
}

const ElOptionStub = {
  name: 'ElOption',
  template: '<div data-test="option" :data-value="value">{{ label }}</div>',
  props: ['label', 'value'],
}

const ElTagStub = {
  name: 'ElTag',
  template: '<span data-test="tag" :data-type="type" :data-effect="effect"><slot /></span>',
  props: ['type', 'size', 'effect'],
}

const ElButtonStub = {
  name: 'ElButton',
  template: '<button data-test="button" :data-type="type" @click="$emit(\'click\')"><slot /></button>',
  props: ['type', 'size', 'link'],
  emits: ['click'],
}

const ElEmptyStub = {
  name: 'ElEmpty',
  template: '<div data-test="empty">{{ description }}</div>',
  props: ['description'],
}

const globalStubs = {
  stubs: {
    'el-radio-group': ElRadioGroupStub,
    'el-radio-button': ElRadioButtonStub,
    'el-select': ElSelectStub,
    'el-option': ElOptionStub,
    'el-tag': ElTagStub,
    'el-button': ElButtonStub,
    'el-empty': ElEmptyStub,
  },
}

const sampleItems: QualityChecklistItem[] = [
  {
    level: 'blocking',
    category: 'formula',
    section_id: 'accounts_receivable',
    table_id: 'aging_analysis',
    row_id: 'total',
    col_id: 'closing_balance',
    message: '公式执行错误：除零错误',
    route: '/projects/{pid}/disclosure-notes?section=accounts_receivable',
    evidence: { formula_id: 'f_001', error: '除零错误' },
  },
  {
    level: 'warning',
    category: 'stale',
    section_id: 'cash',
    message: '章节数据陈旧，底稿已更新但附注未刷新',
    route: '/projects/{pid}/disclosure-notes?section=cash',
  },
  {
    level: 'warning',
    category: 'manual_override',
    section_id: 'fixed_assets',
    table_id: 'main',
    row_id: 'r1',
    col_id: 'amount',
    message: '手工覆盖未确认',
    route: '/projects/{pid}/disclosure-notes?section=fixed_assets',
  },
  {
    level: 'blocking',
    category: 'ai',
    section_id: 'related_party',
    message: 'AI 草稿未经人工确认，阻止签发',
    route: '/projects/{pid}/disclosure-notes?section=related_party',
  },
  {
    level: 'info',
    category: 'completeness',
    section_id: 'investments',
    message: '章节缺失数据',
  },
]

describe('NoteQualityChecklistPanel — 渲染', () => {
  it('渲染全部清单条目', () => {
    const wrapper = mount(NoteQualityChecklistPanel, {
      props: { items: sampleItems },
      global: globalStubs,
    })
    const listItems = wrapper.findAll('.checklist-item')
    expect(listItems.length).toBe(5)
  })

  it('展示正确的消息文本', () => {
    const wrapper = mount(NoteQualityChecklistPanel, {
      props: { items: sampleItems },
      global: globalStubs,
    })
    expect(wrapper.text()).toContain('公式执行错误：除零错误')
    expect(wrapper.text()).toContain('章节数据陈旧')
    expect(wrapper.text()).toContain('手工覆盖未确认')
    expect(wrapper.text()).toContain('AI 草稿未经人工确认')
    expect(wrapper.text()).toContain('章节缺失数据')
  })

  it('展示 blocking 计数', () => {
    const wrapper = mount(NoteQualityChecklistPanel, {
      props: { items: sampleItems },
      global: globalStubs,
    })
    expect(wrapper.text()).toContain('2 项阻止签发')
  })

  it('空列表展示空状态', () => {
    const wrapper = mount(NoteQualityChecklistPanel, {
      props: { items: [] },
      global: globalStubs,
    })
    const empty = wrapper.find('[data-test="empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('暂无质量问题')
  })
})

describe('NoteQualityChecklistPanel — 筛选', () => {
  it('按 blocking 级别筛选', async () => {
    const wrapper = mount(NoteQualityChecklistPanel, {
      props: { items: sampleItems },
      global: globalStubs,
    })
    // Simulate filterLevel change
    const vm = wrapper.vm as any
    vm.filterLevel = 'blocking'
    await wrapper.vm.$nextTick()
    const listItems = wrapper.findAll('.checklist-item')
    expect(listItems.length).toBe(2)
  })

  it('按 warning 级别筛选', async () => {
    const wrapper = mount(NoteQualityChecklistPanel, {
      props: { items: sampleItems },
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.filterLevel = 'warning'
    await wrapper.vm.$nextTick()
    const listItems = wrapper.findAll('.checklist-item')
    expect(listItems.length).toBe(2)
  })

  it('按 category 筛选 formula', async () => {
    const wrapper = mount(NoteQualityChecklistPanel, {
      props: { items: sampleItems },
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.filterCategory = 'formula'
    await wrapper.vm.$nextTick()
    const listItems = wrapper.findAll('.checklist-item')
    expect(listItems.length).toBe(1)
    expect(wrapper.text()).toContain('公式执行错误')
  })

  it('组合筛选 level + category', async () => {
    const wrapper = mount(NoteQualityChecklistPanel, {
      props: { items: sampleItems },
      global: globalStubs,
    })
    const vm = wrapper.vm as any
    vm.filterLevel = 'warning'
    vm.filterCategory = 'stale'
    await wrapper.vm.$nextTick()
    const listItems = wrapper.findAll('.checklist-item')
    expect(listItems.length).toBe(1)
    expect(wrapper.text()).toContain('数据陈旧')
  })
})

describe('NoteQualityChecklistPanel — 跳转', () => {
  it('点击跳转按钮 emit navigate', async () => {
    const wrapper = mount(NoteQualityChecklistPanel, {
      props: { items: sampleItems },
      global: globalStubs,
    })
    const buttons = wrapper.findAll('[data-test="button"]')
    // First item has a route so it should have a jump button
    expect(buttons.length).toBeGreaterThan(0)
    await buttons[0].trigger('click')

    const emitted = wrapper.emitted('navigate')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({
      route: '/projects/{pid}/disclosure-notes?section=accounts_receivable',
      section_id: 'accounts_receivable',
      table_id: 'aging_analysis',
      row_id: 'total',
      col_id: 'closing_balance',
    })
  })

  it('无 route 的条目不显示跳转按钮', () => {
    const itemNoRoute: QualityChecklistItem[] = [
      {
        level: 'info',
        category: 'completeness',
        message: '无路由条目',
      },
    ]
    const wrapper = mount(NoteQualityChecklistPanel, {
      props: { items: itemNoRoute },
      global: globalStubs,
    })
    const buttons = wrapper.findAll('[data-test="button"]')
    expect(buttons.length).toBe(0)
  })
})
