/**
 * useCrossCheckRules —— 表间审核规则 composable（spec formula-global-settings-sync S2）
 *
 * 守护：persist 后调 askApplyScope（changed_slot_keys）、applyRulesData 保留 layer/pending、
 * onAdd/onSave/onRemove 经 persist、执行结果解析。
 */
import { afterEach, describe, it, expect, vi, beforeEach } from 'vitest'
import { effectScope, ref } from 'vue'
import { flushPromises } from '@vue/test-utils'
import { useCrossCheckRules, type CrossCheckDeps } from '../useCrossCheckRules'

const scopes: ReturnType<typeof effectScope>[] = []
afterEach(() => { for (const scope of scopes.splice(0)) scope.stop() })
function createScoped(deps: CrossCheckDeps) {
  const scope = effectScope(); scopes.push(scope)
  return scope.run(() => useCrossCheckRules(deps))!
}

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
    const cc = createScoped(deps)
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
    const cc = createScoped(deps)
    await cc.persist()
    expect(deps.askApplyScope).toHaveBeenCalledWith('cross_check', ['cross_report_note#r1'])
  })

  it('guardFormulaMutation 拒绝时不发请求', async () => {
    const deps = makeDeps({ guardFormulaMutation: vi.fn(() => false) as any })
    const cc = createScoped(deps)
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
    cc = createScoped(deps)
  })

  it('onAdd → onSave 新增规则并落库', () => {
    cc.onAdd()
    expect(cc.showDialog.value).toBe(true)
    cc.form.value = { ...cc.form.value, label: '新规则', left_ref: '1', operator: '=', right_ref: '2', description: '' }
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
    const cc = createScoped(makeDeps())
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
    const cc = createScoped(deps)
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
    expect(run.issues).toHaveLength(RUN.issue_list.length)
    expect(run.issues[0]).toMatchObject({ ...RUN.issue_list[0], severity: 'warning' })
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
    const cc = createScoped(deps)
    await cc.loadExecItems()
    expect(cc.execRun.value.failed).toBe(true)
    expect(cc.execRun.value.executed).toBe(false)
    expect(cc.execRun.value.error).toBe('无权查看该项目')
    expect(cc.execEmpty.value).toBe(false)
    expect(cc.execItems.value.report_note).toEqual([])
    expect(cc.execLoaded.value).toBe(false)
    expect(ruleCalls(deps)).toHaveLength(1)
  })

  it('本年度无报表数据（no_result）：未执行、记为无结果', async () => {
    const deps = depsWith({ issue_list: [], results: [], hints: [], last_computed_at: null, status: 'no_result', no_result: true })
    const cc = createScoped(deps)
    await cc.loadExecItems()
    expect(cc.execRun.value.executed).toBe(false)
    expect(cc.execRun.value.failed).toBe(false)
    expect(cc.execEmpty.value).toBe(true)
  })

  it('刷新：强制重新执行一次，只刷新勾稽结论，不重载用户规则（免得冲掉规则的执行结果）', async () => {
    const deps = depsWith(RUN)
    const cc = createScoped(deps)
    await cc.loadExecItems()
    cc.rulesMap.value.cross_report_note = [{ label: 'R', left_ref: 'L', operator: '=', right_ref: 'R', _checked: true, _pass: true }]
    const originalRule = cc.rulesMap.value.cross_report_note[0]
    ;(deps.api.get as any).mockImplementation(async (url: string) =>
      (url.endsWith('/report-cross-check') ? { ...RUN, issue_list: [], results: [
        { ...RUN.results[0], passed: true },
        { formula_id: 'user:r', expression: 'L = R', status: 'failed', reason: '刷新后实际不平' },
      ] } : { rules: {} }))
    await cc.refreshExec()
    expect(crossCheckCalls(deps)).toHaveLength(2)
    expect(ruleCalls(deps)).toHaveLength(1)
    expect(cc.execRun.value.issues).toEqual([])
    expect(cc.execItems.value.report_note[0].icon).toBe('✅')
    expect(cc.rulesMap.value.cross_report_note[0]).toBe(originalRule)
    expect(originalRule).toMatchObject({ label: 'R', _checked: true, _pass: false, _status: 'failed', _reason: '刷新后实际不平' })
  })

  it('换了项目：加载期间先清掉上一个项目的问题清单', async () => {
    const deps = depsWith(RUN)
    const cc = createScoped(deps)
    await cc.loadExecItems()
    expect(cc.execRun.value.issues).toHaveLength(1)
    let release!: (v: unknown) => void
    ;(deps.api.get as any).mockImplementation((url: string) =>
      (url.endsWith('/report-cross-check') ? new Promise((r) => { release = r }) : Promise.resolve({ rules: {} })))
    deps.projectId.value = 'p2'
    deps.currentProjectCacheKey.value = 'p2:v1:2025'
    const pending = cc.loadExecItems()
    await flushPromises()
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
    const cc = createScoped(deps)
    expect(cc.rulesMap.value).toEqual({})
    await cc.loadExecItems()
    expect(deps.api.get.mock.calls.map((c: any[]) => String(c[0]))).toContain('/api/projects/p1/formula/cross-check-rules')
    expect(cc.rulesMap.value).toEqual({})
  })

  it('首次保存只写用户自己加的规则', () => {
    const deps = makeDeps()
    deps.api.put.mockResolvedValue({ rules: {}, loaded: {} })
    const cc = createScoped(deps)
    cc.onAdd()
    cc.form.value = { ...cc.form.value, label: '我的规则', left_ref: "REPORT('BS-002','期末')", operator: '=',
                      right_ref: "NOTE('五、1','合计','期末')", description: '' }
    cc.onSave()
    const payload = deps.api.put.mock.calls[0][1].rules
    expect(Object.values(payload).flat().map((r: any) => r.label)).toEqual(['我的规则'])
  })

  it('读 / 存的响应是本项目全部规则：响应里没有的节点清空', () => {
    const cc = createScoped(makeDeps())
    cc.rulesMap.value = { cross_report_wp: [{ label: '旧' }] }
    cc.applyRulesData({ rules: { cross_report_note: [{ rule_id: 'r1', label: 'A' }] }, loaded: {} })
    expect(Object.keys(cc.rulesMap.value)).toEqual(['cross_report_note'])
  })
})


describe('run — 请求失败如实可见（formula-writer-ownership-and-stale R4）', () => {
  it('实际 GET 执行端点非 2xx 时保留原因、可重试，不把空 results 冒充成功', async () => {
    const deps = makeDeps()
    const error = { response: { status: 500, data: { detail: '执行失败' } } }
    deps.api.get.mockRejectedValue(error)
    const cc = createScoped(deps)
    cc.rulesMap.value.cross_report_note = [{ label: '规则', left_ref: '1', operator: '=', right_ref: '2' }]

    expect(await cc.run()).toEqual({ passCount: 0, failCount: 0 })

    expect(cc.execRun.value).toMatchObject({ failed: true, executed: false, error: '执行失败' })
    expect(cc.execLoaded.value).toBe(false)
    expect(cc.execEmpty.value).toBe(false)
    expect(cc.running.value).toBe(false)
    expect(deps.api.get).toHaveBeenCalledWith(
      '/api/projects/p1/formula/report-cross-check', { params: { year: 2025 }, _silent: true },
    )
    expect(deps.api.get.mock.calls[0][1].validateStatus).toBeUndefined()
    expect(deps.api.post).not.toHaveBeenCalled()
    expect(cc.rulesMap.value.cross_report_note[0]).toMatchObject({ _checked: false, _pass: false, _status: 'error', _reason: '执行失败' })
  })

  it.each([
    { name: '403 无字符串原因', error: { response: { status: 403, data: {} } }, expected: '没有权限执行此操作' },
    { name: '500 空原因', error: { response: { status: 500, data: { detail: '' } } }, expected: '报表勾稽执行失败' },
    { name: '无网络状态', error: new Error('传输失败'), expected: '报表勾稽执行失败：网络不通，请检查连接' },
    { name: '结构化原因', error: { response: { status: 500, data: { detail: { message: '数据尚未就绪' } } } }, expected: '报表勾稽执行失败：数据尚未就绪' },
    { name: '422 逐条引用', error: { response: { status: 422, data: { detail: {
      error_code: 'FORMULA_DANGLING_REFS', message: '公式引用无效', issues: [{ ref: 'ROW(缺失行)', message: '该行不存在' }],
    } } } }, expected: '报表勾稽执行失败：公式引用无效：ROW(缺失行)：该行不存在' },
    { name: '另一信封的字符串原因', error: { status: 500, data: { detail: '执行器暂不可用' } }, expected: '执行器暂不可用' },
  ])('$name 仍保留统一错误兜底，不把对象转成文本', async ({ error, expected }) => {
    const deps = makeDeps()
    deps.api.get.mockRejectedValue(error)
    const cc = createScoped(deps)
    cc.rulesMap.value.cross_report_note = [{ label: '规则', left_ref: '1', operator: '=', right_ref: '2' }]
    await cc.run()
    expect(cc.execRun.value).toMatchObject({ failed: true, executed: false, error: expected })
    expect(cc.rulesMap.value.cross_report_note[0]).toMatchObject({ _status: 'error', _reason: expected })
    expect(cc.execRun.value.error).not.toContain('[object Object]')
    expect(cc.execLoaded.value).toBe(false)
    expect(cc.execEmpty.value).toBe(false)
  })
})

// 候选 R3：保留以上主树回归，追加 CAS、保存/执行屏障与上下文隔离。
const rule = (extra: Record<string, unknown> = {}) => ({ rule_id: 'r1', label: '规则', left_ref: 'L', operator: '=', right_ref: 'R', tolerance: '0.25', severity: 'info', ...extra })
const run = (results: any[] = []) => ({ status: 'executed', run_id: 'run-1', results, issue_list: [], hints: [], no_result: false })
function deferred<T = any>() { let resolve!: (v: T) => void; let reject!: (e: any) => void; const promise = new Promise<T>((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
function setup() {
  const deps = makeDeps({ currentProjectCacheKey: ref('p1:2025') })
  deps.api.get.mockResolvedValue(run()); deps.api.put.mockResolvedValue({ rules: {}, loaded: {} })
  const scope = effectScope(); scopes.push(scope)
  const cc = scope.run(() => useCrossCheckRules(deps))!
  return { deps, cc, scope }
}
function itemWithoutUi(r: any) { const { layer, pending, ...persisted } = r; return persisted }

describe('规则读取与保存契约', () => {
  it('初始空集；全量替换保留元数据、容差、严重度与 CAS', async () => {
    const { cc, deps } = setup(); expect(cc.rulesMap.value).toEqual({})
    cc.applyRulesData({ rules: { cross_report_wp: [rule()] } })
    const item = rule({ slot_key: 'slot1', version_token: 'V2', layer: 'global', pending: true })
    cc.applyRulesData({ rules: { cross_report_note: [item] }, loaded: { slot1: 'V2' } })
    expect(Object.keys(cc.rulesMap.value)).toEqual(['cross_report_note'])
    expect(cc.rulesForCurrent.value[0]).toMatchObject(item)
    deps.api.put.mockResolvedValue({ rules: { cross_report_note: [item] }, loaded: { slot1: 'V3' }, changed_slot_keys: ['slot1'] })
    expect(await cc.persist()).toBe(true)
    expect(deps.api.put.mock.calls[0][1]).toMatchObject({ loaded: { slot1: 'V2' }, rules: { cross_report_note: [itemWithoutUi(item)] } })
    expect(cc.tokens.value).toEqual({ slot1: 'V3' }); expect(cc.unsaved.value).toBe(false)
    expect(deps.askApplyScope).toHaveBeenCalledWith('cross_check', ['slot1'])
  })
  it('权限拒绝不保存；新增只写实际规则；删除走同一保存接口', async () => {
    const { cc, deps } = setup(); deps.guardFormulaMutation = vi.fn(() => false)
    expect(await cc.persist()).toBe(false); expect(deps.api.put).not.toHaveBeenCalled()
    deps.guardFormulaMutation = () => true; cc.onAdd(); cc.form.value = { ...cc.form.value, ...rule(), description: '' } as any
    cc.onSave(); expect(deps.api.put.mock.calls[0][1].rules.cross_report_note).toHaveLength(1)
    await flushPromises(); cc.applyRulesData({ rules: { cross_report_note: [rule(), rule({ rule_id: 'r2', label: '第二条' })] } })
    cc.onRemove(0); expect(cc.rulesForCurrent.value.map(r => r.label)).toEqual(['第二条']); await flushPromises()
  })
})

describe('保存时序', () => {
  it('共用同一保存 Promise，保存期间所有 UI 修改被拒绝', async () => {
    const { cc, deps } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule()] } })
    const d = deferred(); deps.api.put.mockReturnValue(d.promise)
    const a = cc.persist(), b = cc.persist(); expect(a).toBe(b); expect(deps.api.put).toHaveBeenCalledTimes(1)
    cc.onAdd(); cc.onEdit(cc.rulesForCurrent.value[0], 0); cc.onSave(); cc.onRemove(0)
    expect(cc.showDialog.value).toBe(false); expect(cc.rulesForCurrent.value).toHaveLength(1)
    expect(deps.showFormulaError).toHaveBeenCalledTimes(4)
    const pendingRun = cc.run(); expect(deps.api.get).not.toHaveBeenCalled()
    d.resolve({ rules: { cross_report_note: [rule()] }, loaded: {} }); await a; await pendingRun
    expect(deps.api.get).toHaveBeenCalledTimes(1); expect(cc.saving.value).toBe(false)
  })
  it('失败保持未保存、阻止执行；显式重试成功后方可执行', async () => {
    const { cc, deps } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule()] } })
    deps.api.put.mockRejectedValueOnce(new Error('CAS 冲突'))
    expect(await cc.persist()).toBe(false); await cc.run()
    expect(cc.unsaved.value).toBe(true); expect(deps.api.get).not.toHaveBeenCalled()
    expect(cc.rulesForCurrent.value[0]).toMatchObject({ _status: 'not_executed', _pass: false, _reason: '规则尚未保存成功，请先重试保存' })
    deps.api.put.mockResolvedValue({ rules: { cross_report_note: [rule()] }, loaded: {} })
    expect(await cc.persist()).toBe(true); await cc.run(); expect(deps.api.get).toHaveBeenCalledTimes(1)
  })
  it('缺失规则集合或保存中 revision 变化显式失败，不猜新 ID 或重发', async () => {
    const { cc, deps } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule()] } })
    deps.api.put.mockResolvedValueOnce({ loaded: {} }); expect(await cc.persist()).toBe(false)
    const d = deferred(); deps.api.put.mockReturnValue(d.promise); const pending = cc.persist()
    cc.applyRulesData({ rules: { cross_report_note: [rule({ label: '较新规则' })] } })
    d.resolve({ rules: { cross_report_note: [rule({ label: '旧保存集合' })] }, loaded: {} })
    expect(await pending).toBe(false); expect(cc.rulesForCurrent.value[0].label).toBe('较新规则')
    expect(deps.api.put).toHaveBeenCalledTimes(2); expect(cc.unsaved.value).toBe(true)
  })
  it('保存使较早读取失效；切项目后旧保存不触发应用范围或清新保存 loading', async () => {
    const { cc, deps } = setup(); const read = deferred(), oldSave = deferred(), newSave = deferred()
    deps.api.get.mockReturnValue(read.promise); const loading = cc.loadUserRules()
    cc.applyRulesData({ rules: { cross_report_note: [rule()] } }); deps.api.put.mockReturnValueOnce(oldSave.promise)
    const first = cc.persist(); read.resolve({ rules: { cross_report_note: [rule({ label: '旧读取' })] } }); await loading
    expect(cc.rulesForCurrent.value[0].label).toBe('规则')
    deps.projectId.value = 'p2'; cc.applyRulesData({ rules: { cross_report_note: [rule({ label: '新项目' })] } })
    deps.api.put.mockReturnValueOnce(newSave.promise); const second = cc.persist()
    oldSave.resolve({ rules: { cross_report_note: [rule({ label: '旧项目保存' })] } }); await first
    expect(cc.saving.value).toBe(true); expect(deps.askApplyScope).not.toHaveBeenCalled()
    newSave.resolve({ rules: { cross_report_note: [rule({ label: '新项目' })] }, loaded: {} }); await second
    expect(cc.rulesForCurrent.value[0].label).toBe('新项目'); expect(cc.saving.value).toBe(false)
  })
})

describe('一次后端结果与规则匹配', () => {
  it('只发 GET；五态与严重度独立，零与显式 NULL 保留', async () => {
    const { cc, deps } = setup(); const states = ['passed', 'failed', 'not_executed', 'not_applicable', 'error']
    cc.applyRulesData({ rules: { cross_report_note: states.map((s, i) => rule({ rule_id: `r${i}`, left_ref: `L${i}`, severity: 'blocking' })) } })
    deps.api.get.mockResolvedValue({ ...run(states.map((status, i) => ({ formula_id: `user:${i}`, expression: `L${i} = R`, status, reason: `原因${i}`, ...(i === 0 ? { left_value: 0, right_value: null, diff: null } : {}), ...(i === 1 ? { severity: 'info' } : {}) }))), issue_list: [{ formula_id: 'user:0', left_value: '99', right_value: '88', severity: 'info' }] })
    expect(await cc.run()).toEqual({ passCount: 1, failCount: 1 })
    expect(deps.api.get).toHaveBeenCalledWith('/api/projects/p1/formula/report-cross-check', { params: { year: 2025 }, _silent: true })
    expect(deps.api.post).not.toHaveBeenCalled(); expect(cc.rulesForCurrent.value.map(r => r._status)).toEqual(states)
    expect(cc.rulesForCurrent.value[0]).toMatchObject({ _leftVal: 0, _rightVal: null, _diff: null, _severity: 'info' })
    expect(cc.rulesForCurrent.value[1]._severity).toBe('info'); expect(cc.rulesForCurrent.value[2]._severity).toBe('blocking')
    expect(cc.execItems.value.report_note.map(r => r.icon)).toEqual(['✅', '❌', '⏸', '➖', '⚠️'])
  })
  it.each(['local', 'backend', 'builtin', 'different'])('%s 歧义或非精确结果不能猜测通过', async kind => {
    const { cc, deps } = setup(); const rows = [rule()]
    if (kind === 'local') rows.push(rule({ rule_id: 'r2' }))
    cc.applyRulesData({ rules: { cross_report_note: rows } })
    const o = { formula_id: kind === 'builtin' ? 'builtin:1' : 'user:1', expression: kind === 'different' ? 'L=R' : 'L = R', passed: true }
    deps.api.get.mockResolvedValue(run(kind === 'backend' ? [o, { ...o, formula_id: 'user:2' }] : [o]))
    await cc.run(); expect(cc.rulesForCurrent.value.every(r => r._status === 'not_executed' && !r._checked && !r._pass)).toBe(true)
  })
  it('no_result 清空旧证据；执行失败可重试且不伪装空结果', async () => {
    const { cc, deps } = setup(); deps.api.get.mockResolvedValueOnce({ rules: { cross_report_note: [rule()] } }).mockRejectedValueOnce(new Error('执行失败'))
    await cc.loadExecItems(); expect(cc.execRun.value.failed).toBe(true); expect(cc.execLoaded.value).toBe(false)
    expect(cc.rulesForCurrent.value[0]._status).toBe('error')
    deps.api.get.mockResolvedValueOnce({ rules: { cross_report_note: [rule()] } }).mockResolvedValueOnce({ ...run([{ formula_id: 'user:1', expression: 'L = R', passed: true }]), no_result: true })
    await cc.loadExecItems(); expect(cc.execEmpty.value).toBe(true); expect(cc.execRun.value.outcomes).toEqual([])
    expect(cc.rulesForCurrent.value[0]._status).toBe('not_executed')
  })
  it.each(['project', 'year', 'node', 'dispose', 'aba'])('%s 变化丢弃旧执行成功结果', async kind => {
    const { cc, deps, scope } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule()] } })
    const old = deferred(); deps.api.get.mockReturnValueOnce(old.promise); const p = cc.run()
    if (kind === 'year') deps.year.value = 2026
    else if (kind === 'node') deps.selectedNodeKey.value = 'cross_report_wp'
    else if (kind === 'dispose') scope.stop()
    else { deps.projectId.value = 'p2'; if (kind === 'aba') deps.projectId.value = 'p1' }
    old.resolve(run([{ formula_id: 'user:1', expression: 'L = R', passed: true }])); await p
    expect(cc.execRun.value.outcomes).toEqual([]); expect(cc.running.value).toBe(false)
  })
})

describe('迟到失败不得污染当前执行', () => {
  it.each(['project', 'year', 'node', 'aba'])('%s 切换后旧 reject/finally 不结束新执行', async kind => {
    const { cc, deps } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule()] } })
    const old = deferred(), latest = deferred()
    deps.api.get.mockReturnValueOnce(old.promise).mockReturnValueOnce(latest.promise)
    const first = cc.run()
    if (kind === 'year') deps.year.value = 2026
    else if (kind === 'node') deps.selectedNodeKey.value = 'cross_report_wp'
    else { deps.projectId.value = 'p2'; if (kind === 'aba') deps.projectId.value = 'p1' }
    const node = deps.selectedNodeKey.value
    cc.applyRulesData({ rules: { [node]: [rule({ label: '当前规则' })] } })
    const second = cc.run(); old.reject(new Error('旧请求错误')); await first
    expect(cc.running.value).toBe(true); expect(cc.execLoading.value).toBe(true)
    expect(cc.execRun.value.failed).toBe(false); expect(deps.showFormulaError).not.toHaveBeenCalled()
    latest.resolve(run([{ formula_id: 'user:new', expression: 'L = R', status: 'passed' }]))
    expect(await second).toEqual({ passCount: 1, failCount: 0 })
    expect(cc.rulesForCurrent.value[0]).toMatchObject({ label: '当前规则', _status: 'passed' })
    expect(cc.running.value).toBe(false); expect(cc.execLoading.value).toBe(false)
  })
  it('卸载后旧执行 reject 不再写错误或恢复结果', async () => {
    const { cc, deps, scope } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule()] } })
    const old = deferred(); deps.api.get.mockReturnValueOnce(old.promise)
    const pending = cc.run(); scope.stop(); old.reject(new Error('已卸载'))
    await expect(pending).resolves.toBeUndefined()
    expect(cc.execRun.value.outcomes).toEqual([]); expect(cc.execRun.value.failed).toBe(false)
    expect(deps.showFormulaError).not.toHaveBeenCalled()
  })
})

describe('保存上下文隔离', () => {
  it.each(['year-resolve', 'year-reject', 'aba-resolve', 'aba-reject'])('%s 旧保存不改新数据或清新 saving', async kind => {
    const { cc, deps } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule()] } })
    const old = deferred(), latest = deferred(); deps.api.put.mockReturnValueOnce(old.promise).mockReturnValueOnce(latest.promise)
    const first = cc.persist()
    if (kind.startsWith('year')) deps.year.value = 2026
    else { deps.projectId.value = 'p2'; deps.projectId.value = 'p1' }
    cc.applyRulesData({ rules: { cross_report_note: [rule({ label: '新上下文' })] } })
    const second = cc.persist()
    if (kind.endsWith('reject')) old.reject(new Error('旧保存失败'))
    else old.resolve({ rules: { cross_report_note: [rule({ label: '旧保存' })] }, changed_slot_keys: ['old'] })
    expect(await first).toBe(false); expect(cc.saving.value).toBe(true); expect(cc.unsaved.value).toBe(true)
    expect(cc.rulesForCurrent.value[0].label).toBe('新上下文')
    expect(deps.showFormulaError).not.toHaveBeenCalled(); expect(deps.askApplyScope).not.toHaveBeenCalled()
    latest.resolve({ rules: { cross_report_note: [rule({ label: '已确认新规则' })] }, loaded: { slot: 'V3' }, changed_slot_keys: ['new'] })
    expect(await second).toBe(true); expect(cc.saving.value).toBe(false)
    expect(cc.rulesForCurrent.value[0].label).toBe('已确认新规则')
    expect(deps.askApplyScope).toHaveBeenCalledExactlyOnceWith('cross_check', ['new'])
  })
  it.each(['resolve', 'reject'])('卸载后保存 %s 无写回和提示副作用', async kind => {
    const { cc, deps, scope } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule()] } })
    const old = deferred(); deps.api.put.mockReturnValueOnce(old.promise)
    const pending = cc.persist(); scope.stop()
    if (kind === 'resolve') old.resolve({ rules: { cross_report_note: [rule()] }, changed_slot_keys: ['old'] })
    else old.reject(new Error('已卸载保存失败'))
    expect(await pending).toBe(false); expect(cc.rulesMap.value).toEqual({}); expect(cc.saving.value).toBe(false)
    expect(deps.showFormulaError).not.toHaveBeenCalled(); expect(deps.askApplyScope).not.toHaveBeenCalled()
  })
})

describe('载入令牌最小防御', () => {
  it.each(['edit', 'delete'])('既有槽 %s 缺载入令牌时在 PUT 前拒绝并保脏', async kind => {
    const { cc, deps } = setup()
    cc.applyRulesData({ rules: { cross_report_note: [rule({ slot_key: 's1', version_token: 'row-token' })] }, loaded: {} })
    if (kind === 'edit') { cc.onEdit(cc.rulesForCurrent.value[0], 0); cc.form.value.label = '已修改'; cc.onSave() }
    else cc.onRemove(0)
    await flushPromises(); expect(deps.api.put).not.toHaveBeenCalled()
    expect(cc.unsaved.value).toBe(true); expect(cc.saving.value).toBe(false)
    expect(vi.mocked(deps.showFormulaError).mock.calls[0][0].message).toContain('缺少载入令牌')
    await cc.refreshExec(); expect(deps.api.get).not.toHaveBeenCalled()
    expect(await cc.persist()).toBe(false); expect(deps.api.put).not.toHaveBeenCalled()
  })
  it('未改既有槽即使 loaded 为空仍可提交合法新增', async () => {
    const { cc, deps } = setup()
    cc.applyRulesData({ rules: { cross_report_note: [rule({ slot_key: 's1' })] }, loaded: {} })
    cc.onAdd(); cc.form.value.label = '新增'; cc.onSave(); await flushPromises()
    expect(deps.api.put).toHaveBeenCalledTimes(1)
    expect(deps.api.put.mock.calls[0][1].rules.cross_report_note).toHaveLength(2)
    expect(cc.unsaved.value).toBe(false)
  })
  it.each(['edit', 'delete'])('预设明确 null 版本允许 %s，不要求行 token 等于槽 token', async kind => {
    const { cc, deps } = setup(), item = rule({ slot_key: 'preset', version_token: 'different', layer: 'preset' })
    cc.applyRulesData({ rules: { cross_report_note: [item] }, loaded: { preset: null } })
    if (kind === 'edit') cc.rulesForCurrent.value[0].label = '改写'
    else cc.rulesMap.value.cross_report_note = []
    deps.api.put.mockResolvedValue({ rules: { cross_report_note: [] }, loaded: { preset: 'new-version', concurrent: null } })
    expect(await cc.persist()).toBe(true)
    expect(deps.api.put.mock.calls[0][1].loaded).toEqual({ preset: null })
    expect(cc.tokens.value).toEqual({ preset: 'new-version', concurrent: null })
  })
  it('合法并发新增由服务端回传，不要求新行预先持有令牌', async () => {
    const { cc, deps } = setup()
    cc.applyRulesData({ rules: { cross_report_note: [rule({ slot_key: 's1' })] }, loaded: { s1: 'v1' } })
    cc.rulesForCurrent.value[0].label = '修改'
    deps.api.put.mockResolvedValue({ data: { rules: { cross_report_note: [rule({ slot_key: 's1' }), rule({ rule_id: 'r2', slot_key: 's2' })] }, loaded: { s1: 'v2', s2: 'v1' } } })
    expect(await cc.persist()).toBe(true); expect(cc.rulesForCurrent.value).toHaveLength(2)
  })
})

describe('回执形状必须有效才清脏', () => {
  const invalid = [
    { rules: null, loaded: {} }, { rules: [], loaded: {} },
    { rules: { cross_report_note: {} }, loaded: {} }, { rules: { cross_report_note: [null] }, loaded: {} },
    { rules: {} }, { rules: {}, loaded: null }, { rules: {}, loaded: [] },
    { rules: {}, loaded: { slot: 3 } }, { rules: {}, loaded: { slot: {} } },
  ]
  it.each(invalid)('保存异常回执 %# 不替换规则、不清脏、不执行', async response => {
    const { cc, deps } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule()] } })
    deps.api.put.mockResolvedValueOnce(response)
    expect(await cc.persist()).toBe(false); expect(cc.unsaved.value).toBe(true)
    expect(cc.rulesForCurrent.value[0].label).toBe('规则'); expect(cc.tokens.value).toEqual({})
    expect(deps.askApplyScope).not.toHaveBeenCalled(); expect(cc.saving.value).toBe(false)
    await cc.run(); expect(deps.api.get).not.toHaveBeenCalled()
    deps.api.put.mockResolvedValue({ rules: { cross_report_note: [rule()] }, loaded: {} })
    expect(await cc.persist()).toBe(true); expect(deps.api.put).toHaveBeenCalledTimes(2)
  })
  it.each(invalid.filter(response => 'loaded' in response))('读取异常回执 %# 不假成功', async response => {
    const { cc, deps } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule()] } })
    deps.api.get.mockResolvedValue(response)
    expect(await cc.loadUserRules()).toBe(false)
    expect(cc.rulesForCurrent.value[0].label).toBe('规则'); expect(deps.showFormulaError).toHaveBeenCalledTimes(1)
  })
  it('缺槽元数据的既有规则改写不能伪装新增，未改旧规则仍兼容', async () => {
    const { cc, deps } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule()] } })
    cc.rulesForCurrent.value[0].label = '已改'
    expect(await cc.persist()).toBe(false); expect(deps.api.put).not.toHaveBeenCalled()
  })
  it('切项目清除原载入快照，不阻断新项目合法新增', async () => {
    const { cc, deps } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule({ slot_key: 'old' })] } })
    deps.projectId.value = 'p2'; cc.onAdd(); cc.form.value.label = '新项目新增'; cc.onSave()
    await flushPromises(); expect(deps.api.put).toHaveBeenCalledTimes(1); expect(cc.unsaved.value).toBe(false)
  })
})


describe('载入快照按条匹配', () => {
  it('缺令牌但未修改的重复身份不粗暴禁止整表', async () => {
    const { cc, deps } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule(), rule({ label: '另一条' })] }, loaded: {} })
    expect(await cc.persist()).toBe(true); expect(deps.api.put).toHaveBeenCalledTimes(1)
  })
  it('相同槽和业务定义的两条原规则，删除一条不能由另一条冒充未改', async () => {
    const { cc, deps } = setup(), item = rule({ slot_key: 'same' })
    cc.applyRulesData({ rules: { cross_report_note: [{ ...item }, { ...item }] }, loaded: {} })
    cc.rulesForCurrent.value.splice(0, 1)
    expect(await cc.persist()).toBe(false); expect(deps.api.put).not.toHaveBeenCalled(); expect(cc.unsaved.value).toBe(true)
  })
  it('业务不变但更换既有身份也不能冒充合法新增', async () => {
    const { cc, deps } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule({ slot_key: 'old' })] }, loaded: {} })
    cc.rulesForCurrent.value[0].slot_key = 'new'
    expect(await cc.persist()).toBe(false); expect(deps.api.put).not.toHaveBeenCalled()
  })
})

describe('保存同步异常不残留已完成 Promise', () => {
  it('PUT 同步抛错后仍可重试，失败保脏且不执行', async () => {
    const { cc, deps } = setup(); cc.applyRulesData({ rules: { cross_report_note: [rule()] } })
    deps.api.put.mockImplementationOnce(() => { throw new Error('同步失败') })
    expect(await cc.persist()).toBe(false); expect(cc.saving.value).toBe(false); expect(cc.unsaved.value).toBe(true)
    await cc.run(); expect(deps.api.get).not.toHaveBeenCalled()
    deps.api.put.mockResolvedValue({ rules: { cross_report_note: [rule()] }, loaded: {} })
    expect(await cc.persist()).toBe(true); expect(deps.api.put).toHaveBeenCalledTimes(2)
  })
})