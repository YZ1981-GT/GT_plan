/**
 * GtAnalyticalReview.spec.ts — 分析性复核组件测试
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import GtAnalyticalReview from '../GtAnalyticalReview.vue'

const mockData = {
  wp_code: 'A1-13',
  scope: 'standalone' as const,
  year: 2025,
  materiality: 100000,
  is_listed: false,
  sheets: {
    bs_horizontal: {
      title: '已审资产负债表（母公司）横向趋势分析',
      index: 'A1-13-1',
      columns: [],
      rows: [
        {
          row_code: 'BS-001',
          name: '货币资金',
          row_number: 1,
          indent_level: 0,
          is_total_row: false,
          prior: 100,
          current: 150,
          change: 50,
          change_pct: 50,
          status: 'significant' as const,
          reason: null,
        },
      ],
    },
    bs_vertical: { title: '纵向', index: 'A1-13-2', columns: [], rows: [] },
    is_horizontal: { title: 'IS横向', index: 'A1-13-3', columns: [], rows: [] },
    is_vertical: { title: 'IS纵向', index: 'A1-13-4', columns: [], rows: [] },
    ratio_analysis: {
      title: '比率分析',
      index: 'A1-13-5',
      categories: [
        {
          name: '盈利能力',
          items: [
            {
              seq: 1,
              name: '毛利率',
              formula: 'A/B',
              prior_numerator: null,
              prior_denominator: null,
              prior_value: 0.3,
              current_numerator: null,
              current_denominator: null,
              current_value: 0.35,
              change: 0.05,
              direction: 'up' as const,
              normal_value: null,
            },
          ],
        },
      ],
      notes: ['测试注释'],
    },
    industry_comparison: null,
    eps_roe: null,
  },
}

const globalStubs = {
  'el-tabs': { template: '<div class="el-tabs"><slot /></div>', props: ['modelValue'] },
  'el-tab-pane': { template: '<div class="el-tab-pane"><slot /></div>', props: ['label', 'name'] },
  'el-input': {
    template: '<input class="el-input" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
    props: ['modelValue', 'size', 'placeholder', 'disabled'],
    emits: ['update:modelValue', 'input'],
  },
}

describe('GtAnalyticalReview', () => {
  it('渲染标题和 scope 标签', () => {
    const wrapper = mount(GtAnalyticalReview, {
      props: { wpId: 'wp-1', htmlData: { analytical_review: mockData } },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.gt-analytical-review__title').text()).toContain('母公司')
    expect(wrapper.find('.gt-analytical-review__meta').text()).toContain('A1-13')
  })

  it('BS 横向表渲染显著变动行', () => {
    const wrapper = mount(GtAnalyticalReview, {
      props: { wpId: 'wp-1', htmlData: { analytical_review: mockData } },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.row-significant').exists()).toBe(true)
    expect(wrapper.text()).toContain('货币资金')
    expect(wrapper.text()).toContain('显著')
  })

  it('上市公司 A1-14 显示同行业和 EPS Tab 数据', async () => {
    const listedData = {
      ...mockData,
      wp_code: 'A1-14',
      scope: 'consolidated' as const,
      is_listed: true,
      sheets: {
        ...mockData.sheets,
        industry_comparison: {
          title: '同行业对比分析',
          index: 'A1-14-6',
          years: [2023, 2024, 2025],
          companies: [{ key: 'A', name: '可比A', stock_code: '000001' }],
          financial_data: { total_assets: { '2025': { self: 1000 } } },
          comparison_table: { roe: { '2025': { self: 0.12 } } },
          financial_metric_labels: { total_assets: '资产总额' },
          comparison_metric_labels: { roe: '净资产收益率' },
          data_source_note: 'Wind',
        },
        eps_roe: {
          title: 'EPS-ROE',
          index: 'A1-14-7',
          year: 2025,
          inputs: { net_profit: 100, equity_end: 500, equity_begin: 400, weighted_avg_shares: 50 },
          share_changes: [],
          computed: { roe_diluted: 20, roe_weighted: 22, basic_eps: 2, diluted_eps: 1.8 },
          notes: ['CAS 34'],
        },
      },
    }
    const wrapper = mount(GtAnalyticalReview, {
      props: { wpId: 'wp-2', htmlData: { analytical_review: listedData } },
      global: { stubs: globalStubs },
    })
    expect(wrapper.text()).toContain('合并')
  })

  it('显著变动行显示原因输入框', () => {
    const wrapper = mount(GtAnalyticalReview, {
      props: { wpId: 'wp-1', htmlData: { analytical_review: mockData } },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.col-reason input').exists()).toBe(true)
  })
})
