/**
 * NoteDisclosureContextBar.spec.ts — 数据披露四维上下文栏测试
 *
 * Spec:    .kiro/specs/disclosure-note-semantic-structure-and-presentation/ Task 6.6
 * Design:  数据披露四维上下文：单位 | 年度 | 科目/明细 | 金额口径
 * Reqs:    2.1, 2.2, 2.3, 2.4
 *
 * 用例：
 *   1. 渲染四个下拉选择器
 *   2. 切换单位 emit context-change
 *   3. 切换年度 emit context-change
 *   4. 切换科目 emit context-change
 *   5. 切换金额口径 emit context-change
 *   6. 空选项状态
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import NoteDisclosureContextBar from '../NoteDisclosureContextBar.vue'

// Element Plus stubs
const ElSelectStub = {
  name: 'ElSelect',
  template: '<div data-test="select"><slot /></div>',
  props: ['modelValue', 'placeholder', 'size', 'clearable'],
  emits: ['update:modelValue'],
}

const globalStubs = {
  stubs: {
    'el-select': ElSelectStub,
    'el-option': {
      template: '<div data-test="option" :data-value="value"><slot />{{ label }}</div>',
      props: ['label', 'value'],
    },
    'el-tag': {
      template: '<span data-test="tag"><slot /></span>',
      props: ['type', 'size'],
    },
  },
}

const mockEntities = [
  { id: 'e1', name: '测试项目', type: 'project' as const },
  { id: 'e2', name: '子公司A', type: 'subsidiary' as const },
  { id: 'e3', name: '关联方B', type: 'related_party' as const },
]

const mockYears = [2025, 2024, 2023]

const mockAccounts = [
  { code: '1122', name: '应收账款' },
  { code: '1601', name: '固定资产', detail: '房屋建筑物' },
  { code: '1001', name: '货币资金' },
]

const mockAmountRoles = ['closing', 'opening', 'current', 'prior']

const defaultProps = {
  entities: mockEntities,
  years: mockYears,
  accounts: mockAccounts,
  amountRoles: mockAmountRoles,
}

describe('NoteDisclosureContextBar — 渲染四个下拉选择器', () => {
  it('渲染四个 el-select 下拉框', () => {
    const wrapper = mount(NoteDisclosureContextBar, {
      props: defaultProps,
      global: globalStubs,
    })
    const selects = wrapper.findAll('[data-test="select"]')
    expect(selects.length).toBe(4)
  })

  it('显示中文标签：单位、年度、科目/明细、金额口径', () => {
    const wrapper = mount(NoteDisclosureContextBar, {
      props: defaultProps,
      global: globalStubs,
    })
    const labels = wrapper.findAll('.disclosure-context-bar__label')
    expect(labels.length).toBe(4)
    expect(labels[0].text()).toBe('单位')
    expect(labels[1].text()).toBe('年度')
    expect(labels[2].text()).toBe('科目/明细')
    expect(labels[3].text()).toBe('金额口径')
  })

  it('渲染单位选项并显示类型标签', () => {
    const wrapper = mount(NoteDisclosureContextBar, {
      props: defaultProps,
      global: globalStubs,
    })
    const options = wrapper.findAll('[data-test="option"]')
    // 3 entities + 3 years + 3 accounts + 4 roles = 13 options
    expect(options.length).toBe(13)
    // 子公司 tag 存在
    const html = wrapper.html()
    expect(html).toContain('子公司')
    expect(html).toContain('关联方')
  })

  it('科目带明细时显示"名称 - 明细"格式', () => {
    const wrapper = mount(NoteDisclosureContextBar, {
      props: defaultProps,
      global: globalStubs,
    })
    const html = wrapper.html()
    expect(html).toContain('固定资产 - 房屋建筑物')
  })

  it('金额口径显示中文标签', () => {
    const wrapper = mount(NoteDisclosureContextBar, {
      props: defaultProps,
      global: globalStubs,
    })
    const html = wrapper.html()
    expect(html).toContain('期末余额')
    expect(html).toContain('期初余额')
    expect(html).toContain('本期发生')
    expect(html).toContain('上期发生')
  })
})

describe('NoteDisclosureContextBar — 切换单位 emit context-change', () => {
  it('切换单位后 emit context-change 事件', async () => {
    const wrapper = mount(NoteDisclosureContextBar, {
      props: { ...defaultProps, currentYear: 2025, currentAccount: '1122', currentAmountRole: 'closing' },
      global: globalStubs,
    })
    const selects = wrapper.findAllComponents(ElSelectStub)
    // 第一个 select 是单位
    selects[0].vm.$emit('update:modelValue', 'e2')
    await wrapper.vm.$nextTick()

    const emitted = wrapper.emitted('context-change')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({
      entity: 'e2',
      year: 2025,
      account: '1122',
      amountRole: 'closing',
    })
  })
})

describe('NoteDisclosureContextBar — 切换年度 emit context-change', () => {
  it('切换年度后 emit context-change 事件', async () => {
    const wrapper = mount(NoteDisclosureContextBar, {
      props: { ...defaultProps, currentEntity: 'e1', currentAccount: '1122', currentAmountRole: 'closing' },
      global: globalStubs,
    })
    const selects = wrapper.findAllComponents(ElSelectStub)
    // 第二个 select 是年度
    selects[1].vm.$emit('update:modelValue', 2024)
    await wrapper.vm.$nextTick()

    const emitted = wrapper.emitted('context-change')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({
      entity: 'e1',
      year: 2024,
      account: '1122',
      amountRole: 'closing',
    })
  })
})

describe('NoteDisclosureContextBar — 切换科目 emit context-change', () => {
  it('切换科目后 emit context-change 事件', async () => {
    const wrapper = mount(NoteDisclosureContextBar, {
      props: { ...defaultProps, currentEntity: 'e1', currentYear: 2025, currentAmountRole: 'opening' },
      global: globalStubs,
    })
    const selects = wrapper.findAllComponents(ElSelectStub)
    // 第三个 select 是科目
    selects[2].vm.$emit('update:modelValue', '1601')
    await wrapper.vm.$nextTick()

    const emitted = wrapper.emitted('context-change')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({
      entity: 'e1',
      year: 2025,
      account: '1601',
      amountRole: 'opening',
    })
  })
})

describe('NoteDisclosureContextBar — 切换金额口径 emit context-change', () => {
  it('切换金额口径后 emit context-change 事件', async () => {
    const wrapper = mount(NoteDisclosureContextBar, {
      props: { ...defaultProps, currentEntity: 'e1', currentYear: 2025, currentAccount: '1001' },
      global: globalStubs,
    })
    const selects = wrapper.findAllComponents(ElSelectStub)
    // 第四个 select 是金额口径
    selects[3].vm.$emit('update:modelValue', 'prior')
    await wrapper.vm.$nextTick()

    const emitted = wrapper.emitted('context-change')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({
      entity: 'e1',
      year: 2025,
      account: '1001',
      amountRole: 'prior',
    })
  })
})

describe('NoteDisclosureContextBar — 空选项状态', () => {
  it('无任何选项时仍正常渲染四个下拉框', () => {
    const wrapper = mount(NoteDisclosureContextBar, {
      props: {
        entities: [],
        years: [],
        accounts: [],
        amountRoles: [],
      },
      global: globalStubs,
    })
    const selects = wrapper.findAll('[data-test="select"]')
    expect(selects.length).toBe(4)
    // 无 option
    const options = wrapper.findAll('[data-test="option"]')
    expect(options.length).toBe(0)
  })

  it('无当前选中值时 payload 含 undefined', async () => {
    const wrapper = mount(NoteDisclosureContextBar, {
      props: {
        entities: mockEntities,
        years: mockYears,
        accounts: mockAccounts,
        amountRoles: mockAmountRoles,
      },
      global: globalStubs,
    })
    const selects = wrapper.findAllComponents(ElSelectStub)
    selects[0].vm.$emit('update:modelValue', 'e1')
    await wrapper.vm.$nextTick()

    const emitted = wrapper.emitted('context-change')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({
      entity: 'e1',
      year: undefined,
      account: undefined,
      amountRole: undefined,
    })
  })
})
