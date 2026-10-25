/**
 * useCrossCheckRules —— 表间审核规则 composable（spec formula-global-settings-sync S2）
 *
 * 守护：persist 后调 askApplyScope（changed_slot_keys）、applyRulesData 保留 layer/pending、
 * onAdd/onSave/onRemove 经 persist、执行结果解析。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useCrossCheckRules, type CrossCheckDeps } from '../useCrossCheckRules'

const KEYS = {
  report_note: 'cross_report_note',
  report_wp: 'cross_report_wp',
  note_wp: 'cross_note_wp',
  consol: 'cross_consol',
} as any

function makeDeps(overrides: Partial<CrossCheckDeps> = {}): CrossCheckDeps {
  return {
    projectId: ref('p1'),
    year: ref(2025 as number | string | undefined),
    selectedNodeKey: ref('cross_report_note'),
    currentProjectCacheKey: ref('p1:v1:2025'),
    cacheKeyMatches: (a, b) => a === b,
    shouldApplyResponse: () => true,
    api: { get: vi.fn().mockResolvedValue({}), put: vi.fn().mockResolvedValue({}), post: vi.fn().mockResolvedValue({}) },
    projectFormula: {
      reportCrossCheck: (pid: string) => `/api/projects/${pid}/formula/report-cross-check`,
      crossCheckRules: (pid: string) => `/api/projects/${pid}/formula/cross-check-rules`,
    },
    P_rc: { executeFormulasBatch: '/api/report-config/execute-formulas-batch' },
    guardFormulaMutation: vi.fn(() => true),
    showFormulaError: vi.fn(),
    askApplyScope: vi.fn(),
    CROSS_CHECK_NODE_KEYS: KEYS,
    ...overrides,
  }
}

describe('applyRulesData', () => {
  it('保留后端下发的 layer 和 pending', () => {
    const deps = makeDeps()
    const cc = useCrossCheckRules(deps)
    cc.applyRulesData({
      rules: { cross_report_note: [{ rule_id: 'r1', label: '规则A', left_ref: '1', operator: '=', right_ref: '2', layer: 'global', pending: true }] },
      loaded: { 'cross_report_note#r1': 'G1' },
    })
    const rule = cc.rulesMap.value.cross_report_note[0]
    expect(rule.layer).toBe('global')
    expect(rule.pending).toBe(true)
    expect(cc.tokens.value).toEqual({ 'cross_report_note#r1': 'G1' })
  })
})

describe('persist', () => {
  it('成功后调 askApplyScope 传 changed_slot_keys', async () => {
    const deps = makeDeps()
    deps.api.put.mockResolvedValue({ rules: {}, loaded: {}, changed_slot_keys: ['cross_report_note#r1'] })
    const cc = useCrossCheckRules(deps)
    await cc.persist()
    expect(deps.askApplyScope).toHaveBeenCalledWith('cross_check', ['cross_report_note#r1'])
  })

  it('guardFormulaMutation 拒绝时不发请求', async () => {
    const deps = makeDeps({ guardFormulaMutation: vi.fn(() => false) as any })
    const cc = useCrossCheckRules(deps)
    await cc.persist()
    expect(deps.api.put).not.toHaveBeenCalled()
  })
})

describe('CRUD delegates to persist', () => {
  let deps: CrossCheckDeps
  let cc: ReturnType<typeof useCrossCheckRules>

  beforeEach(() => {
    deps = makeDeps()
    deps.api.put.mockResolvedValue({ rules: {}, loaded: {} })
    cc = useCrossCheckRules(deps)
  })

  it('onAdd → onSave 新增规则并落库', () => {
    cc.onAdd()
    expect(cc.showDialog.value).toBe(true)
    cc.form.value = { label: '新规则', left_ref: '1', operator: '=', right_ref: '2', description: '' }
    cc.onSave()
    expect(cc.showDialog.value).toBe(false)
    expect(cc.rulesForCurrent.value.some(r => r.label === '新规则')).toBe(true)
    expect(deps.api.put).toHaveBeenCalled()
  })

  it('onRemove 删除规则并落库', () => {
    cc.rulesMap.value.cross_report_note = [{ label: 'A' }, { label: 'B' }]
    cc.onRemove(0)
    expect(cc.rulesMap.value.cross_report_note.map(r => r.label)).toEqual(['B'])
    expect(deps.api.put).toHaveBeenCalled()
  })
})

describe('resetCache', () => {
  it('清空执行结果缓存', () => {
    const cc = useCrossCheckRules(makeDeps())
    cc.execLoaded.value = true
    cc.execRun.value = { ...cc.execRun.value, executed: true }
    cc.resetCache()
    expect(cc.execLoaded.value).toBe(false)
    expect(cc.execEmpty.value).toBe(false)
    expect(cc.execRun.value.executed).toBe(false)
  })
})

// spec formula-governance-coverage-closure R4：问题清单 / 提醒取自打开时那一次勾稽响应
describe('内置勾稽：同一次响应供树与问题清单', () => {
  const RUN = {
    issue_list: [{ formula_id: 'report-cross-check-1', addr_id: null, description: '资产 ≠ 负债 + 权益',
      left_value: '100.00', right_value: '90.00' }],
    results: [
      { formula_id: 'report-cross-check-1', description: '资产 ≠ 负债 + 权益', expression: "ROW('a') = ROW('b')", passed: false },
      { formula_id: 'report-cross-check-2', description: '净利润一致', expression: "ROW('c') = ROW('d')", passed: true },
    ],
    hints: ['毛利率较上年变动超过 30%'],
    last_computed_at: '2026-10-22T08:00:00',
    run_id: 'run-1', status: 'executed', no_result: false,
  }
  const crossCheckCalls = (deps: CrossCheckDeps) =>
    (deps.api.get as any).mock.calls.filter((c: any[]) => String(c[0]).endsWith('/report-cross-check'))
  const ruleCalls = (deps: CrossCheckDeps) =>
    (deps.api.get as any).mock.calls.filter((c: any[]) => String(c[0]).endsWith('/cross-check-rules'))

  function depsWith(run: unknown) {
    const deps = makeDeps()
    ;(deps.api.get as any).mockImplementation(async (url: string) => (url.endsWith('/report-cross-check') ? run : { rules: {} }))
    return deps
  }

  it('一次请求：树节点 ✅/❌ 与问题清单 / 提醒 / 计算时间同源，不再另调一次', async () => {
    const deps = depsWith(RUN)
    const cc = useCrossCheckRules(deps)
    await cc.loadExecItems()
    expect(crossCheckCalls(deps)).toHaveLength(1)
    // 失败如实上报：不再用 validateStatus 把 4xx / 5xx 吞成「无结果」
    expect(crossCheckCalls(deps)[0][1]).toMatchObject({ params: { year: 2025 }, _silent: true })
    expect(crossCheckCalls(deps)[0][1].validateStatus).toBeUndefined()
    expect(cc.execItems.value.report_note.map((n: any) => [n.key, n.icon])).toEqual([
      ['cross_exec_report-cross-check-1', '❌'], ['cross_exec_report-cross-check-2', '✅'],
    ])
    const run = cc.execRun.value
    expect(run.executed).toBe(true)
    expect(run.failed).toBe(false)
    expect(run.issues).toEqual(RUN.issue_list)
    expect(run.outcomes.map((o) => [o.formula_id, o.passed])).toEqual([
      ['report-cross-check-1', false], ['report-cross-check-2', true],
    ])
    expect(run.hints).toEqual(['毛利率较上年变动超过 30%'])
    expect(run.lastComputedAt).toBe('2026-10-22T08:00:00')
    expect(run.runId).toBe('run-1')
    expect(cc.execEmpty.value).toBe(false)
    expect(cc.execLoading.value).toBe(false)
    // 已缓存：再调 loadExecItems 不重复执行（该接口每调一次落一次运行记录）
    await cc.loadExecItems()
    expect(crossCheckCalls(deps)).toHaveLength(1)
  })

  it('请求失败：记为失败并带原因，不显示成「无结果」，也不冒充通过', async () => {
    const deps = makeDeps()
    ;(deps.api.get as any).mockImplementation(async (url: string) => {
      if (url.endsWith('/report-cross-check')) throw { response: { status: 403, data: { detail: '无权查看该项目' } } }
      return { rules: {} }
    })
    const cc = useCrossCheckRules(deps)
    await cc.loadExecItems()
    expect(cc.execRun.value.failed).toBe(true)
    expect(cc.execRun.value.executed).toBe(false)
    expect(cc.execRun.value.error).toBe('无权查看该项目')
    expect(cc.execEmpty.value).toBe(false)
    expect(cc.execItems.value.report_note).toEqual([])
    expect(cc.execLoaded.value).toBe(true)
    expect(ruleCalls(deps)).toHaveLength(1)
  })

  it('本年度无报表数据（no_result）：未执行、记为无结果', async () => {
    const deps = depsWith({ issue_list: [], results: [], hints: [], last_computed_at: null, status: 'no_result', no_result: true })
    const cc = useCrossCheckRules(deps)
    await cc.loadExecItems()
    expect(cc.execRun.value.executed).toBe(false)
    expect(cc.execRun.value.failed).toBe(false)
    expect(cc.execEmpty.value).toBe(true)
  })

  it('刷新：强制重新执行一次，只刷新勾稽结论，不重载用户规则（免得冲掉规则的执行结果）', async () => {
    const deps = depsWith(RUN)
    const cc = useCrossCheckRules(deps)
    await cc.loadExecItems()
    cc.rulesMap.value.cross_report_note = [{ label: 'R', _checked: true, _pass: true }]
    ;(deps.api.get as any).mockImplementation(async (url: string) =>
      (url.endsWith('/report-cross-check') ? { ...RUN, issue_list: [], results: [{ ...RUN.results[0], passed: true }] } : { rules: {} }))
    await cc.refreshExec()
    expect(crossCheckCalls(deps)).toHaveLength(2)
    expect(ruleCalls(deps)).toHaveLength(1)
    expect(cc.execRun.value.issues).toEqual([])
    expect(cc.execItems.value.report_note[0].icon).toBe('✅')
    expect(cc.rulesMap.value.cross_report_note[0]._checked).toBe(true)
  })

  it('换了项目：加载期间先清掉上一个项目的问题清单', async () => {
    const deps = depsWith(RUN)
    const cc = useCrossCheckRules(deps)
    await cc.loadExecItems()
    expect(cc.execRun.value.issues).toHaveLength(1)
    let release!: (v: unknown) => void
    ;(deps.api.get as any).mockImplementation((url: string) =>
      (url.endsWith('/report-cross-check') ? new Promise((r) => { release = r }) : Promise.resolve({ rules: {} })))
    deps.projectId.value = 'p2'
    deps.currentProjectCacheKey.value = 'p2:v1:2025'
    const pending = cc.loadExecItems()
    expect(cc.execLoading.value).toBe(true)
    expect(cc.execRun.value.issues).toEqual([])
    expect(cc.execRun.value.executed).toBe(false)
    release(RUN)
    await pending
    expect(cc.execLoading.value).toBe(false)
    expect(cc.execRun.value.executed).toBe(true)
  })
})

// spec formula-fetch-followup-defect-closure 7.2：原先规则表初值是一组写死的「示例规则」，读接口返回空集时不覆盖 ⇒
// 冒充本项目规则显示，首次保存任何规则时被整组写库；示例里 NOTE 第一参写标题（应为章节编号）、CONSOL 不可执行。
describe('不拿写死的示例冒充本项目规则', () => {
  it('初始没有任何规则；读接口返回空集后仍为空（面板显示「尚无自定义规则」）', async () => {
    const deps = makeDeps()
    deps.api.get.mockImplementation(async (url: string) =>
      String(url).includes('cross-check-rules') ? { rules: {}, loaded: {} } : { results: [] })
    const cc = useCrossCheckRules(deps)
    expect(cc.rulesMap.value).toEqual({})
    await cc.loadExecItems()
    expect(deps.api.get.mock.calls.map((c: any[]) => String(c[0]))).toContain('/api/projects/p1/formula/cross-check-rules')
    expect(cc.rulesMap.value).toEqual({})
  })

  it('首次保存只写用户自己加的规则', () => {
    const deps = makeDeps()
    deps.api.put.mockResolvedValue({ rules: {}, loaded: {} })
    const cc = useCrossCheckRules(deps)
    cc.onAdd()
    cc.form.value = { label: '我的规则', left_ref: "REPORT('BS-002','期末')", operator: '=',
                      right_ref: "NOTE('五、1','合计','期末')", description: '' }
    cc.onSave()
    const payload = deps.api.put.mock.calls[0][1].rules
    expect(Object.values(payload).flat().map((r: any) => r.label)).toEqual(['我的规则'])
  })

  it('读 / 存的响应是本项目全部规则：响应里没有的节点清空', () => {
    const cc = useCrossCheckRules(makeDeps())
    cc.rulesMap.value = { cross_report_wp: [{ label: '旧' }] }
    cc.applyRulesData({ rules: { cross_report_note: [{ rule_id: 'r1', label: 'A' }] }, loaded: {} })
    expect(Object.keys(cc.rulesMap.value)).toEqual(['cross_report_note'])
  })
})
