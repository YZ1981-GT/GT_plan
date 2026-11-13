import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, effectScope, ref, type EffectScope } from 'vue'
import type { ReportConsistencyCheck, ReportRow } from '@/services/auditPlatformApi'
const mocks = vi.hoisted(() => ({ getReport: vi.fn(), getCheck: vi.fn(), apiGet: vi.fn(), showGuide: vi.fn(), handleError: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), warning: vi.fn() }, ElMessageBox: { confirm: vi.fn() } }))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn() } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: mocks.apiGet } }))
vi.mock('@/services/auditPlatformApi', () => ({ getReport: mocks.getReport, getReportConsistencyCheck: mocks.getCheck, generateReports: vi.fn() }))
vi.mock('@/composables/useWorkflowGuide', () => ({ showGuide: mocks.showGuide }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: mocks.handleError }))
import { useReportData } from '../useReportData'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function review(status = 'passed', name = '合成审核'): ReportConsistencyCheck {
  return { consistent: false, noResult: false, checks: [
    { name, status, category: 'logic_check', category_label: '勾稽', formula: null, source: 'synthetic' },
  ] }
}
function rows(name: string): ReportRow[] {
  return [{ row_code: name, row_name: name, current_period_amount: '0', prior_period_amount: null,
    formula_used: null, source_accounts: null, indent_level: 0, is_total_row: false }]
}
const scopes: EffectScope[] = []
function createState() {
  const project = ref('synthetic-A'), year = ref<number | null>(2025), standard = ref('soe')
  const activeTab = ref('balance_sheet'), reportMode = ref<'audited' | 'unadjusted' | 'compare'>('audited')
  const scope = effectScope()
  scopes.push(scope)
  const data = scope.run(() => useReportData({ projectId: computed(() => project.value), year: computed(() => year.value),
    currentApplicableStandard: computed(() => standard.value), activeTab, reportMode }))!
  return { data, project, year, standard, activeTab, reportMode, scope }
}
beforeEach(() => {
  mocks.getReport.mockReset().mockResolvedValue([])
  mocks.getCheck.mockReset().mockResolvedValue(review())
  mocks.apiGet.mockReset().mockResolvedValue(null)
  mocks.showGuide.mockReset().mockResolvedValue(true)
  mocks.handleError.mockReset()
})
afterEach(() => { scopes.splice(0).forEach(scope => { scope.stop() }) })

describe('人工审核请求与会话', () => {
  it.each(['project', 'year', 'standard'] as const)('%s 的 ABA 在确认前后都使旧请求失效', async key => {
    const state = createState()
    const target = state[key]
    const before = target.value
    const confirmation = deferred<boolean>()
    mocks.showGuide.mockReturnValueOnce(confirmation.promise)
    const pending = state.data.onConsistencyCheck()
    await vi.waitFor(() => { expect(mocks.showGuide).toHaveBeenCalledTimes(1) })
    if (key === 'year') { state.year.value = 2024; state.year.value = before as number }
    else if (key === 'project') { state.project.value = 'synthetic-B'; state.project.value = before as string }
    else { state.standard.value = 'listed'; state.standard.value = before as string }
    confirmation.resolve(true)
    expect(await pending).toBeNull()
    expect(mocks.getCheck).not.toHaveBeenCalled()
    expect(state.data.consistencyResult.value).toBeNull()
  })

  it.each(['project', 'year', 'standard'] as const)('%s 的 ABA 拒绝已发出请求的迟到结果', async key => {
    const state = createState()
    const response = deferred<ReportConsistencyCheck>()
    mocks.getCheck.mockReturnValueOnce(response.promise)
    const pending = state.data.onConsistencyCheck()
    await vi.waitFor(() => { expect(mocks.getCheck).toHaveBeenCalledTimes(1) })
    if (key === 'year') { state.year.value = 2024; state.year.value = 2025 }
    else if (key === 'project') { state.project.value = 'synthetic-B'; state.project.value = 'synthetic-A' }
    else { state.standard.value = 'listed'; state.standard.value = 'soe' }
    response.resolve(review('failed', '旧响应'))
    expect(await pending).toBeNull()
    expect(state.data.consistencyResult.value).toBeNull()
    expect(state.data.balanceCheckResult.value).toBeNull()
    expect(state.data.checkLoading.value).toBe(false)
  })

  it('同上下文逆序返回时只采用最后一次，旧 finally 不清新请求 loading', async () => {
    const { data } = createState()
    const first = deferred<ReportConsistencyCheck>(), second = deferred<ReportConsistencyCheck>()
    mocks.getCheck.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const a = data.onConsistencyCheck()
    await vi.waitFor(() => { expect(mocks.getCheck).toHaveBeenCalledTimes(1) })
    const b = data.onConsistencyCheck()
    await vi.waitFor(() => { expect(mocks.getCheck).toHaveBeenCalledTimes(2) })
    first.resolve(review('failed', '旧响应'))
    expect(await a).toBeNull()
    expect(data.checkLoading.value).toBe(true)
    second.resolve(review('passed', '新响应'))
    const completed = await b
    expect(completed?.isCurrent()).toBe(true)
    expect(completed?.result).toBe(data.consistencyResult.value)
    expect(data.consistencyResult.value?.checks[0].name).toBe('新响应')
    expect(data.checkLoading.value).toBe(false)
  })

  it('后一次先完成时旧响应不得覆盖，返回闭包仍有效', async () => {
    const { data } = createState()
    const first = deferred<ReportConsistencyCheck>(), second = deferred<ReportConsistencyCheck>()
    mocks.getCheck.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const a = data.onConsistencyCheck()
    await vi.waitFor(() => { expect(mocks.getCheck).toHaveBeenCalledTimes(1) })
    const b = data.onConsistencyCheck()
    await vi.waitFor(() => { expect(mocks.getCheck).toHaveBeenCalledTimes(2) })
    second.resolve(review('passed', '新响应'))
    const completed = await b
    first.resolve(review('failed', '旧响应'))
    expect(await a).toBeNull()
    expect(completed?.isCurrent()).toBe(true)
    expect(data.consistencyResult.value?.checks[0].name).toBe('新响应')
  })
})

describe('审核生命周期和摘要边界', () => {
  it('取消确认不重用旧结果；切上下文后旧 completion 失效', async () => {
    const state = createState()
    const completed = await state.data.onConsistencyCheck()
    const original = state.data.consistencyResult.value
    mocks.showGuide.mockResolvedValueOnce(false)
    expect(await state.data.onConsistencyCheck()).toBeNull()
    expect(state.data.consistencyResult.value).toBe(original)
    expect(mocks.getCheck).toHaveBeenCalledTimes(1)
    expect(completed?.isCurrent()).toBe(false)
    state.project.value = 'synthetic-B'
    expect(state.data.consistencyResult.value).toBeNull()
    expect(state.data.balanceCheckResult.value).toBeNull()
  })

  it('scope 销毁后迟到审核不得写回或继续 loading', async () => {
    const state = createState(), response = deferred<ReportConsistencyCheck>()
    mocks.getCheck.mockReturnValueOnce(response.promise)
    const pending = state.data.onConsistencyCheck()
    await vi.waitFor(() => { expect(mocks.getCheck).toHaveBeenCalledTimes(1) })
    state.scope.stop()
    response.resolve(review())
    expect(await pending).toBeNull()
    expect(state.data.consistencyResult.value).toBeNull()
    expect(state.data.balanceCheckResult.value).toBeNull()
    expect(state.data.checkLoading.value).toBe(false)
  })

  it('旧上下文的拒绝响应被忽略；当前拒绝正常报错且不伪造结果', async () => {
    const state = createState(), response = deferred<ReportConsistencyCheck>()
    mocks.getCheck.mockReturnValueOnce(response.promise)
    const pending = state.data.onConsistencyCheck()
    await vi.waitFor(() => { expect(mocks.getCheck).toHaveBeenCalledTimes(1) })
    state.project.value = 'synthetic-B'
    response.reject(new Error('旧请求失败'))
    expect(await pending).toBeNull()
    expect(mocks.handleError).not.toHaveBeenCalled()
    const currentError = new Error('当前请求失败')
    mocks.getCheck.mockRejectedValueOnce(currentError)
    expect(await state.data.onConsistencyCheck()).toBeNull()
    expect(mocks.handleError).toHaveBeenCalledWith(currentError, '报表审核')
    expect(state.data.consistencyResult.value).toBeNull()
  })

  it('摘要不能证明通过，且不能覆盖已取得的五态明细', async () => {
    const { data } = createState()
    mocks.apiGet.mockResolvedValue({ results: { report_balance: { status: 'passed', message: '全部通过' } } })
    await data.runBalanceCheck()
    expect(data.balanceCheckResult.value?.status).toBe('unverified')
    await data.onConsistencyCheck()
    const full = data.balanceCheckResult.value
    await data.runBalanceCheck()
    expect(data.balanceCheckResult.value).toBe(full)
  })
})

describe('静默审核及报表取数围栏', () => {
  it('no_result 空明细清横幅，迟到摘要不能把它重新填回', async () => {
    const { data } = createState()
    await data.onConsistencyCheck()
    const summary = deferred<unknown>()
    mocks.apiGet.mockReturnValueOnce(summary.promise)
    const pendingSummary = data.runBalanceCheck()
    mocks.getReport.mockResolvedValueOnce(rows('当前行'))
    mocks.getCheck.mockResolvedValueOnce({ consistent: null, noResult: true, checks: [] })
    await data.fetchReport()
    expect(data.balanceCheckResult.value).toBeNull()
    summary.resolve({ results: { report_balance: { status: 'passed' } } })
    await pendingSummary
    expect(data.balanceCheckResult.value).toBeNull()
  })

  it('同上下文切页签静默加载保留人工审核；有真明细的 no_result 仍展示五态', async () => {
    const state = createState()
    await state.data.onConsistencyCheck()
    const original = state.data.consistencyResult.value
    state.activeTab.value = 'income_statement'
    mocks.getReport.mockResolvedValueOnce(rows('IS-001'))
    mocks.getCheck.mockResolvedValueOnce({ ...review('not_applicable'), noResult: true })
    await state.data.fetchReport()
    expect(state.data.consistencyResult.value).toBe(original)
    expect(state.data.balanceCheckResult.value?.counts.not_applicable).toBe(1)
    expect(state.data.balanceCheckResult.value?.status).toBe('not_applicable')
  })

  it('同上下文取数逆序只保留最新行，旧 finally 不清最新 loading', async () => {
    const { data } = createState()
    const first = deferred<ReportRow[]>(), second = deferred<ReportRow[]>()
    mocks.getReport.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const a = data.fetchReport(), b = data.fetchReport()
    first.resolve(rows('旧行'))
    await a
    expect(data.loading.value).toBe(true)
    expect(data.rows.value).toEqual([])
    second.resolve(rows('新行'))
    await b
    expect(data.rows.value[0].row_code).toBe('新行')
    expect(data.loading.value).toBe(false)
    expect(mocks.getCheck).toHaveBeenCalledTimes(1)
  })

  it('比较模式迟到双响应不能覆盖已切换的普通报表', async () => {
    const state = createState()
    state.reportMode.value = 'compare'
    const audited = deferred<ReportRow[]>(), unadjusted = deferred<ReportRow[]>()
    mocks.getReport.mockReturnValueOnce(audited.promise).mockReturnValueOnce(unadjusted.promise)
    const old = state.data.fetchReport()
    state.reportMode.value = 'audited'
    mocks.getReport.mockResolvedValueOnce(rows('当前行'))
    await state.data.fetchReport()
    audited.resolve(rows('旧审定行')); unadjusted.resolve(rows('旧未审行'))
    await old
    expect(state.data.rows.value[0].row_code).toBe('当前行')
    expect(state.data.compareRows.value).toEqual([])
    expect(state.data.equityCompareAudited.value).toEqual([])
    expect(state.data.equityCompareUnadjusted.value).toEqual([])
  })
})

describe('模板回退与元数据晚到', () => {
  it('404 模板回退沿用原票据，不覆盖切换后的当前行', async () => {
    const state = createState(), template = deferred<unknown>()
    mocks.getReport.mockRejectedValueOnce({ response: { status: 404 } })
    mocks.apiGet.mockReturnValueOnce(template.promise)
    const old = state.data.fetchReport()
    await vi.waitFor(() => { expect(mocks.apiGet).toHaveBeenCalledTimes(1) })
    state.activeTab.value = 'income_statement'
    mocks.getReport.mockResolvedValueOnce(rows('IS-当前'))
    await state.data.fetchReport()
    template.resolve([{ row_code: 'BS-过期模板', row_name: '旧模板' }])
    await old
    expect(state.data.rows.value[0].row_code).toBe('IS-当前')
    expect(mocks.getCheck).toHaveBeenCalledTimes(1)
  })

  it('模板请求与报表取数共用 rows lane，后发报表赢且旧 finally 不清 loading', async () => {
    const { data } = createState(), template = deferred<unknown>(), report = deferred<ReportRow[]>()
    mocks.apiGet.mockReturnValueOnce(template.promise)
    const old = data.loadTemplateRows()
    mocks.getReport.mockReturnValueOnce(report.promise)
    const current = data.fetchReport()
    template.resolve([{ row_code: '旧模板' }])
    await old
    expect(data.loading.value).toBe(true)
    expect(data.rows.value).toEqual([])
    report.resolve(rows('当前行'))
    await current
    expect(data.rows.value[0].row_code).toBe('当前行')
    expect(data.loading.value).toBe(false)
  })

  it('项目 ABA 使迟到的详情失效，不继续请求旧向导', async () => {
    const state = createState(), details = deferred<unknown>()
    mocks.apiGet.mockReturnValueOnce(details.promise)
    const pending = state.data.ensureProjectYear()
    state.project.value = 'synthetic-B'
    state.project.value = 'synthetic-A'
    details.resolve({ name: '旧项目', audit_year: 2024, template_type: 'listed', report_scope: 'consolidated' })
    await pending
    expect(mocks.apiGet).toHaveBeenCalledTimes(1)
    expect(state.data.projectName.value).toBe('')
    expect(state.data._fetchedAuditYear.value).toBeNull()
    expect(state.data.templateType.value).toBe('')
    expect(state.data.reportScope.value).toBe('standalone')
  })

  it('换项目后迟到的旧向导不得覆盖当前项目元数据', async () => {
    const state = createState(), oldWizard = deferred<unknown>()
    mocks.apiGet.mockResolvedValueOnce({ name: '旧项目', audit_year: 2024, template_type: 'soe' })
      .mockReturnValueOnce(oldWizard.promise)
    const old = state.data.ensureProjectYear()
    await vi.waitFor(() => { expect(mocks.apiGet).toHaveBeenCalledTimes(2) })
    state.project.value = 'synthetic-B'
    mocks.apiGet.mockResolvedValueOnce({ client_name: '当前项目', audit_year: 2025, template_type: 'soe', report_scope: 'standalone' })
      .mockResolvedValueOnce({ steps: { basic_info: { data: { template_type: 'listed', report_scope: 'consolidated' } } } })
    await state.data.ensureProjectYear()
    oldWizard.resolve({ steps: { basic_info: { data: { client_name: '过期向导', template_type: 'soe', report_scope: 'standalone' } } } })
    await old
    expect(state.data.projectName.value).toBe('当前项目')
    expect(state.data._fetchedAuditYear.value).toBe(2025)
    expect(state.data.templateType.value).toBe('listed')
    expect(state.data.reportScope.value).toBe('consolidated')
    expect(state.data.isConsolidated.value).toBe(true)
    expect(mocks.apiGet.mock.calls.map(call => call[0])).toEqual([
      '/api/projects/synthetic-A', '/api/projects/synthetic-A/wizard',
      '/api/projects/synthetic-B', '/api/projects/synthetic-B/wizard',
    ])
  })

  it('同项目重复加载只接受最后一次详情；旧错误不抹掉当前年度', async () => {
    const state = createState(), first = deferred<unknown>()
    mocks.apiGet.mockReturnValueOnce(first.promise)
    const old = state.data.ensureProjectYear()
    mocks.apiGet.mockResolvedValueOnce({ name: '当前详情', audit_year: 2025, template_type: 'soe' })
      .mockResolvedValueOnce(null)
    await state.data.ensureProjectYear()
    first.reject(new Error('旧详情失败'))
    await old
    expect(state.data.projectName.value).toBe('当前详情')
    expect(state.data._fetchedAuditYear.value).toBe(2025)
    expect(mocks.apiGet).toHaveBeenCalledTimes(3)
  })

  it('元数据请求所在 scope 销毁后，迟到详情不落状态且不请求向导', async () => {
    const state = createState(), details = deferred<unknown>()
    mocks.apiGet.mockReturnValueOnce(details.promise)
    const pending = state.data.ensureProjectYear()
    state.scope.stop()
    details.resolve({ name: '已销毁项目', audit_year: 2024 })
    await pending
    expect(state.data.projectName.value).toBe('')
    expect(state.data._fetchedAuditYear.value).toBeNull()
    expect(mocks.apiGet).toHaveBeenCalledTimes(1)
  })

  it('非法页签清行并结束 loading，不请求模板或报表', async () => {
    const state = createState()
    state.data.rows.value = rows('旧行')
    state.data.loading.value = true
    state.activeTab.value = 'analysis'
    await state.data.loadTemplateRows()
    expect(state.data.rows.value).toEqual([])
    expect(state.data.loading.value).toBe(false)
    expect(mocks.apiGet).not.toHaveBeenCalled()
    expect(mocks.getReport).not.toHaveBeenCalled()
  })
})
