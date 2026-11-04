import { describe, expect, it, vi } from 'vitest'

vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn() } }))

import {
  TABS,
  VISIBLE_TABS,
  changeRate,
  equityCell,
  isGenerated,
  mapCrossCheck,
  mergeCompare,
  periodLabels,
  type ReportRow,
} from '../useCitarReportAnalysis'

const row = (code: string, cur: unknown, prior: unknown = null, extra: Partial<ReportRow> = {}): ReportRow =>
  ({ row_code: code, row_name: code, current_period_amount: cur as any, prior_period_amount: prior as any, ...extra })

describe('报表分析标签', () => {
  it('旧财务报表页的 6 张报表都在，分析组在后', () => {
    expect(TABS.filter(t => t.group === 'report').map(t => t.key)).toEqual([
      'balance_sheet', 'income_statement', 'cash_flow_statement',
      'equity_statement', 'cash_flow_supplement', 'impairment_provision',
    ])
    expect(TABS.filter(t => t.group === 'analysis').map(t => t.label)).toEqual(['智能核对', '多年对比', '变动分析', '财务指标'])
  })

  it('页面只显示资产负债表、利润表与分析组（其余四张表隐藏）', () => {
    expect(VISIBLE_TABS.map(t => t.label)).toEqual([
      '资产负债表', '利润表', '智能核对', '多年对比', '变动分析', '财务指标',
    ])
  })

  it('时点报表与期间报表列名不同', () => {
    expect(periodLabels('balance_sheet')).toEqual(['期末数', '期初数'])
    expect(periodLabels('income_statement')).toEqual(['本期金额', '上期金额'])
    expect(periodLabels('impairment_provision')).toEqual(['期末账面余额', '年初账面余额'])
  })
})

describe('对比视图', () => {
  it('按 row_code 合并未审数，算调整影响、变动额、变动率', () => {
    const [r] = mergeCompare([row('BS-002', '120', '100')], [row('BS-002', '110')])
    expect(r).toMatchObject({ audited: 120, unadjusted: 110, adjustment: 10, prior: 100, change: 20, change_rate: 20 })
  })

  it('上期为空或 0 时没有变动率，也不算变动额', () => {
    const [a, b] = mergeCompare([row('A', '50', null), row('B', '50', '0')], [])
    expect(a.change).toBeNull()
    expect(a.change_rate).toBeNull()
    expect(b.change).toBe(50)
    expect(b.change_rate).toBeNull()
    expect(a.unadjusted).toBeNull()
    expect(a.adjustment).toBeNull()
  })

  it('变动率分母取绝对值', () => {
    expect(changeRate(-80, -100)).toBe(20)
  })

  it('金额全空 = 未生成', () => {
    expect(isGenerated([row('A', null), row('B', null)])).toBe(false)
    expect(isGenerated([row('A', null), row('B', '0')])).toBe(true)
  })
})

describe('权益变动表矩阵', () => {
  it('有矩阵取矩阵列', () => {
    const r = row('EQ-001', '-1', null, { source_accounts: { eq_matrix: { current_year: { retained_earnings: 6292664.3, total_equity: 6292664.3 } } } })
    expect(equityCell(r, 'retained_earnings')).toBe(6292664.3)
    expect(equityCell(r, 'total_equity')).toBe(6292664.3)
    expect(equityCell(r, 'capital_reserve')).toBeNull()
  })

  it('没有矩阵的行只有合计列有数，其余留空', () => {
    const r = row('EQ-005', '0', null, { source_accounts: ['3102'] })
    expect(equityCell(r, 'total_equity')).toBe(0)
    expect(equityCell(r, 'share_capital')).toBeNull()
  })
})

describe('跨表核对', () => {
  it('用 inputs 与 refs 显示左右值（Issue 不带左右值时）', () => {
    const rows = mapCrossCheck({
      results: [
        { formula_id: 'report-cross-check-1', description: '资产合计 = 负债合计 + 所有者权益合计', passed: false, refs: ['assets_total', 'liabilities_total', 'equity_total'] },
      ],
      issue_list: [{ formula_id: 'report-cross-check-1', left_value: null, right_value: null }],
      inputs: { assets_total: '1000', liabilities_total: '600', equity_total: '300' },
    })
    expect(rows[0]).toMatchObject({ passed: false })
    expect(rows[0].values).toEqual([
      { key: 'assets_total', label: '资产总计', amount: 1000 },
      { key: 'liabilities_total', label: '负债合计', amount: 600 },
      { key: 'equity_total', label: '所有者权益合计', amount: 300 },
    ])
  })
})
