/**
 * 内置报表勾稽的问题清单 / 提醒接入表间审核面板（spec formula-governance-coverage-closure R4.1 / R4.2）。
 *
 * - formulaIssueHint：接口响应 → 面板形状（兼容信封）；按树节点裁剪。
 * - FormulaCrossCheckPanel 真挂载 GtFormulaIssuePanel：执行过才画问题清单（没跑不显示「全部通过」）、
 *   失败给原因 + 重试、提醒非空才显示、与内置勾稽无关的节点不显示。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import FormulaCrossCheckPanel from '../FormulaCrossCheckPanel.vue'
import GtFormulaIssuePanel from '../GtFormulaIssuePanel.vue'
import {
  emptyIssueRun, failedIssueRun, issueHintFromRun, issueRunForNode, type FormulaIssueRun,
} from '../formulaIssueHint'

const BODY = {
  issue_list: [{ formula_id: 'f1', addr_id: 'report:BS/A', description: '资产 ≠ 负债 + 权益', left_value: '100.5', right_value: '90' }],
  results: [
    { formula_id: 'f1', description: '资产 ≠ 负债 + 权益', expression: "ROW('a') = ROW('b')", passed: false },
    { formula_id: 'f2', description: '净利润一致', expression: "ROW('c') = ROW('d')", passed: true },
  ],
  hints: [],
  last_computed_at: '2026-10-22T08:00:00',
  run_id: 'r1', status: 'executed', no_result: false,
}

describe('issueHintFromRun', () => {
  it('已解包与未解包信封同一结果；缺 passed 按不通过、提醒只收非空文案', () => {
    const a = issueHintFromRun(BODY)
    expect(issueHintFromRun({ code: 200, message: 'ok', data: BODY })).toEqual(a)
    expect(a.executed).toBe(true)
    expect(a.issues[0]).toMatchObject({ ...BODY.issue_list[0], severity: 'warning' })
    const b = issueHintFromRun({ ...BODY, results: [{ formula_id: 'f9', description: 'x', expression: 'e' }],
      hints: ['  ', '毛利率异常', { hint_text: '存货周转放缓' }, 3] })
    expect(b.outcomes[0].passed).toBe(false)
    expect(b.hints).toEqual(['毛利率异常', '存货周转放缓'])
  })

  it('逐条保留五态、中文标签和严重程度，金额仍为字符串且保留真零', () => {
    const statuses = ['passed', 'failed', 'not_executed', 'not_applicable', 'error'] as const
    const severities = ['blocking', 'warning', 'info'] as const
    const run = issueHintFromRun({
      ...BODY,
      issue_list: [{ formula_id: '缺数', description: '缺少期初数', left_value: 0, right_value: null,
        status: 'not_executed', label: '尚未取数', severity: 'info' }],
      results: statuses.map((status, i) => ({ formula_id: status, description: status,
        expression: '', passed: status === 'passed', status, label: `标签${i}`, severity: severities[i % 3] })),
    })
    expect(run.issues[0]).toMatchObject({ left_value: '0', right_value: null,
      status: 'not_executed', label: '尚未取数', severity: 'info' })
    expect(run.outcomes.map((o) => o.status)).toEqual(statuses)
    expect(run.outcomes.map((o) => o.label)).toEqual(statuses.map((_, i) => `标签${i}`))
    expect(run.outcomes.map((o) => o.severity)).toEqual(statuses.map((_, i) => severities[i % 3]))
  })

  it('显式未知或空状态是异常，不被旧 passed 布尔值蒙绿；严重度默认警告', () => {
    const run = issueHintFromRun({ ...BODY,
      issue_list: [{ ...BODY.issue_list[0], status: 'passed', label: 1, severity: 'fatal' }],
      results: [
        { ...BODY.results[1], status: 'unknown', label: false, severity: 'fatal' },
        { ...BODY.results[1], status: null },
        { ...BODY.results[1] },
        { ...BODY.results[0] },
        { ...BODY.results[1], status: 'not_executed', reason: '缺少来源' },
      ],
    })
    expect(run.issues[0]).toMatchObject({ status: 'passed', severity: 'warning' })
    expect(run.issues[0].label).toBeUndefined()
    expect(run.outcomes.map((o) => o.status)).toEqual(['error', 'error', 'passed', 'failed', 'not_executed'])
    expect(run.outcomes.map((o) => o.passed)).toEqual([false, false, true, false, false])
    expect(run.outcomes[0].label).toBeUndefined()
    expect(run.outcomes[0].severity).toBe('warning')
    expect(run.outcomes[4].reason).toBe('缺少来源')
  })

  it('结果金额保留真实零和显式空，拒绝半合法数字、布尔值与无穷值', () => {
    const values = [0, '0', null, '', '12oops', Infinity, true, ' 12.5 ']
    const run = issueHintFromRun({ results: values.map((v, i) => ({
      formula_id: String(i), passed: true, left_value: v, right_value: v, diff: v,
    })) })
    const expected = [0, 0, null, null, null, null, null, 12.5]
    for (const field of ['left_value', 'right_value', 'diff'] as const) {
      expect(run.outcomes.map((o) => o[field])).toEqual(expected)
    }
    const absent = issueHintFromRun({ results: [{ formula_id: 'absent', passed: true }] }).outcomes[0]
    expect(absent).not.toHaveProperty('left_value')
    expect(absent).not.toHaveProperty('diff')
  })

  it('无结果 / 空响应都不是「执行过」，并清空旧问题与结论', () => {
    for (const signal of [{ no_result: true }, { status: 'no_result' }]) {
      const stale = issueHintFromRun({ ...BODY, ...signal, hints: ['独立提醒仍保留'] })
      expect(stale.executed).toBe(false)
      expect(stale.issues).toEqual([])
      expect(stale.outcomes).toEqual([])
      expect(stale.hints).toEqual(['独立提醒仍保留'])
    }
    expect(issueHintFromRun({ ...BODY, results: [], issue_list: [], no_result: true }).executed).toBe(false)
    expect(issueHintFromRun(null).executed).toBe(false)
    expect(issueHintFromRun(undefined)).toEqual(emptyIssueRun())
  })
})

describe('issueRunForNode', () => {
  const run = issueHintFromRun(BODY)
  it('「报表 ↔ 附注」看全部；单条勾稽节点只看自己；其余节点（含不可选中的根节点）不显示', () => {
    expect(issueRunForNode(run, 'cross_report_note')).toBe(run)
    expect(issueRunForNode(run, 'cross_check')).toBeNull()
    const f2 = issueRunForNode(run, 'cross_exec_f2')!
    expect(f2.outcomes.map((o) => o.formula_id)).toEqual(['f2'])
    expect(f2.issues).toEqual([])
    expect(f2.executed).toBe(true)
    expect(issueRunForNode(run, 'cross_exec_f1')!.issues).toHaveLength(1)
    // 树上不存在的勾稽：没有结论可看，不能显示成「全部通过」
    expect(issueRunForNode(run, 'cross_exec_nope')!.executed).toBe(false)
    for (const k of ['cross_report_wp', 'cross_note_wp', 'cross_consol', 'report_bs']) {
      expect(issueRunForNode(run, k)).toBeNull()
    }
  })
})

describe('表间审核面板：内置勾稽问题清单', () => {
  const props = (issueRun: FormulaIssueRun | null, extra: Record<string, unknown> = {}) => ({
    selectedPath: '表间审核', rules: [], execEmpty: false, running: false, showDialog: false, dialogTitle: '',
    form: { label: '', left_ref: '', operator: '=', right_ref: '', description: '' }, projectId: 'p1', year: 2025,
    layerTagType: () => 'info', layerLabel: () => '', issueRun, ...extra,
  })
  const mountPanel = (issueRun: FormulaIssueRun | null, extra: Record<string, unknown> = {}) =>
    mount(FormulaCrossCheckPanel, {
      props: props(issueRun, extra),
      global: { plugins: [ElementPlus], stubs: { CrossCheckHistoryPanel: true } },
    })

  it('执行过：真挂载问题清单，显示不通过项的左右值与差异、全部校验条数', () => {
    const w = mountPanel(issueHintFromRun(BODY))
    const panel = w.findComponent(GtFormulaIssuePanel)
    expect(panel.exists()).toBe(true)
    const text = panel.text()
    for (const s of ['逻辑判断问题清单', '1 项待处理', '资产 ≠ 负债 + 权益', '100.50', '90.00', '10.50',
      '来源：report:BS/A', '查看全部校验（2 条）']) {
      expect(text, s).toContain(s)
    }
    expect(w.find('[data-testid="cc-issue-hints"]').exists()).toBe(false)
  })

  it('问题清单「刷新」与失败「重试」都发 refresh-exec', async () => {
    const w = mountPanel(issueHintFromRun(BODY))
    await w.findComponent(GtFormulaIssuePanel).vm.$emit('refresh')
    expect(w.emitted('refresh-exec')).toHaveLength(1)
    const f = mountPanel(failedIssueRun('没有权限执行此操作'))
    expect(f.findComponent(GtFormulaIssuePanel).exists()).toBe(false)
    expect(f.text()).toContain('内置报表勾稽执行失败')
    expect(f.text()).toContain('没有权限执行此操作')
    await f.find('[data-testid="cc-issue-retry"]').trigger('click')
    expect(f.emitted('refresh-exec')).toHaveLength(1)
  })

  it('没跑出结论：不画问题清单（不冒充「全部通过」），给无结果说明与重新执行', async () => {
    const w = mountPanel(issueHintFromRun({ ...BODY, results: [], issue_list: [], no_result: true }), { execEmpty: true })
    expect(w.findComponent(GtFormulaIssuePanel).exists()).toBe(false)
    expect(w.text()).not.toContain('全部通过')
    expect(w.text()).toContain('内置报表勾稽无结果')
    // 节点级「无结果」提示不再重复出现
    expect(w.text()).not.toContain('且该节点尚无自定义规则')
    await w.find('[data-testid="cc-issue-rerun"]').trigger('click')
    expect(w.emitted('refresh-exec')).toHaveLength(1)
  })

  it('提醒非空才显示；与内置勾稽无关的节点整块不显示', () => {
    const w = mountPanel(issueHintFromRun({ ...BODY, hints: ['毛利率较上年变动超过 30%'] }))
    expect(w.find('[data-testid="cc-issue-hints"]').text()).toContain('毛利率较上年变动超过 30%')
    const none = mountPanel(null, { execEmpty: true })
    expect(none.find('[data-testid="cc-issue-run"]').exists()).toBe(false)
    expect(none.text()).toContain('且该节点尚无自定义规则')
  })
})
describe('S2 共享问题面板五态兼容', () => {
  const mountIssuePanel = (outcomes: FormulaIssueRun['outcomes']) => mount(GtFormulaIssuePanel, {
    props: { issues: [], outcomes, showRefresh: false },
    global: { plugins: [ElementPlus], stubs: {
      ElCollapse: { template: '<div><slot /></div>' },
      ElCollapseItem: { template: '<div><slot /></div>' },
    } },
  })
  it.each([
    ['passed', '通过', 'success'], ['failed', '失败', 'warning'],
    ['not_executed', '未执行（数据缺失）', 'warning'],
    ['not_applicable', '不适用', 'info'], ['error', '检查异常', 'danger'],
  ] as const)('%s 使用独立标签与颜色，不按 passed 布尔值误判', (status, label, type) => {
    const w = mountIssuePanel([{ formula_id: 's2', description: '校对', expression: '',
      passed: status !== 'passed', status }])
    const tag = w.find('.gt-outcome-item .el-tag')
    expect(tag.text()).toBe(label); expect(tag.classes()).toContain(`el-tag--${type}`)
    if (status !== 'passed') expect(w.text()).not.toContain('全部通过')
    w.unmount()
  })
  it('空结果和全部不适用不显示全部通过，旧 passed 接口仍能显示通过', () => {
    const empty = mountIssuePanel([])
    expect(empty.text()).toContain('无校验结果'); expect(empty.text()).not.toContain('全部通过'); empty.unmount()
    const na = mountIssuePanel([{ formula_id: 'na', description: '无适用表格', expression: '',
      passed: false, status: 'not_applicable' }])
    expect(na.text()).toContain('本次检查不适用'); expect(na.text()).not.toContain('全部通过'); na.unmount()
    const legacy = mountIssuePanel([{ formula_id: 'old', description: '旧结果', expression: '', passed: true }])
    expect(legacy.text()).toContain('全部通过')
    expect(legacy.find('.gt-outcome-item .el-tag').text()).toBe('通过'); legacy.unmount()
  })
})

describe('S2 严重级别不冒充执行状态', () => {
  it.each([
    ['blocking', '阻断', 'danger'], ['warning', '警告', 'warning'], ['info', '提示', 'info'],
  ] as const)('%s 的失败项保留未通过并独立展示严重级别', (severity, label, type) => {
    const w = mount(GtFormulaIssuePanel, {
      props: { issues: [{ ...BODY.issue_list[0], status: 'failed', severity }], showRefresh: false },
      global: { plugins: [ElementPlus] },
    })
    const item = w.find('.gt-issue-item')
    expect(item.classes()).toContain(`gt-issue-item--${severity}`)
    expect(item.text()).toContain('失败'); expect(item.text()).toContain(label)
    expect(item.findAll('.el-tag').every(tag => tag.classes().includes(`el-tag--${type}`))).toBe(true)
    expect(w.text()).not.toContain('全部通过'); w.unmount()
  })
})
