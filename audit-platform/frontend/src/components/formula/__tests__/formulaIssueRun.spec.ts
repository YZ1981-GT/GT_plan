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
    expect(a.issues[0]).toEqual(BODY.issue_list[0])
    const b = issueHintFromRun({ ...BODY, results: [{ formula_id: 'f9', description: 'x', expression: 'e' }],
      hints: ['  ', '毛利率异常', { hint_text: '存货周转放缓' }, 3] })
    expect(b.outcomes[0].passed).toBe(false)
    expect(b.hints).toEqual(['毛利率异常', '存货周转放缓'])
  })

  it('无结果 / 空响应都不是「执行过」', () => {
    expect(issueHintFromRun({ ...BODY, results: [], issue_list: [], no_result: true }).executed).toBe(false)
    expect(issueHintFromRun({ ...BODY, no_result: true }).executed).toBe(false)
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
