/**
 * 合并试算平衡表页（spec consol-elimination-single-source-push 任务 11.2 / 需求 4）
 *
 * - 只读 report-trial 的五列净额，合并审定数用后端值（不在前端按「借减贷」重算）；
 * - 无公式行不显示 0；取不到数的列显示「留空」带原因；
 * - 穿透：抵销 / 调整 / 合并审定数 → 分录明细（node_key 同所选节点）；审定汇总 → 各数据节点；
 * - 汇总节点下拉来自企业树的汇总节点；切换后按该节点重读；
 * - 「重新推送」调推送接口；子企业数据变化时显示过期提示；
 * - 审核按行恒等式逐行核对（精确到分）；不调任何写库的旧接口。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, h } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'

const { api, message } = vi.hoisted(() => ({
  api: {
    getConsolReportTrial: vi.fn(),
    getConsolPushStatus: vi.fn(),
    pushConsolidation: vi.fn(),
    drillConsolRowEntries: vi.fn(),
    drillConsolRowIndividual: vi.fn(),
  } as Record<string, ReturnType<typeof vi.fn>>,
  message: { success: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))
vi.mock('@/services/consolidationApi', () => Object.fromEntries(
  Object.keys(api).map((k) => [k, (...a: any[]) => api[k](...a)]),
))
vi.mock('element-plus', () => ({ ElMessage: message }))
vi.mock('@/composables/useExcelIO', () => ({ exportMultiSheetData: vi.fn() }))

import ConsolTrialBalanceTab from '../ConsolTrialBalanceTab.vue'
import { sumAmounts, trialAuditResults, trialExportAoa, TRIAL_MEASURES } from '../composables/consolTrialView'
import type { ConsolReportTrialRow, ConsolTreeNode } from '@/services/consolidationApi'

function row(code: string, extra: Partial<ConsolReportTrialRow> = {}): ConsolReportTrialRow {
  return {
    row_code: code, row_name: `行${code}`, row_number: 1, indent_level: 0, is_total_row: false, has_formula: true,
    individual: '100.00', elim_equity: '0.00', elim_trade: '-30.00', adjustment: '5.00', consolidated: '75.00',
    linear: true, note: null, ...extra,
  }
}
const ROWS = [
  row('BS-000', { row_name: '流动资产：', has_formula: false, individual: '0.00', elim_trade: '0.00', adjustment: '0.00', consolidated: '0.00' }),
  row('BS-002'),
  row('BS-010', { elim_trade: null, adjustment: null, consolidated: null, note: '公式引用了年初余额，合并口径没有该列' }),
]
function trialResponse(nodeKey = 'G:consol', label = '某集团（合并）') {
  return {
    year: 2025, applicable_standard: 'soe_consolidated', node_key: nodeKey, node_label: label,
    report_type: 'balance_sheet', columns: TRIAL_MEASURES, rows: ROWS,
  }
}
function node(key: string, kind: ConsolTreeNode['kind'], children: ConsolTreeNode[] = []): ConsolTreeNode {
  const [code, role] = key.split(':') as [string, ConsolTreeNode['role']]
  return {
    project_id: null, company_code: code, company_name: code, parent_company_code: null, ultimate_company_code: null,
    consol_level: 1, children, node_key: key, role, kind, display_name: `${code}（${role}）`, relation: null,
    host_project_id: null, flags: [], via: [], mode: null,
  }
}
const TREE = node('G:consol', 'aggregate', [
  node('G:consol_elim', 'elim'), node('G:parent', 'data'),
  node('A:consol', 'aggregate', [node('A:consol_elim', 'elim'), node('A:parent', 'data')]),
])

const Table = defineComponent({
  props: ['data'],
  provide() { return { rows: () => (this as any).data || [] } },
  setup(_, { slots, attrs }) { return () => h('div', { 'data-testid': (attrs as any)['data-testid'] }, slots.default?.()) },
})
const Column = defineComponent({
  inject: ['rows'],
  props: ['label'],
  setup(props, { slots }) {
    return function (this: any) {
      return h('div', { 'data-label': props.label }, this.rows().map((r: any) => h('div', slots.default?.({ row: r }))))
    }
  },
})
const Btn = defineComponent({
  emits: ['click'],
  setup(_, { slots, emit, attrs }) {
    return () => h('button', { 'data-testid': (attrs as any)['data-testid'], onClick: () => emit('click') }, slots.default?.())
  },
})
const Amount = defineComponent({
  props: ['value', 'clickable'],
  emits: ['click'],
  setup(p, { emit }) { return () => h('span', { class: 'amt', onClick: () => emit('click') }, String(p.value ?? '')) },
})
const Pass = defineComponent({
  setup(_, { slots, attrs }) { return () => h('div', { 'data-testid': (attrs as any)['data-testid'] }, [slots.default?.(), slots.title?.()]) },
})
const Select = defineComponent({
  props: ['modelValue'],
  emits: ['update:modelValue', 'change'],
  setup(_, { slots, attrs }) { return () => h('div', { 'data-testid': (attrs as any)['data-testid'] }, slots.default?.()) },
})
const Option = defineComponent({
  props: ['label', 'value'],
  setup(p) { return () => h('i', { 'data-value': p.value }, p.label) },
})
const STUBS = {
  'el-table': Table, 'el-table-column': Column, 'el-button': Btn, 'el-select': Select, 'el-option': Option,
  'el-alert': Pass, 'el-tooltip': Pass, 'el-empty': true,
  'el-dialog': defineComponent({
    props: ['modelValue'],
    setup(p, { slots, attrs }) { return () => (p.modelValue ? h('div', { 'data-testid': (attrs as any)['data-testid'] }, slots.default?.()) : null) },
  }),
  GtAmountCell: Amount,
}

function mountTab(props: Record<string, unknown> = {}) {
  return mount(ConsolTrialBalanceTab, {
    props: { projectId: 'p-g', year: 2025, tree: TREE, ...props },
    global: { stubs: STUBS, directives: { loading: {} } },
  })
}

describe('consolTrialView 纯逻辑', () => {
  it('审核：线性行逐行核对恒等式，精确到分；取不到数的行列原因；非线性行只计数', () => {
    const results = trialAuditResults([
      row('A'), row('B', { consolidated: '75.01' }), row('C', { linear: false }),
      row('D', { consolidated: null, note: '取不到' }), row('E', { has_formula: false }),
    ], '某集团 · 资产负债表')
    expect(results[0]).toMatchObject({ level: 'error', actual: '2 行', difference: '1 行不等' })
    expect(results[0].message).toContain('1 行公式非线性')
    expect(results.find((r) => r.rule_name === '恒等式 - 行B')).toMatchObject({
      level: 'error', expected: '75.01', actual: '75', difference: '-0.01',
    })
    expect(results.find((r) => r.rule_name === '取数 - 行D')).toMatchObject({ level: 'warn', message: '取不到' })
    expect(trialAuditResults([row('A')], 't')[0].level).toBe('pass')
  })

  it('合计按 Decimal（0.1 + 0.2 = 0.3），导出给数字、无公式行留空', () => {
    expect(sumAmounts(['0.1', '0.2', null])).toBe('0.3')
    const aoa = trialExportAoa(ROWS, TRIAL_MEASURES)
    expect(aoa[0]).toEqual(['行次', '项目', '审定汇总', '权益抵销', '往来交易抵销', '报表调整', '合并审定数', '说明'])
    expect(aoa[1].slice(2, 7)).toEqual([null, null, null, null, null])
    expect(aoa[2].slice(2, 7)).toEqual([100, 0, -30, 5, 75])
  })
})

describe('ConsolTrialBalanceTab', () => {
  beforeEach(() => {
    Object.values(api).forEach((f) => f.mockReset())
    Object.values(message).forEach((f) => f.mockClear())
    api.getConsolReportTrial.mockImplementation((_pid: string, opts: any) =>
      Promise.resolve(opts.nodeKey === 'A:consol' ? trialResponse('A:consol', 'A（合并）') : trialResponse()))
    api.getConsolPushStatus.mockResolvedValue({ last_run: null, is_stale: false, stale_rows: 0 })
    api.pushConsolidation.mockResolvedValue({ queued: true, message: '已开始推送，完成后自动刷新' })
  })

  async function loaded(props: Record<string, unknown> = {}) {
    const wrapper = mountTab(props)
    ;(wrapper.vm as any).load()
    await flushPromises()
    return wrapper
  }

  it('读 report-trial：五列用后端净额（合并审定数不在前端重算）；无公式行不显示 0；取不到数显示留空', async () => {
    const wrapper = await loaded()
    // 请求另带 AbortSignal（切换节点时取消上一请求），这里只核对业务参数
    expect(api.getConsolReportTrial).toHaveBeenCalledWith('p-g', expect.objectContaining({ reportType: 'balance_sheet', nodeKey: null, year: 2025 }))
    expect(wrapper.find('[data-testid="ctb-cell-BS-002-consolidated"]').text()).toBe('75.00')
    expect(wrapper.find('[data-testid="ctb-cell-BS-002-elim_trade"]').text()).toBe('-30.00')
    expect(wrapper.find('[data-testid="ctb-cell-BS-000-consolidated"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="ctb-blank-BS-010-consolidated"]').text()).toBe('留空')
    expect(wrapper.find('[data-testid="ctb-cell-BS-010-individual"]').text()).toBe('100.00')
    expect(api.getConsolPushStatus).toHaveBeenCalledWith('p-g', 2025)
    expect(wrapper.find('[data-testid="ctb-push-status"]').text()).toContain('尚未推送过')
  })

  it('节点下拉 = 企业树全部节点（按层级缩进、显示名称）；选下级节点后按该节点重读、回写左树，穿透也带该节点', async () => {
    const wrapper = await loaded()
    const options = wrapper.findAll('[data-testid="ctb-node"] i').map((o) => o.attributes('data-value'))
    // spec consol-autotree-linkage-closure R10.2：不再只列汇总节点（差额户 / 数据节点也能看）
    expect(options).toEqual(['G:consol', 'G:consol_elim', 'G:parent', 'A:consol', 'A:consol_elim', 'A:parent'])
    expect(wrapper.findAll('[data-testid="ctb-node"] i').map((o) => o.text())).not.toContain('G:consol')
    ;(wrapper.vm as any).$.setupState.nodeKey = 'A:consol'
    wrapper.findComponent(Select).vm.$emit('change', 'A:consol')
    await flushPromises()
    expect(api.getConsolReportTrial).toHaveBeenLastCalledWith('p-g', expect.objectContaining({ reportType: 'balance_sheet', nodeKey: 'A:consol', year: 2025 }))
    expect(wrapper.emitted('node-change')).toEqual([['A:consol']])
    api.drillConsolRowEntries.mockResolvedValue({ decomposable: true, total: '-30.00', note: null, lines: [] })
    await wrapper.find('[data-testid="ctb-cell-BS-002-elim_trade"] .amt').trigger('click')
    await flushPromises()
    expect(api.drillConsolRowEntries).toHaveBeenCalledWith('p-g', {
      rowCode: 'BS-002', measure: 'elim_trade', nodeKey: 'A:consol', year: 2025,
    })
  })

  it('穿透：抵销列 → 分录明细与合计；审定汇总 → 各数据节点个别数', async () => {
    const wrapper = await loaded()
    api.drillConsolRowEntries.mockResolvedValue({
      decomposable: true, total: '-30.00', note: null,
      lines: [{ entry_id: 'e', entry_no: 'IA-001', entry_type: 'internal_ar_ap', node_key: 'G:consol_elim', node_label: '合并差额', account_code: '1122', account_name: '应收账款', debit: '0.00', credit: '30.00', contribution: '-30.00' }],
    })
    await wrapper.find('[data-testid="ctb-cell-BS-002-elim_trade"] .amt').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ctb-drill-entries"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ctb-drill-total"]').text()).toContain('-30.00')

    api.drillConsolRowIndividual.mockResolvedValue({ year: 2025, row_code: 'BS-002', rows: [
      { node_key: 'G:parent', node_label: '母公司', project_id: 'p', amount: '60.00', reason: null },
      { node_key: 'A:parent', node_label: 'A', project_id: 'p2', amount: '40.00', reason: null },
    ] })
    await wrapper.find('[data-testid="ctb-cell-BS-002-individual"] .amt').trigger('click')
    await flushPromises()
    // 首次读取后下拉回填为后端给出的根合并节点
    expect(api.drillConsolRowIndividual).toHaveBeenCalledWith('p-g', { rowCode: 'BS-002', nodeKey: 'G:consol', year: 2025 })
    expect(wrapper.find('[data-testid="ctb-drill-individual"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ctb-drill-total"]').text()).toContain('100')
  })

  it('重新推送调推送接口（手动）；子企业数据变化 ⇒ 显示过期提示', async () => {
    api.getConsolPushStatus.mockResolvedValue({
      last_run: { id: 'r', project_id: 'p-g', year: 2025, trigger_source: 'elimination_approved', trigger_label: '分录审批', triggered_by: null, status: 'succeeded', steps: [], warnings: [], started_at: '2026-10-01T01:00:00Z', finished_at: '2026-10-01T01:00:05Z' },
      is_stale: true, stale_rows: 3,
    })
    const wrapper = await loaded()
    expect(wrapper.find('[data-testid="ctb-stale"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="ctb-push-status"]').text()).toContain('分录审批，成功')
    await wrapper.find('[data-testid="ctb-push"]').trigger('click')
    await flushPromises()
    expect(api.pushConsolidation).toHaveBeenCalledWith('p-g', 2025, 'manual')
    expect(message.success).toHaveBeenCalledWith('已开始推送，完成后自动刷新')
  })

  it('审核：交给父组件显示的是行恒等式核对结果', async () => {
    const wrapper = await loaded()
    await wrapper.find('[data-testid="ctb-audit"]').trigger('click')
    const [results] = wrapper.emitted('audit')![0] as any[]
    expect(results[0].rule_name).toContain('行恒等式校验')
    expect(results[0].level).toBe('pass')
    expect(results.some((r: any) => r.rule_name === '取数 - 行BS-010')).toBe(true)
  })

  it('未打开过本页不读；年度变化后（已打开过）按新年度重读并回到根节点', async () => {
    const wrapper = mountTab()
    await flushPromises()
    expect(api.getConsolReportTrial).not.toHaveBeenCalled()
    await wrapper.setProps({ year: 2024 })
    await flushPromises()
    expect(api.getConsolReportTrial).not.toHaveBeenCalled()
    ;(wrapper.vm as any).load()
    await flushPromises()
    await wrapper.setProps({ year: 2025 })
    await flushPromises()
    expect(api.getConsolReportTrial).toHaveBeenLastCalledWith('p-g', expect.objectContaining({ reportType: 'balance_sheet', nodeKey: null, year: 2025 }))
  })
})

// ─── spec consol-autotree-linkage-closure R5.1 / R8.5 / R10 ─────────────────────────

const DRAFT_COLUMNS = [...TRIAL_MEASURES, { key: 'consolidated_with_drafts' as const, label: '含草稿预览' }]

describe('ConsolTrialBalanceTab：含草稿预览、口径说明、平衡提示、穿透补全', () => {
  beforeEach(() => {
    Object.values(api).forEach((f) => f.mockReset())
    api.getConsolPushStatus.mockResolvedValue({ last_run: null, is_stale: false, stale_rows: 0 })
  })

  async function loadedWith(res: Record<string, unknown>) {
    api.getConsolReportTrial.mockResolvedValue({ ...trialResponse(), ...res })
    const wrapper = mountTab()
    ;(wrapper.vm as any).load()
    await flushPromises()
    return wrapper
  }

  it('含草稿预览与合并审定数不同的格高亮并说明来自未审批分录；相同的格不高亮、不可穿透', async () => {
    const wrapper = await loadedWith({
      columns: DRAFT_COLUMNS, draft_pending_entries: 2,
      rows: [row('BS-002', { consolidated_with_drafts: '62.00' }), row('BS-006', { consolidated_with_drafts: '75.00' })],
    })
    const diff = wrapper.find('[data-testid="ctb-cell-BS-002-consolidated_with_drafts"]')
    expect(diff.classes()).toContain('gt-ctb-draft--diff')
    expect(diff.text()).toBe('62.00')
    const same = wrapper.find('[data-testid="ctb-cell-BS-006-consolidated_with_drafts"]')
    expect(same.classes()).not.toContain('gt-ctb-draft--diff')
    expect(wrapper.find('[data-testid="ctb-draft-note"]').text()).toContain('2 笔未审批分录')
    await same.find('.amt').trigger('click')
    await flushPromises()
    expect(api.drillConsolRowEntries).not.toHaveBeenCalled()
  })

  it('列口径按节点类型说明（汇总 / 差额户 / 单体数据）；借贷不平给出两边合计与差额', async () => {
    const agg = await loadedWith({ node_kind: 'aggregate', balance: { debit_total: '10.00', credit_total: '10.00', difference: '0.00', balanced: true } })
    expect(agg.find('[data-testid="ctb-basis-note"]').text()).toContain('合并审定数 = 审定汇总')
    expect(agg.find('[data-testid="ctb-balanced"]').exists()).toBe(true)
    expect(agg.find('[data-testid="ctb-unbalanced"]').exists()).toBe(false)
    const elim = await loadedWith({ node_kind: 'elim' })
    expect(elim.find('[data-testid="ctb-basis-note"]').text()).toContain('差额户')
    const data = await loadedWith({
      node_kind: 'data', balance: { debit_total: '100.00', credit_total: '60.00', difference: '40.00', balanced: false },
    })
    expect(data.find('[data-testid="ctb-basis-note"]').text()).toContain('单体数据')
    expect(data.find('[data-testid="ctb-unbalanced"]').text()).toContain('借方性质合计 100.00，贷方性质合计 60.00，相差 40.00')
  })

  it('穿透：分录带类型与说明，合并审定数给完整构成；个别数带所属上级、可进入项目，0 与空分开显示', async () => {
    const wrapper = await loadedWith({})
    api.drillConsolRowEntries.mockResolvedValue({
      decomposable: true, total: '-30.00', note: null, individual_total: '100.00', consolidated_total: '70.00',
      lines: [{ entry_id: 'e', entry_no: 'IA-001', entry_type: 'internal_ar_ap', entry_type_label: '内部往来抵销', description: '期末往来',
        node_key: 'G:consol_elim', node_label: '某集团（差额户）', account_code: '1122', account_name: '应收账款', debit: '0.00', credit: '30.00', contribution: '-30.00' }],
    })
    await wrapper.find('[data-testid="ctb-cell-BS-002-consolidated"] .amt').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ctb-drill-type"]').text()).toBe('内部往来抵销')
    expect(wrapper.find('[data-testid="ctb-drill-desc"]').text()).toBe('期末往来')
    expect(wrapper.find('[data-testid="ctb-drill-composition"]').text()).toMatch(/合并审定数 70\.00 = 审定汇总 100\.00\s*\+ 已审批分录 -30\.00/)

    api.drillConsolRowIndividual.mockResolvedValue({ year: 2025, row_code: 'BS-002', rows: [
      { node_key: 'G:parent', node_label: '某集团（单体母公司户）', parent_label: '某集团（合并户）', project_id: 'p-gs', amount: '0.00', reason: null },
      { node_key: 'B:subsidiary', node_label: '乙公司', parent_label: '某集团（合并户）', project_id: null, amount: null, reason: '未建单户项目' },
    ] })
    await wrapper.find('[data-testid="ctb-cell-BS-002-individual"] .amt').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="ctb-drill-parent"]').text()).toBe('某集团（合并户）')
    expect(wrapper.find('[data-testid="ctb-drill-amount-G:parent"]').text()).toBe('0.00')
    expect(wrapper.find('[data-testid="ctb-drill-amount-B:subsidiary"]').text()).toBe('空')
    expect(wrapper.find('[data-testid="ctb-drill-enter-B:subsidiary"]').exists()).toBe(false)
    await wrapper.find('[data-testid="ctb-drill-enter-G:parent"]').trigger('click')
    expect(wrapper.emitted('enter-project')).toEqual([[{ projectId: 'p-gs', label: '某集团（单体母公司户）' }]])
  })
})
