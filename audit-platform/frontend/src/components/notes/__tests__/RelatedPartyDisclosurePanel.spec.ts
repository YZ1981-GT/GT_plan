/**
 * RelatedPartyDisclosurePanel.spec.ts — 关联方披露专项面板测试
 *
 * Spec:    .kiro/specs/disclosure-note-semantic-structure-and-presentation/ Task 13.6.8
 * Design:  关联方披露专项
 * Reqs:    9.1, 9.2, 9.3, 9.4
 *
 * 用例：
 *   1. 渲染主体列表
 *   2. 渲染交易列表
 *   3. 渲染余额列表
 *   4. 渲染证据列表
 *   5. 渲染 tie-out 差异
 *   6. 差异计数标签
 *   7. 空数据展示空状态
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RelatedPartyDisclosurePanel from '../RelatedPartyDisclosurePanel.vue'
import type {
  RelatedParty,
  RelatedPartyTransaction,
  RelatedPartyBalance,
  RelatedPartyEvidence,
  TieoutResult,
} from '../RelatedPartyDisclosurePanel.vue'

// Element Plus stubs
const ElTabsStub = {
  name: 'ElTabs',
  template: '<div data-test="tabs"><slot /></div>',
  props: ['modelValue'],
  emits: ['update:modelValue'],
}

const ElTabPaneStub = {
  name: 'ElTabPane',
  template: '<div data-test="tab-pane" :data-name="name"><slot /></div>',
  props: ['label', 'name'],
}

const ElTableStub = {
  name: 'ElTable',
  template: '<table data-test="table"><slot /></table>',
  props: ['data', 'size', 'stripe'],
}

const ElTableColumnStub = {
  name: 'ElTableColumn',
  template: '<col data-test="column" />',
  props: ['prop', 'label', 'width', 'minWidth', 'align'],
}

const ElTagStub = {
  name: 'ElTag',
  template: '<span data-test="tag" :data-type="type"><slot /></span>',
  props: ['type', 'size'],
}

const ElEmptyStub = {
  name: 'ElEmpty',
  template: '<div data-test="empty">{{ description }}</div>',
  props: ['description'],
}

const globalStubs = {
  stubs: {
    'el-tabs': ElTabsStub,
    'el-tab-pane': ElTabPaneStub,
    'el-table': ElTableStub,
    'el-table-column': ElTableColumnStub,
    'el-tag': ElTagStub,
    'el-empty': ElEmptyStub,
  },
}

// Sample data
const sampleParties: RelatedParty[] = [
  {
    party_id: 'rp_001',
    party_name: 'A 集团',
    relationship_type: '母公司',
    relationship_description: '控股母公司',
  },
  {
    party_id: 'rp_002',
    party_name: 'B 科技',
    relationship_type: '子公司',
    relationship_description: '全资子公司',
  },
]

const sampleTransactions: RelatedPartyTransaction[] = [
  {
    party_id: 'rp_001',
    transaction_type: '采购',
    current_amount: '500000.00',
    prior_amount: '400000.00',
  },
]

const sampleBalances: RelatedPartyBalance[] = [
  {
    party_id: 'rp_001',
    balance_type: 'receivable',
    closing_balance: '100000.00',
    opening_balance: '80000.00',
  },
]

const sampleEvidences: RelatedPartyEvidence[] = [
  {
    party_id: 'rp_001',
    has_confirmation: true,
    has_attachment: true,
    confirmation_status: 'confirmed',
  },
]

const sampleTieoutResults: TieoutResult[] = [
  {
    rule_description: '关联方应收余额合计 vs 报表',
    note_total: '100000.00',
    report_amount: '100000.00',
    difference: '0.00',
    is_balanced: true,
  },
  {
    rule_description: '关联方应付余额合计 vs 报表',
    note_total: '50000.00',
    report_amount: '80000.00',
    difference: '30000.00',
    is_balanced: false,
  },
]

function mountPanel(overrides: Partial<{
  parties: RelatedParty[]
  transactions: RelatedPartyTransaction[]
  balances: RelatedPartyBalance[]
  evidences: RelatedPartyEvidence[]
  tieoutResults: TieoutResult[]
}> = {}) {
  return mount(RelatedPartyDisclosurePanel, {
    props: {
      parties: overrides.parties ?? sampleParties,
      transactions: overrides.transactions ?? sampleTransactions,
      balances: overrides.balances ?? sampleBalances,
      evidences: overrides.evidences ?? sampleEvidences,
      tieoutResults: overrides.tieoutResults ?? sampleTieoutResults,
    },
    global: globalStubs,
  })
}

describe('RelatedPartyDisclosurePanel — 渲染', () => {
  it('渲染标题', () => {
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('关联方披露专项')
  })

  it('渲染 tabs 区域', () => {
    const wrapper = mountPanel()
    const tabs = wrapper.find('[data-test="tabs"]')
    expect(tabs.exists()).toBe(true)
  })

  it('渲染五个 tab-pane', () => {
    const wrapper = mountPanel()
    const panes = wrapper.findAll('[data-test="tab-pane"]')
    expect(panes.length).toBe(5)
  })

  it('主体 tab 包含关联方名称', () => {
    const wrapper = mountPanel()
    const partiesPane = wrapper.find('[data-name="parties"]')
    expect(partiesPane.exists()).toBe(true)
    // Table stub is rendered when data exists
    const table = partiesPane.find('[data-test="table"]')
    expect(table.exists()).toBe(true)
  })

  it('交易 tab 渲染表格', () => {
    const wrapper = mountPanel()
    const txPane = wrapper.find('[data-name="transactions"]')
    expect(txPane.exists()).toBe(true)
    const table = txPane.find('[data-test="table"]')
    expect(table.exists()).toBe(true)
  })

  it('余额 tab 渲染表格', () => {
    const wrapper = mountPanel()
    const balPane = wrapper.find('[data-name="balances"]')
    expect(balPane.exists()).toBe(true)
    const table = balPane.find('[data-test="table"]')
    expect(table.exists()).toBe(true)
  })

  it('证据 tab 渲染表格', () => {
    const wrapper = mountPanel()
    const evPane = wrapper.find('[data-name="evidences"]')
    expect(evPane.exists()).toBe(true)
    const table = evPane.find('[data-test="table"]')
    expect(table.exists()).toBe(true)
  })

  it('差异 tab 渲染表格', () => {
    const wrapper = mountPanel()
    const tieoutPane = wrapper.find('[data-name="tieout"]')
    expect(tieoutPane.exists()).toBe(true)
    const table = tieoutPane.find('[data-test="table"]')
    expect(table.exists()).toBe(true)
  })
})

describe('RelatedPartyDisclosurePanel — 差异计数', () => {
  it('有差异时显示计数标签', () => {
    const wrapper = mountPanel()
    // sampleTieoutResults has 1 unbalanced item
    const tags = wrapper.findAll('[data-test="tag"]')
    const diffTag = tags.find(t => t.text().includes('1 项差异'))
    expect(diffTag).toBeTruthy()
  })

  it('全部平衡时不显示计数标签', () => {
    const wrapper = mountPanel({
      tieoutResults: [
        {
          rule_description: '测试',
          note_total: '100',
          report_amount: '100',
          difference: '0',
          is_balanced: true,
        },
      ],
    })
    const text = wrapper.text()
    expect(text).not.toContain('项差异')
  })
})

describe('RelatedPartyDisclosurePanel — 空数据', () => {
  it('主体为空显示空状态', () => {
    const wrapper = mountPanel({ parties: [] })
    const partiesPane = wrapper.find('[data-name="parties"]')
    const empty = partiesPane.find('[data-test="empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('暂无关联方主体')
  })

  it('交易为空显示空状态', () => {
    const wrapper = mountPanel({ transactions: [] })
    const txPane = wrapper.find('[data-name="transactions"]')
    const empty = txPane.find('[data-test="empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('暂无关联方交易')
  })

  it('余额为空显示空状态', () => {
    const wrapper = mountPanel({ balances: [] })
    const balPane = wrapper.find('[data-name="balances"]')
    const empty = balPane.find('[data-test="empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('暂无关联方余额')
  })

  it('证据为空显示空状态', () => {
    const wrapper = mountPanel({ evidences: [] })
    const evPane = wrapper.find('[data-name="evidences"]')
    const empty = evPane.find('[data-test="empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('暂无证据信息')
  })

  it('tie-out 为空显示空状态', () => {
    const wrapper = mountPanel({ tieoutResults: [] })
    const tieoutPane = wrapper.find('[data-name="tieout"]')
    const empty = tieoutPane.find('[data-test="empty"]')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('暂无 tie-out 结果')
  })
})
