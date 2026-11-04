/**
 * 单体财务报表「其他问题」点击定位：切到问题所在页签、滚到该行并高亮；同一问题多个位置再点轮换；
 * 位置在隐藏页签（现金流量表）上的提示不可点；刷新后去掉高亮。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import type { FinancialStatementsData, FsRow } from '../taxAssuranceApi'

const api = vi.hoisted(() => ({ fetch: vi.fn(), goSegment: vi.fn() }))

vi.mock('../useCitarProject', () => ({
  fmtMoney: (v: unknown) => (v == null ? '' : String(v)),
  useCitarProject: () => ({
    projectId: ref('p1'), year: ref(2025), yearLoading: ref(false), entityName: ref('甲公司'), goSegment: api.goSegment,
  }),
}))
vi.mock('../taxAssuranceApi', () => ({
  fetchFinancialStatements: api.fetch,
  saveFinancialStatements: vi.fn(),
  downloadTaxAssurance: vi.fn(),
  numberOf: (v: any) => (v && 'n' in v ? Number(v.n) : null),
}))
vi.mock('../citarReportManual', () => ({ saveReportManualValues: vi.fn() }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import CitarFinancialStatements from '../screens/CitarFinancialStatements.vue'

const row = (r: number, label: string, extra: Partial<FsRow> = {}): FsRow => ({
  r, label, indent: 0, heading: false, total: false, note: null,
  current: { n: '1' } as any, prior: { n: '1' } as any, manual: null, ...extra,
})

const PRIOR_NOTICE = '利润表上期金额为空：上年试算表没有数据'
const CF_NOTICE = '现金流量表取平台已生成的现金流量表，尚未生成'

function payload(): FinancialStatementsData {
  return {
    year: 2025, version: 0, entity_name: '甲公司', format: 'enterprise_system', format_label: '企业会计制度',
    standard_code: '', format_source: 'chart',
    statements: [
      { key: 'balance_sheet', title: '资产负债表', attachment: null, columns: ['期末余额', '上年年末余额'], source: 'fs',
        rows: [row(7, '货币资金'), row(47, '资产总计', { total: true })] },
      { key: 'balance_sheet_liabilities', title: '资产负债表（续）', attachment: null, columns: ['期末余额', '上年年末余额'], source: 'fs',
        rows: [row(35, '负债合计'), row(46, '负债和所有者权益总计', { total: true })] },
      { key: 'income_statement', title: '利润表', attachment: null, columns: ['本期金额', '上期金额'], source: 'fs',
        rows: [row(6, '一、主营业务收入'), row(25, '五、净利润')] },
      { key: 'cash_flow_statement', title: '现金流量表', attachment: null, columns: ['本期金额', '上期金额'], source: 'fs', rows: [] },
    ],
    notices: [PRIOR_NOTICE, CF_NOTICE],
    notice_targets: {
      [PRIOR_NOTICE]: [{ statement: 'income_statement', r: null, column: 'prior' }],
      [CF_NOTICE]: [{ statement: 'cash_flow_statement', r: null, column: null }],
    },
    checks: [{
      label: '期末资产总计 − 负债和所有者权益总计', difference: { n: '-100' } as any, ok: false,
      targets: [
        { statement: 'balance_sheet', r: 47, column: 'current' },
        { statement: 'balance_sheet_liabilities', r: 46, column: 'current' },
      ],
    }],
  }
}

async function setup() {
  const scroll = vi.fn()
  Element.prototype.scrollIntoView = scroll
  const w = mount(CitarFinancialStatements, { attachTo: document.body })
  await flushPromises()
  return { w, scroll }
}

const activeTab = (w: any) => w.find('.aud-tab--active').text()

/** 期末不平带差额来源（spec citar-fs-issue-source-locate） */
function withSources(): FinancialStatementsData {
  const d = payload()
  d.notice_sources = { [PRIOR_NOTICE]: [{ kind: 'page', title: '导入 2024 年账套', amount: null, page: 'ledger_import', rows: [], more: 0 }] }
  d.checks[0].sources = [
    {
      kind: 'ledger_mismatch', title: '科目余额表本期发生额与序时账不一致', amount: { n: '-50' } as any, page: 'balance', more: 0,
      rows: [{ code: '5801', name: '以前年度损益调整', amount: { n: '-50' } as any, note: '余额表 借 -50.00', journal: true }],
    },
    {
      kind: 'manual', title: '本页手工修改的金额', amount: { n: '-50' } as any, page: 'statement', more: 0,
      rows: [{ code: '', name: '负债合计', amount: { n: '-50' } as any, note: '手工值', statement: 'balance_sheet_liabilities', r: 35, column: 'current' }],
    },
    { kind: 'unexplained', title: '其余差额未能定位到具体数据行', amount: { n: '0.01' } as any, page: null, rows: [], more: 0 },
  ]
  return d
}

describe('CitarFinancialStatements 其他问题定位', () => {
  beforeEach(() => {
    api.fetch.mockReset()
    api.goSegment.mockReset()
    api.fetch.mockResolvedValue(payload())
  })

  it('数据源头：点客户科目行到科目余额表定位、看序时账、提示类按钮去数据导入、本页格子就地定位', async () => {
    api.fetch.mockResolvedValue(withSources())
    const { w } = await setup()
    const block = w.find('.fs-sources')
    expect(block.exists()).toBe(true)
    expect(block.text()).toContain('科目余额表本期发生额与序时账不一致')
    const links = block.findAll('.fs-sources__link')
    const row = links.find(b => b.text() === '科目余额表 5801 以前年度损益调整')!
    await row.trigger('click')
    expect(api.goSegment).toHaveBeenLastCalledWith('ledger-query', { tab: 'balance', locate: '5801' })
    await links.find(b => b.text() === '看序时账')!.trigger('click')
    expect(api.goSegment).toHaveBeenLastCalledWith('ledger-query', { tab: 'journal', account: '5801' })
    // 「其余差额未能定位」没有可去的页
    expect(block.text()).toContain('其余差额未能定位到具体数据行')
    expect(links.some(b => b.text().startsWith('去'))).toBe(false)
    // 本页格子：不跳页，切到续表并高亮该行
    await links.find(b => b.text() === '本页「负债合计」')!.trigger('click')
    await flushPromises()
    expect(api.goSegment).toHaveBeenCalledTimes(2)
    expect(activeTab(w)).toBe('资产负债表（续）')
    expect(w.find('tr[data-fs-row="35"]').classes()).toContain('fs-located-row')
    // 提示类问题的页级源头
    await w.findAll('.citar-errors .citar-btn').find(b => b.text() === '导入 2024 年账套')!.trigger('click')
    expect(api.goSegment).toHaveBeenLastCalledWith('ledger-import', {})
    w.unmount()
  })

  it('不平校验：切到资产负债表并高亮资产总计期末格，再点轮换到续表', async () => {
    const { w, scroll } = await setup()
    w.findAll('.aud-tab')[2].trigger('click')
    await flushPromises()
    const issue = w.findAll('.fs-issue').find(b => b.text().startsWith('期末资产总计'))!
    await issue.trigger('click')
    await flushPromises()
    expect(activeTab(w)).toBe('资产负债表')
    const tr = w.find('tr[data-fs-row="47"]')
    expect(tr.classes()).toContain('fs-located-row')
    const cells = tr.findAll('td')
    expect(cells[1].classes()).toContain('fs-located-cell')
    expect(cells[2].classes()).not.toContain('fs-located-cell')
    expect(w.find('tr[data-fs-row="7"]').classes()).not.toContain('fs-located-row')
    expect(scroll).toHaveBeenCalled()
    expect(scroll.mock.contexts.at(-1)).toBe(tr.element)

    await issue.trigger('click')
    await flushPromises()
    expect(activeTab(w)).toBe('资产负债表（续）')
    expect(w.find('tr[data-fs-row="46"]').classes()).toContain('fs-located-row')

    // 直接点位置按钮
    const links = w.findAll('.fs-issue__link')
    expect(links.map(l => l.text())).toEqual(['资产负债表「资产总计」期末余额', '资产负债表（续）「负债和所有者权益总计」期末余额'])
    await links[0].trigger('click')
    await flushPromises()
    expect(activeTab(w)).toBe('资产负债表')
    w.unmount()
  })

  it('整列提示：切到利润表并高亮上期金额列；隐藏页签上的提示不可点', async () => {
    const { w } = await setup()
    const issue = w.findAll('.fs-issue').find(b => b.text() === PRIOR_NOTICE)!
    await issue.trigger('click')
    await flushPromises()
    expect(activeTab(w)).toBe('利润表')
    const heads = w.findAll('thead th')
    expect(heads[2].classes()).toContain('fs-located-col')
    expect(heads[1].classes()).not.toContain('fs-located-col')
    for (const tr of w.findAll('tbody tr')) {
      expect(tr.findAll('td')[2].classes()).toContain('fs-located-cell')
      expect(tr.classes()).not.toContain('fs-located-row')
    }
    expect(w.findAll('.fs-issue').some(b => b.text().startsWith('现金流量表'))).toBe(false)
    expect(w.text()).toContain(CF_NOTICE)
    w.unmount()
  })

  it('刷新后去掉定位高亮', async () => {
    const { w } = await setup()
    await w.findAll('.fs-issue').find(b => b.text() === PRIOR_NOTICE)!.trigger('click')
    await flushPromises()
    expect(w.findAll('.fs-located-cell').length).toBeGreaterThan(0)
    await w.findAll('.citar-btn').find(b => b.text() === '刷新')!.trigger('click')
    await flushPromises()
    expect(api.fetch).toHaveBeenCalledTimes(2)
    expect(w.findAll('.fs-located-cell').length).toBe(0)
    expect(w.find('.fs-issue--active').exists()).toBe(false)
    w.unmount()
  })
})
