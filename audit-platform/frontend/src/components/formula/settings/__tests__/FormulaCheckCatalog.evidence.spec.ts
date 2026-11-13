/** R3：能力、来源历史与逐条规则结论必须分开；所有夹具均为隔离的合成数据。 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElTable, ElTableColumn } from 'element-plus'
import type { CheckCatalogQuery, CheckRuleSource } from '@/composables/formula/useFormulaSettings'

const mocked = vi.hoisted(() => ({ checkRules: vi.fn() }))
vi.mock('@/services/formulaSettingsApi', () => ({ formulaSettingsApi: mocked }))
import FormulaCheckCatalog from '../FormulaCheckCatalog.vue'

enableAutoUnmount(afterEach)
let entries: CheckRuleSource[] = []
function source(patch: Partial<CheckRuleSource> = {}): CheckRuleSource {
  return { key: 'report_builtin', label: '合成报表规则', category: '报表', runs_in: '校验入口', editable: false,
    edit_where: '', files: [], from_db: false, rule_count: 1, error: null, execution: 'wired', executor: 'module.check',
    result_table: 'cross_check_results', last_run: { at: null, status: 'never_run', counts: {}, year: 2025 },
    last_run_note: '未找到此范围的运行记录，不代表校验通过', matched: 1,
    rules: [{ id: '合成规则-1', label: '合成金额勾稽', expression: '1 = 1', severity: 'logic_check', severity_label: '勾稽', scope: '报表' }],
    ...patch }
}
beforeEach(() => {
  entries = []
  mocked.checkRules.mockReset().mockImplementation(async (params: CheckCatalogQuery = {}) => ({
    sources: params.source ? entries.filter((s) => s.key === params.source) : entries,
    total: entries.length,
  }))
})
async function show(sources: CheckRuleSource[], props: { projectId?: string; year?: number } = { projectId: 'p1', year: 2025 }) {
  entries = sources
  const w = mount(FormulaCheckCatalog, { props, global: { plugins: [ElementPlus] } })
  await flushPromises()
  return w
}

describe('规则能力不等于项目执行', () => {
  it.each([
    ['wired', '入口可调用'], ['display_only', '仅展示'], ['not_executable', '无可用执行器'], [undefined, '能力未提供'],
  ] as const)('能力 %s 单独展示，不当作历史通过', async (execution, label) => {
    const w = await show([source({ execution })])
    expect(w.get('[data-testid="fcc-capability-report_builtin"]').text()).toContain(label)
    expect(w.get('[data-testid="fcc-capability-report_builtin"]').text()).toContain('入口能力不代表项目已执行或通过')
    expect(w.get('[data-testid="fcc-history-report_builtin"]').text()).toContain('未找到运行记录（所查范围内）')
    expect(w.text()).not.toContain('历史摘要通过')
  })
})

describe('来源历史的缺失与失败不伪装成通过', () => {
  it('无项目不显示服务器返回的旧项目摘要、计数、年度、时间或范围说明', async () => {
    const w = await show([source({
      last_run: { at: '2023-04-01T02:03:04+00:00', status: 'passed', counts: { pass: 3 }, year: 2023 },
      last_run_note: '旧项目的历史范围说明',
    })], {})
    const history = w.get('[data-testid="fcc-history-report_builtin"]')
    expect(history.text()).toContain('未指定项目，未查询执行结果')
    for (const stale of ['历史摘要通过', '通过：3', '结果年度：', '摘要最新记录时间：', '旧项目的历史范围说明']) {
      expect(history.text()).not.toContain(stale)
    }
  })

  it.each([
    [{ result_table: null, last_run: null, last_run_note: '本类结果不落库' }, '本类结果不落库'],
    [{ last_run: null, last_run_note: '' }, '未取得项目历史，不能据此认定通过'],
    [{ last_run: { at: null, status: 'unavailable', counts: {} } }, '读取失败，未取得可用结论'],
    [{ last_run: { at: null, status: 'never_run', counts: {}, year: 2025 } }, '未找到运行记录（所查范围内）'],
    [{ last_run: { at: null, status: 'unknown', counts: { alien: 1 } } }, '存在未识别状态，不能认定通过'],
    [{ last_run: { at: null, status: 'alien', counts: { alien: 1 } } }, '未识别的历史状态，不能认定通过'],
  ] satisfies Array<[Partial<CheckRuleSource>, string]>)('状态 %j 如实呈现', async (patch, label) => {
    const w = await show([source(patch)])
    const text = w.get('[data-testid="fcc-history-report_builtin"]').text()
    expect(text).toContain(label)
    expect(text).not.toContain('历史摘要通过')
    if (patch.last_run?.counts.alien) expect(text).toContain('未识别状态（alien）：1')
  })

  it.each([
    ['failed', '历史摘要未通过'], ['error', '历史执行出错'], ['not_executed', '含未执行项'],
    ['not_applicable', '不适用'], ['skip', '含未执行项'],
  ])('状态 %s 不降级为通过', async (status, label) => {
    const w = await show([source({ last_run: { at: null, status, counts: { [status]: 1 } } })])
    expect(w.get('[data-testid="fcc-history-report_builtin"]').text()).toContain(label)
    expect(w.text()).not.toContain('历史摘要通过')
  })
})

describe('历史范围与逐行规则不混用', () => {
  it('搜索按来源分别展示能力与历史，不把某来源摘要嫁接成逐行执行结论', async () => {
    const w = await show([
      source({ label: '合成报表来源', last_run: { at: null, status: 'passed', counts: { pass: 2 }, year: 2025 },
        last_run_note: '报表逐规则最新，可能来自多次运行' }),
      source({ key: 'qc_rules', label: '合成质控来源', result_table: 'wp_qc_results', execution: 'display_only',
        last_run: { at: null, status: 'failed', counts: { working_papers: 1, blocking: 1 } },
        last_run_note: '逐底稿汇总，不按年度过滤，不能作为所选年度的执行证据',
        rules: [{ id: '合成质控-1', label: '合成质控规则', expression: '', severity: 'logic_check', severity_label: '勾稽', scope: '质控' }] }),
      source({ key: 'cross_check_preset', label: '未命中来源', result_table: null, last_run: null, matched: 0, rules: [] }),
    ])
    await w.get('input[data-testid="fcc-search"]').setValue('合成')
    await w.get('[data-testid="fcc-search-btn"]').trigger('click')
    await flushPromises()
    expect(mocked.checkRules).toHaveBeenLastCalledWith({ project_id: 'p1', year: 2025, q: '合成' })
    expect(w.findAll('[data-testid^="fcc-evidence-"]')).toHaveLength(2)
    const report = w.get('[data-testid="fcc-evidence-report_builtin"]')
    const qc = w.get('[data-testid="fcc-evidence-qc_rules"]')
    expect(report.text()).toContain('合成报表来源（来源摘要）')
    expect(report.get('[data-testid="fcc-capability-report_builtin"]').text()).toContain('入口可调用')
    expect(report.get('[data-testid="fcc-history-report_builtin"]').text()).toContain('历史摘要通过')
    expect(report.text()).not.toContain('底稿数：')
    expect(qc.text()).toContain('合成质控来源（来源摘要）')
    expect(qc.get('[data-testid="fcc-capability-qc_rules"]').text()).toContain('仅展示')
    expect(qc.get('[data-testid="fcc-history-qc_rules"]').text()).toContain('历史摘要未通过')
    expect(qc.text()).toContain('底稿数：1')
    expect(qc.text()).toContain('不按年度过滤，不能作为所选年度的执行证据')
    expect(qc.text()).not.toContain('历史摘要通过')
    expect(qc.text()).not.toContain('结果年度：')
    expect(w.find('[data-testid="fcc-evidence-cross_check_preset"]').exists()).toBe(false)
    const table = w.findComponent(ElTable)
    const rows = table.props('data') as Array<Record<string, unknown>>
    expect(rows.map((r) => r._source)).toEqual(['合成报表来源', '合成质控来源'])
    for (const row of rows) {
      expect(row).not.toHaveProperty('status')
      expect(row).not.toHaveProperty('last_run')
    }
    const columns = table.findAllComponents(ElTableColumn).map((c) => c.props('label'))
    expect(columns).toContain('来源')
    expect(columns).not.toContain('执行结果')
    expect(w.get('[data-testid="fcc-rules"]').text()).not.toContain('历史摘要通过')
  })

  it.each(['2025-04-01T02:03:04+00:00', '2025-04-01T02:03:04'])('cross-check 摘要标明年度、时间及多次运行聚合 %s', async (at) => {
    const note = '仅取 2025 年度内逐规则最新结果，可能来自多次运行，并非单次运行快照；不是目录每条规则的执行结论'
    const w = await show([source({ last_run: { at, status: 'passed', counts: { pass: 2 }, year: 2025 }, last_run_note: note })])
    const history = w.get('[data-testid="fcc-history-report_builtin"]').text()
    expect(history).toContain('结果年度：2025')
    expect(history).toContain('摘要最新记录时间：')
    expect(history).toContain('通过：2')
    expect(history).toContain(note)
    expect(history).not.toContain('Invalid Date')
    expect(history).not.toContain('NaN')
    const table = w.findComponent(ElTable)
    const rows = table.props('data') as Array<Record<string, unknown>>
    expect(rows).toHaveLength(1)
    expect(rows[0]).not.toHaveProperty('last_run')
    expect(rows[0]).not.toHaveProperty('status')
    expect(table.findAllComponents(ElTableColumn).map((c) => c.props('label'))).not.toContain('执行结果')
    expect(w.get('[data-testid="fcc-rules"]').text()).not.toContain('历史摘要通过')
  })

  it('QC 明确逐底稿聚合且非年度证据；所选年度不伪造成结果年度', async () => {
    const note = '项目各底稿最新自检结果汇总，并非单次运行快照；不按年度过滤，不能作为所选年度的执行证据'
    const w = await show([source({ key: 'qc_rules', result_table: 'wp_qc_results',
      last_run: { at: null, status: 'failed', counts: { working_papers: 2, blocking: 1 } }, last_run_note: note })])
    const history = w.get('[data-testid="fcc-history-qc_rules"]').text()
    expect(history).toContain(note)
    expect(history).toContain('底稿数：2')
    expect(history).toContain('阻断项：1')
    expect(history).not.toContain('结果年度：')
    expect(w.get('[data-testid="fcc-context"]').text()).toContain('所选年度：2025')
  })

  it.each([['allow', '门禁放行'], ['warn', '门禁警告'], ['block', '门禁阻断']])('Gate %s 仅为签字门禁，不充当 JSON 执行证据', async (status, label) => {
    const note = '项目最近一次签字门禁记录；不按年度过滤，不能作为所选年度的执行证据；门禁记录不代表循环 JSON 规则执行'
    const w = await show([source({ key: 'cycle_validation', execution: 'not_executable', executor: null,
      result_table: 'gate_decisions', last_run: { at: null, status, counts: { hit_rules: 1 } }, last_run_note: note })])
    expect(w.get('[data-testid="fcc-capability-cycle_validation"]').text()).toContain('无可用执行器')
    const history = w.get('[data-testid="fcc-history-cycle_validation"]').text()
    expect(history).toContain(`${label}（非规则执行结论）`)
    expect(history).toContain(note)
    expect(history).not.toContain('历史摘要通过')
    expect(history).not.toContain('结果年度：')
  })
})
