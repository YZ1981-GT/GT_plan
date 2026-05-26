/**
 * GtDForm.spec.ts — D 类检查表顶层路由组件单元测试
 *
 * spec workpaper-html-renderer Task 8.8（5 子模式分发测试）
 *
 * 验证：
 * 1. schema.form_type='table' → 渲染 GtDFormTable
 * 2. schema.form_type='paragraph' → 渲染 GtDFormParagraph
 * 3. schema.form_type='qa' → 渲染 GtDFormQA
 * 4. schema.form_type='confirmation' → 渲染 GtDFormConfirmation
 * 5. schema.form_type='review' → 渲染 GtDFormReview
 * 6. 未知 form_type → 渲染兜底 "无法识别的 D 子模式"
 * 7. formType prop fallback ('d-form-table' → 'table')
 * 8. emit 转发：field-change / save / sign / jump-to-reference
 *
 * Validates: Requirements 3.5（D 类 5 子模式分发）
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, defineComponent, h } from 'vue'

// Stub child components BEFORE importing GtDForm to make Vue resolve to stubs.
// Each stub renders its name into the DOM so we can assert which mode was selected.
vi.mock('../GtDFormTable.vue', () => ({
  default: defineComponent({
    name: 'GtDFormTable',
    props: ['wpId', 'sheetName', 'schema', 'htmlData', 'readonly'],
    emits: ['field-change', 'jump-to-reference', 'save'],
    setup(_props, { emit }) {
      return () =>
        h(
          'div',
          { class: 'stub-table', 'data-stub': 'table' },
          [
            'GtDFormTable Stub',
            h('button', {
              class: 'stub-table-emit',
              onClick: () =>
                emit('field-change', { field_name: 'test', new_value: 'hello' }),
            }),
          ],
        )
    },
  }),
}))

vi.mock('../GtDFormParagraph.vue', () => ({
  default: defineComponent({
    name: 'GtDFormParagraph',
    props: ['wpId', 'sheetName', 'schema', 'htmlData', 'readonly'],
    emits: ['field-change', 'jump-to-reference', 'save'],
    setup() {
      return () => h('div', { class: 'stub-paragraph', 'data-stub': 'paragraph' }, 'GtDFormParagraph Stub')
    },
  }),
}))

vi.mock('../GtDFormQA.vue', () => ({
  default: defineComponent({
    name: 'GtDFormQA',
    props: ['wpId', 'sheetName', 'schema', 'htmlData', 'readonly'],
    emits: ['field-change', 'jump-to-reference', 'save'],
    setup() {
      return () => h('div', { class: 'stub-qa', 'data-stub': 'qa' }, 'GtDFormQA Stub')
    },
  }),
}))

vi.mock('../GtDFormConfirmation.vue', () => ({
  default: defineComponent({
    name: 'GtDFormConfirmation',
    props: ['wpId', 'sheetName', 'schema', 'htmlData', 'readonly'],
    emits: ['field-change', 'jump-to-reference', 'save'],
    setup(_props, { emit }) {
      return () =>
        h(
          'div',
          { class: 'stub-confirmation', 'data-stub': 'confirmation' },
          [
            'GtDFormConfirmation Stub',
            h('button', {
              class: 'stub-confirmation-jump',
              onClick: () => emit('jump-to-reference', 'D2-1'),
            }),
          ],
        )
    },
  }),
}))

vi.mock('../GtDFormReview.vue', () => ({
  default: defineComponent({
    name: 'GtDFormReview',
    props: ['wpId', 'sheetName', 'schema', 'htmlData', 'readonly'],
    emits: ['field-change', 'jump-to-reference', 'save', 'sign'],
    setup(_props, { emit }) {
      return () =>
        h(
          'div',
          { class: 'stub-review', 'data-stub': 'review' },
          [
            'GtDFormReview Stub',
            h('button', {
              class: 'stub-review-sign',
              onClick: () =>
                emit('sign', {
                  role: 'preparer',
                  signed_by: '张三',
                  signed_at: '2026-01-10T08:00:00Z',
                }),
            }),
          ],
        )
    },
  }),
}))

// Import AFTER mocks so the resolved component graph picks up the stubs
import GtDForm from '../GtDForm.vue'

const globalStubs = {
  'el-result': {
    template:
      '<div class="el-result" :data-icon="icon"><div class="el-result__title">{{ title }}</div><slot /><slot name="sub-title" /></div>',
    props: ['icon', 'title'],
  },
}

describe('GtDForm — 5 子模式分发', () => {
  it('schema.form_type=table → 渲染 GtDFormTable', () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: '关联方检查',
        schema: { form_type: 'table' },
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    expect(wrapper.find('[data-stub="table"]').exists()).toBe(true)
    expect(wrapper.find('[data-stub="paragraph"]').exists()).toBe(false)
    expect(wrapper.find('[data-stub="qa"]').exists()).toBe(false)
  })

  it('schema.form_type=paragraph → 渲染 GtDFormParagraph', () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: '会计政策',
        schema: { form_type: 'paragraph' },
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    expect(wrapper.find('[data-stub="paragraph"]').exists()).toBe(true)
    expect(wrapper.find('[data-stub="table"]').exists()).toBe(false)
  })

  it('schema.form_type=qa → 渲染 GtDFormQA', () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款业务模式分析',
        schema: { form_type: 'qa' },
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    expect(wrapper.find('[data-stub="qa"]').exists()).toBe(true)
    expect(wrapper.find('[data-stub="confirmation"]').exists()).toBe(false)
  })

  it('schema.form_type=confirmation → 渲染 GtDFormConfirmation', () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: '函证统计',
        schema: { form_type: 'confirmation' },
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    expect(wrapper.find('[data-stub="confirmation"]').exists()).toBe(true)
    expect(wrapper.find('[data-stub="qa"]').exists()).toBe(false)
  })

  it('schema.form_type=review → 渲染 GtDFormReview', () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: '复核记录',
        schema: { form_type: 'review' },
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    expect(wrapper.find('[data-stub="review"]').exists()).toBe(true)
    expect(wrapper.find('[data-stub="confirmation"]').exists()).toBe(false)
  })
})

describe('GtDForm — 未识别 form_type 兜底', () => {
  it('未知 form_type 渲染 "无法识别的 D 子模式"', () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: '某未知 sheet',
        schema: { form_type: 'unknown_mode' as any },
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    expect(wrapper.text()).toContain('无法识别的 D 子模式')
    // 5 sub-form stubs should not render
    expect(wrapper.find('[data-stub="table"]').exists()).toBe(false)
    expect(wrapper.find('[data-stub="paragraph"]').exists()).toBe(false)
    expect(wrapper.find('[data-stub="qa"]').exists()).toBe(false)
    expect(wrapper.find('[data-stub="confirmation"]').exists()).toBe(false)
    expect(wrapper.find('[data-stub="review"]').exists()).toBe(false)
  })

  it('schema.form_type 缺失 + formType prop 也缺失 → 兜底', () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: '某 sheet',
        schema: {} as any,
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    expect(wrapper.text()).toContain('无法识别的 D 子模式')
  })
})

describe('GtDForm — formType prop fallback', () => {
  it('schema.form_type 缺失但 formType="d-form-table" → 渲染 GtDFormTable', () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: '关联方检查',
        schema: {} as any,
        htmlData: {},
        formType: 'd-form-table',
      },
      global: { stubs: globalStubs },
    })

    expect(wrapper.find('[data-stub="table"]').exists()).toBe(true)
  })

  it('formType="d-form-confirmation" → 渲染 GtDFormConfirmation', () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: '函证统计',
        schema: {} as any,
        htmlData: {},
        formType: 'd-form-confirmation',
      },
      global: { stubs: globalStubs },
    })

    expect(wrapper.find('[data-stub="confirmation"]').exists()).toBe(true)
  })

  it('schema.form_type 优先于 formType prop', () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: 'mixed',
        schema: { form_type: 'qa' },
        htmlData: {},
        formType: 'd-form-table', // should be ignored
      },
      global: { stubs: globalStubs },
    })

    // schema wins
    expect(wrapper.find('[data-stub="qa"]').exists()).toBe(true)
    expect(wrapper.find('[data-stub="table"]').exists()).toBe(false)
  })
})

describe('GtDForm — emit 转发', () => {
  it('子组件 field-change 通过 GtDForm 透传', async () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: 'x',
        schema: { form_type: 'table' },
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    await wrapper.find('.stub-table-emit').trigger('click')
    await nextTick()

    const emitted = wrapper.emitted('field-change')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toMatchObject({
      field_name: 'test',
      new_value: 'hello',
    })
  })

  it('子组件 jump-to-reference 通过 GtDForm 透传', async () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: 'x',
        schema: { form_type: 'confirmation' },
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    await wrapper.find('.stub-confirmation-jump').trigger('click')
    await nextTick()

    const emitted = wrapper.emitted('jump-to-reference')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toBe('D2-1')
  })

  it('GtDFormReview 的 sign 事件透传到 GtDForm', async () => {
    const wrapper = mount(GtDForm, {
      props: {
        wpId: 'wp-001',
        sheetName: 'x',
        schema: { form_type: 'review' },
        htmlData: {},
      },
      global: { stubs: globalStubs },
    })

    await wrapper.find('.stub-review-sign').trigger('click')
    await nextTick()

    const emitted = wrapper.emitted('sign')
    expect(emitted).toBeDefined()
    const payload = emitted![0][0] as any
    expect(payload.role).toBe('preparer')
    expect(payload.signed_by).toBe('张三')
  })
})
