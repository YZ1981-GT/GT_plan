/**
 * NotePolicyReviewPanel.spec.ts — 政策条款审阅面板测试
 *
 * Spec:    .kiro/specs/disclosure-note-semantic-structure-and-presentation/ Task 5.8
 * Design:  会计政策条款结构 _policy_clauses sidecar
 * Reqs:    1.1, 1.2, 1.3, 1.4, 1.5
 *
 * 用例：
 *   1. 渲染条款列表 + 三栏对照
 *   2. 筛选功能：只看有差异 / 只看未确认
 *   3. 批量确认 emit
 *   4. 变量高亮
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'

// el-* 组件 stub
const globalStubs = {
  stubs: {
    'el-radio-group': {
      template: '<div data-test="radio-group"><slot /></div>',
      props: ['modelValue', 'size'],
      emits: ['update:modelValue'],
    },
    'el-radio-button': {
      template: '<button data-test="radio-btn" :data-value="value" @click="$parent.$emit(\'update:modelValue\', value)"><slot /></button>',
      props: ['value'],
    },
    'el-button': {
      template: '<button data-test="btn" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>',
      props: ['disabled', 'size', 'type'],
      emits: ['click'],
    },
    'el-tag': {
      template: '<span data-test="tag" :data-type="type"><slot /></span>',
      props: ['type', 'size'],
    },
    'el-empty': {
      template: '<div data-test="empty">{{ description }}</div>',
      props: ['description'],
    },
  },
}

import NotePolicyReviewPanel from '../NotePolicyReviewPanel.vue'
import type { NotePolicyClause } from '@/types/noteSemantic'

const mockClauses: NotePolicyClause[] = [
  {
    clause_id: 'c1',
    title: '存货',
    level: 1,
    current_text: '本公司采用{{company_name}}方法核算存货。',
    template_text: '本公司采用成本法核算存货。',
    prior_year_text: '本公司采用成本法核算存货。',
    variables: ['company_name'],
    diff_status: 'changed',
    confirm_status: 'pending',
  },
  {
    clause_id: 'c2',
    title: '固定资产',
    level: 1,
    current_text: '固定资产按成本计量。',
    template_text: '固定资产按成本计量。',
    prior_year_text: '固定资产按成本计量。',
    variables: [],
    diff_status: 'unchanged',
    confirm_status: 'pending',
  },
  {
    clause_id: 'c3',
    title: '无形资产',
    level: 1,
    current_text: '无形资产按实际成本入账。',
    template_text: '无形资产按实际成本入账。',
    prior_year_text: '无形资产按实际成本入账。',
    variables: [],
    diff_status: 'unchanged',
    confirm_status: 'confirmed',
  },
  {
    clause_id: 'c4',
    title: '收入确认',
    level: 1,
    current_text: '本年新增收入确认政策。',
    template_text: null,
    prior_year_text: null,
    variables: [],
    diff_status: 'added',
    confirm_status: 'pending',
  },
]

describe('NotePolicyReviewPanel — 渲染条款列表 + 三栏对照', () => {
  it('渲染所有条款目录', () => {
    const wrapper = mount(NotePolicyReviewPanel, {
      props: { clauses: mockClauses },
      global: globalStubs,
    })
    const tocItems = wrapper.findAll('.toc-item')
    expect(tocItems.length).toBe(4)
    expect(tocItems[0].text()).toContain('存货')
    expect(tocItems[1].text()).toContain('固定资产')
  })

  it('默认选中第一个条款显示三栏', () => {
    const wrapper = mount(NotePolicyReviewPanel, {
      props: { clauses: mockClauses },
      global: globalStubs,
    })
    const columns = wrapper.findAll('.clause-col')
    expect(columns.length).toBe(3)
    // 模板、上年、本年列都存在
    expect(wrapper.find('.clause-col--template').exists()).toBe(true)
    expect(wrapper.find('.clause-col--prior').exists()).toBe(true)
    expect(wrapper.find('.clause-col--current').exists()).toBe(true)
  })

  it('显示差异状态标签', () => {
    const wrapper = mount(NotePolicyReviewPanel, {
      props: { clauses: mockClauses },
      global: globalStubs,
    })
    const html = wrapper.html()
    // 第一条有「变更」标签
    expect(html).toContain('变更')
  })
})

describe('NotePolicyReviewPanel — 筛选功能', () => {
  it('切换到"只看有差异"模式过滤 unchanged 条款', async () => {
    const wrapper = mount(NotePolicyReviewPanel, {
      props: { clauses: mockClauses },
      global: globalStubs,
    })

    // 模拟设置 filterMode
    const vm = wrapper.vm as any
    vm.filterMode = 'changed'
    await wrapper.vm.$nextTick()

    const tocItems = wrapper.findAll('.toc-item')
    // 只有 changed + added = 2 条
    expect(tocItems.length).toBe(2)
  })

  it('切换到"只看未确认"模式过滤 confirmed 条款', async () => {
    const wrapper = mount(NotePolicyReviewPanel, {
      props: { clauses: mockClauses },
      global: globalStubs,
    })

    const vm = wrapper.vm as any
    vm.filterMode = 'pending'
    await wrapper.vm.$nextTick()

    const tocItems = wrapper.findAll('.toc-item')
    // pending 有 c1, c2, c4 = 3 条
    expect(tocItems.length).toBe(3)
  })
})

describe('NotePolicyReviewPanel — 批量确认', () => {
  it('点击批量确认按钮 emit batch-confirm 事件', async () => {
    const wrapper = mount(NotePolicyReviewPanel, {
      props: { clauses: mockClauses },
      global: globalStubs,
    })

    const btn = wrapper.find('[data-test="btn"]')
    await btn.trigger('click')

    const emitted = wrapper.emitted('batch-confirm')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual(['c2']) // 只有 c2 是 unchanged + pending
  })

  it('无可确认条款时按钮禁用', () => {
    const allConfirmed = mockClauses.map(c => ({ ...c, confirm_status: 'confirmed' as const }))
    const wrapper = mount(NotePolicyReviewPanel, {
      props: { clauses: allConfirmed },
      global: globalStubs,
    })

    const btn = wrapper.find('[data-test="btn"]')
    expect(btn.attributes('disabled')).toBeDefined()
  })
})

describe('NotePolicyReviewPanel — 变量高亮', () => {
  it('模板变量 {{xxx}} 被 mark 标签包裹', () => {
    const wrapper = mount(NotePolicyReviewPanel, {
      props: { clauses: mockClauses },
      global: globalStubs,
    })
    const html = wrapper.html()
    expect(html).toContain('var-highlight')
    expect(html).toContain('company_name')
  })

  it('无内容时显示"暂无内容"', () => {
    const clauseWithNull: NotePolicyClause[] = [
      {
        clause_id: 'empty',
        title: '空条款',
        level: 1,
        current_text: '有内容',
        template_text: null,
        prior_year_text: null,
        variables: [],
        diff_status: 'added',
        confirm_status: 'pending',
      },
    ]
    const wrapper = mount(NotePolicyReviewPanel, {
      props: { clauses: clauseWithNull },
      global: globalStubs,
    })
    const html = wrapper.html()
    expect(html).toContain('暂无内容')
  })
})
