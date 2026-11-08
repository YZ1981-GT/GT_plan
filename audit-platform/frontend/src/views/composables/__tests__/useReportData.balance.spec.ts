import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { compile, computed, defineComponent, effectScope, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { ReportConsistencyCheck, ReportRow } from '@/services/auditPlatformApi'
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), warning: vi.fn() }, ElMessageBox: { confirm: vi.fn() } }))
vi.mock('@/services/auditPlatformApi', () => ({ generateReports: vi.fn(), getReport: vi.fn(), getReportConsistencyCheck: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn() } }))
vi.mock('@/composables/useWorkflowGuide', () => ({ showGuide: vi.fn().mockResolvedValue(true) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
import { generateReports, getReport, getReportConsistencyCheck } from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'
import { showGuide } from '@/composables/useWorkflowGuide'
import {
  getReportBalanceDetails, getReportBalancePresentation, getReportCheckPresentation, useReportData,
  type ReportBalanceCheck, type ReportBalanceCheckResult, type ReportCheckStatus,
} from '../useReportData'
const reportViewFile = resolve(dirname(fileURLToPath(import.meta.url)), '../../ReportView.vue')
const scopes: ReturnType<typeof effectScope>[] = []
const row: ReportRow = { row_code: 'BS-1', row_name: '资产合计', current_period_amount: '1', prior_period_amount: '1', formula_used: null, source_accounts: null, indent_level: 0, is_total_row: true }
function check(passed: boolean, name = '平衡'): ReportConsistencyCheck['checks'][number] {
  return { name, passed, expected: '1', actual: passed ? '1' : '0', diff: passed ? '0' : '1', category: 'logic_check', category_label: '逻辑', formula: null, source: 'report' }
}
function result(checks: ReportConsistencyCheck['checks'], patch: Partial<ReportConsistencyCheck> = {}): ReportConsistencyCheck {
  return { consistent: checks.every(item => item.passed), noResult: false, checks, total: checks.length, ...patch }
}
function create() {
  const project = ref('p1'); const year = ref<number | null>(2025); const standard = ref('soe')
  const scope = effectScope(); scopes.push(scope)
  const data = scope.run(() => useReportData({ projectId: computed(() => project.value), year: computed(() => year.value), currentApplicableStandard: computed(() => standard.value), activeTab: ref('balance_sheet'), reportMode: ref('audited') }))!
  return { data, project, year, standard, scope }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
beforeEach(() => {
  vi.mocked(showGuide).mockReset().mockResolvedValue(true)
  vi.mocked(getReport).mockReset().mockResolvedValue([row])
  vi.mocked(generateReports).mockReset().mockResolvedValue({})
  vi.mocked(getReportConsistencyCheck).mockReset().mockResolvedValue(result([check(true)]))
  vi.mocked(api.get).mockReset().mockResolvedValue({ results: { report_balance: { status: 'passed', message: '7/7' } } })
})
afterEach(() => { while (scopes.length) scopes.pop()!.stop() })
describe('报表检查证据与展示', () => {
  it('生成后的 passed 摘要不能覆盖失败明细', async () => {
    const detail = result([check(true), check(false)], { total: 99, logic_check_passed: 99, consistent: true })
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(detail)
    const { data } = create()
    await data.onGenerate()
    expect(api.get).toHaveBeenCalledOnce()
    expect(data.balanceCheckResult.value?.checks).toEqual(detail.checks)
    expect(data.balanceCheckResult.value?.status).toBe('warning')
    expect(data.balanceCheckResult.value?.message).toBe('审核明细 2 项：通过 1 项，未通过 1 项，未执行 0 项，不适用 0 项，错误 0 项')
  })
  it('完整成功按实际三项显示，不固定七项', async () => {
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(result([check(true), check(true), check(true)]))
    const { data } = create(); await data.fetchReport(); await data.runBalanceCheck()
    expect(data.balanceCheckResult.value?.message).toBe('审核明细 3 项：通过 3 项，未通过 0 项，未执行 0 项，不适用 0 项，错误 0 项')
    expect(data.balanceCheckResult.value?.checks).toHaveLength(3)
  })
  it('passed 摘要没有 checks 时仅为未验证', async () => {
    const { data } = create(); await data.runBalanceCheck()
    expect(data.balanceCheckResult.value).toEqual({ status: 'unverified', message: '7/7' })
    expect(getReportBalancePresentation(data.balanceCheckResult.value).message).toBe('未验证：暂无审核明细，汇总信息不能证明检查通过')
  })
  it('空 checks 即使 consistent 为 true 也不能全部通过', async () => {
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(result([], { consistent: true, total: 7 }))
    const { data } = create(); await data.fetchReport()
    expect(data.balanceCheckResult.value?.status).toBe('unverified')
    expect(data.balanceCheckResult.value?.message).not.toContain('通过')
  })
  it('noResult 清除旧结果，不显示通过或零差异', async () => {
    const { data } = create(); await data.fetchReport()
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(result([], { consistent: null, noResult: true }))
    await data.fetchReport(); expect(data.balanceCheckResult.value).toBeNull()
  })
  it('读取失败不得残留上一轮通过状态', async () => {
    const { data } = create(); await data.fetchReport()
    vi.mocked(getReportConsistencyCheck).mockRejectedValue(new Error('离线失败'))
    await data.fetchReport(); expect(data.balanceCheckResult.value).toBeNull()
  })
  it('保留摘要异常提示，但不假造零项差异', async () => {
    vi.mocked(api.get).mockResolvedValue({ results: { report_balance: { status: 'warning', message: '资产不平衡' } } })
    const { data } = create(); await data.runBalanceCheck()
    expect(getReportBalancePresentation(data.balanceCheckResult.value).message).toBe('未验证：暂无审核明细，汇总信息不能证明检查通过')
  })
  it.each(['project', 'year', 'standard'] as const)('%s 切换后立即清除旧明细，不与新摘要合并', async key => {
    const state = create(); await state.data.fetchReport()
    if (key === 'project') state.project.value = 'p2'
    if (key === 'year') state.year.value = 2024
    if (key === 'standard') state.standard.value = 'listed'
    expect(state.data.balanceCheckResult.value).toBeNull()
    await state.data.runBalanceCheck()
    expect(state.data.balanceCheckResult.value?.checks).toBeUndefined()
    expect(state.data.balanceCheckResult.value?.status).toBe('unverified')
  })
  it('A→B→A 后丢弃旧摘要响应', async () => {
    const old = deferred<{ results: { report_balance: { status: string; message: string } } }>()
    vi.mocked(api.get).mockReturnValueOnce(old.promise)
    const { data, project } = create(); const pending = data.runBalanceCheck()
    project.value = 'p2'; project.value = 'p1'
    old.resolve({ results: { report_balance: { status: 'passed', message: '旧结果' } } })
    await pending; expect(data.balanceCheckResult.value).toBeNull()
  })
  it('新明细先返回时，晚到摘要仍不能覆盖', async () => {
    const old = deferred<{ results: { report_balance: { status: string; message: string } } }>()
    vi.mocked(api.get).mockReturnValueOnce(old.promise)
    const { data } = create(); const pending = data.runBalanceCheck()
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(result([check(false)]))
    await data.fetchReport()
    old.resolve({ results: { report_balance: { status: 'passed', message: '旧摘要' } } })
    await pending; expect(data.balanceCheckResult.value?.status).toBe('warning')
    expect(data.balanceCheckResult.value?.checks).toHaveLength(1)
  })
  it('年度切换后丢弃迟到完整检查', async () => {
    const old = deferred<ReportConsistencyCheck>()
    vi.mocked(getReportConsistencyCheck).mockReturnValueOnce(old.promise)
    const { data, year } = create(); const pending = data.fetchReport()
    await vi.waitFor(() => expect(getReportConsistencyCheck).toHaveBeenCalledOnce())
    year.value = 2024; old.resolve(result([check(false)])); await pending
    expect(data.balanceCheckResult.value).toBeNull()
  })
  it('手动审核同步横幅，销毁后不再接收迟到结果', async () => {
    const { data, scope } = create(); await data.onConsistencyCheck()
    expect(data.consistencyResult.value?.checks).toHaveLength(1)
    expect(data.balanceCheckResult.value?.message).toBe('审核明细 1 项：通过 1 项，未通过 0 项，未执行 0 项，不适用 0 项，错误 0 项')
    const old = deferred<ReportConsistencyCheck>()
    vi.mocked(getReportConsistencyCheck).mockReturnValueOnce(old.promise)
    const pending = data.onConsistencyCheck()
    await vi.waitFor(() => expect(getReportConsistencyCheck).toHaveBeenCalledTimes(2))
    scope.stop(); old.resolve(result([check(false)])); await pending
    expect(data.balanceCheckResult.value).toBeNull()
  })
  it.each(['project', 'year', 'standard', 'project-roundtrip', 'disposed'] as const)('确认等待期间 %s 变化后不执行旧审核', async key => {
    const guide = deferred<boolean>()
    vi.mocked(showGuide).mockReturnValueOnce(guide.promise)
    const state = create(); const pending = state.data.onConsistencyCheck()
    await vi.waitFor(() => expect(showGuide).toHaveBeenCalledOnce())
    if (key === 'project') state.project.value = 'p2'
    if (key === 'year') state.year.value = 2024
    if (key === 'standard') state.standard.value = 'listed'
    if (key === 'project-roundtrip') { state.project.value = 'p2'; state.project.value = 'p1' }
    if (key === 'disposed') state.scope.stop()
    if (key !== 'disposed') await state.data.fetchReport()
    const current = state.data.balanceCheckResult.value
    const calls = vi.mocked(getReportConsistencyCheck).mock.calls.length
    guide.resolve(true); await pending
    expect(getReportConsistencyCheck).toHaveBeenCalledTimes(calls)
    expect(state.data.balanceCheckResult.value).toEqual(current)
    expect(state.data.consistencyResult.value).toBeNull()
  })
  it('真实 ReportView 横幅绑定展示函数而非固定文案或摘要状态', () => {
    const source = readFileSync(reportViewFile, 'utf8')
    const banner = source.slice(source.indexOf('<!-- F29:'), source.indexOf('<transition name="el-zoom-in-top">'))
    expect(banner).toContain('balanceCheckPresentation.message')
    expect(banner).toContain("'gt-rv-balance-bar--' + balanceCheckPresentation.status")
    expect(source).toContain('computed(() => getReportBalancePresentation(balanceCheckResult.value))')
    expect(banner).not.toContain('7/7')
    expect(banner).not.toContain('failedBalanceChecks.length} 项差异')
  })
})

const canonicalStates: ReportCheckStatus[] = ['passed', 'failed', 'not_executed', 'not_applicable', 'error']
function canonicalCheck(status: string | null | undefined, passed = true): ReportBalanceCheck & { passed: boolean } {
  return { ...check(passed, `检查-${String(status)}`), status, reason: '来源未就绪', severity: 'warning' }
}
function detailed(checks: ReportBalanceCheck[]): ReportBalanceCheckResult {
  return { status: 'passed', message: '摘要声称 7/7', checks }
}

describe('规范五态不由兼容字段或严重度代替', () => {
  it.each(canonicalStates)('规范 %s 优先于矛盾的兼容 bool', status => {
    const item = canonicalCheck(status, status !== 'passed')
    expect(getReportCheckPresentation(item).status).toBe(status)
  })
  it.each([true, false])('只有 status 缺省才兼容 bool=%s', passed => {
    const item = check(passed)
    expect(Object.prototype.hasOwnProperty.call(item, 'status')).toBe(false)
    expect(getReportCheckPresentation(item).status).toBe(passed ? 'passed' : 'failed')
  })
  it.each([undefined, null, '', ' ', 'unknown', 'executed', 'succeeded'])('非法或运行态 %s 不回退为通过', status => {
    const presentation = getReportCheckPresentation(canonicalCheck(status, true))
    expect(presentation.status).toBe('error')
    expect(presentation.label).toBe('错误')
    expect(presentation.reason).toContain('来源未就绪')
    expect(presentation.reason).toContain(status == null || status === '' ? '检查状态缺失或为空' : `未知检查状态：${status}`)
  })
  it('status 和 bool 都缺失时按错误而非通过', () => {
    expect(getReportCheckPresentation({ reason: '无证据' })).toEqual({ status: 'error', label: '错误', reason: '检查状态缺失或为空；无证据' })
  })
  it('原因和消息保留且相同内容不重复', () => {
    expect(getReportCheckPresentation({ status: 'error', reason: '取数失败', message: '连接中断' }).reason).toBe('取数失败；连接中断')
    expect(getReportCheckPresentation({ status: 'failed', reason: '不平衡', message: '不平衡' }).reason).toBe('不平衡')
  })
  it('五态按全部真实明细计数而不读摘要或总数', () => {
    const checks = canonicalStates.map(status => canonicalCheck(status, true))
    expect(getReportBalanceDetails(detailed(checks))).toHaveLength(5)
    expect(getReportBalancePresentation(detailed(checks))).toEqual({ status: 'error', message: '审核明细 5 项：通过 1 项，未通过 1 项，未执行 1 项，不适用 1 项，错误 1 项' })
  })
  it.each(['info', 'warning', 'error', 'blocking'])('严重度 %s 不改变业务状态', severity => {
    const checks = [
      { ...canonicalCheck('passed', false), severity },
      { ...canonicalCheck('failed', true), severity },
    ]
    expect(getReportBalanceDetails(detailed(checks)).map(item => item.presentation.status)).toEqual(['passed', 'failed'])
    expect(getReportBalancePresentation(detailed(checks)).status).toBe('warning')
    expect(getReportBalanceDetails(detailed(checks)).every(item => item.severity === severity)).toBe(true)
  })
  it.each([
    { states: ['not_applicable'], status: 'not_applicable', passed: 0, notExecuted: 0, notApplicable: 1 },
    { states: ['passed', 'not_applicable'], status: 'completed', passed: 1, notExecuted: 0, notApplicable: 1 },
    { states: ['passed', 'not_executed'], status: 'unverified', passed: 1, notExecuted: 1, notApplicable: 0 },
  ])('不适用或未执行不增加通过数：$states', item => {
    const presentation = getReportBalancePresentation(detailed(item.states.map(status => canonicalCheck(status))))
    expect(presentation.status).toBe(item.status)
    expect(presentation.message).toBe(`审核明细 ${item.states.length} 项：通过 ${item.passed} 项，未通过 0 项，未执行 ${item.notExecuted} 项，不适用 ${item.notApplicable} 项，错误 0 项`)
  })
  it.each(['passed', 'failed', 'warning', 'error', 'executed', 'succeeded'])('无明细摘要 %s 始终未验证', status => {
    expect(getReportBalancePresentation({ status, message: '摘要说明', checks: [] })).toEqual({ status: 'unverified', message: '未验证：暂无审核明细，汇总信息不能证明检查通过' })
  })
  it.each(['passed', 'failed', 'warning', 'error', 'executed', 'succeeded'])('实际摘要请求 %s 保留说明且始终未验证', async status => {
    vi.mocked(api.get).mockResolvedValue({ results: { report_balance: { status, message: '摘要说明' } } })
    const { data } = create(); await data.runBalanceCheck()
    expect(data.balanceCheckResult.value).toEqual({ status: 'unverified', message: '摘要说明' })
    expect(getReportBalancePresentation(data.balanceCheckResult.value).message).toBe('未验证：暂无审核明细，汇总信息不能证明检查通过')
  })
  it('noResult 摘要不得抹去真实未执行或不适用明细', async () => {
    const detail = result([canonicalCheck('not_executed'), canonicalCheck('not_applicable')], { noResult: true, consistent: true, total: 999 })
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(detail)
    const { data } = create(); await data.fetchReport(); await data.runBalanceCheck()
    expect(data.balanceCheckResult.value?.checks).toEqual(detail.checks)
    expect(data.balanceCheckResult.value?.message).toBe('审核明细 2 项：通过 0 项，未通过 0 项，未执行 1 项，不适用 1 项，错误 0 项')
  })
  it('审核动作保留规范状态而不按 passed bool 判定', async () => {
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(result(canonicalStates.map(status => canonicalCheck(status, true))))
    const { data } = create(); await data.onConsistencyCheck()
    expect(getReportBalanceDetails(data.balanceCheckResult.value).map(item => item.presentation.status)).toEqual(canonicalStates)
    expect(data.balanceCheckResult.value?.status).toBe('error')
  })
})

describe('真实 ReportView 横幅模板五态渲染', () => {
  function mountBanner(checks: ReportBalanceCheck[]) {
    const source = readFileSync(reportViewFile, 'utf8')
    const start = source.indexOf('<!-- F29:')
    const end = source.indexOf('<!-- Sprint 4：', start)
    expect(start).toBeGreaterThan(-1)
    expect(end).toBeGreaterThan(start)
    const template = source.slice(start, end)
    expect(template).not.toContain('failedBalanceChecks')
    expect(source).toContain('computed(() => getReportBalanceDetails(balanceCheckResult.value))')
    return mount(defineComponent({
      render: compile(template),
      setup() {
        const balanceCheckResult = ref<ReportBalanceCheckResult | null>(detailed(checks))
        return {
          balanceCheckResult, rvBalanceExpanded: ref(false), scrollToReportRow: vi.fn(),
          balanceCheckPresentation: computed(() => getReportBalancePresentation(balanceCheckResult.value)),
          balanceCheckDetails: computed(() => getReportBalanceDetails(balanceCheckResult.value)),
        }
      },
    }), { global: { stubs: { 'el-button': defineComponent({ template: '<button><slot /></button>' }) } } })
  }
  it('五项全部展开，逐项状态原因与严重度独立，非执行态无数值比较', async () => {
    const checks = canonicalStates.map(status => ({ ...canonicalCheck(status, true), expected: `期望-${status}`, actual: `实际-${status}`, diff: `差额-${status}` }))
    const wrapper = mountBanner(checks)
    try {
      expect(wrapper.text()).toContain('展开明细（5）')
      await wrapper.find('button').trigger('click')
      const details = wrapper.findAll('.gt-rv-balance-detail__row')
      expect(details).toHaveLength(5)
      expect(details.map(item => item.find('.gt-rv-balance-detail__status').text())).toEqual(['通过', '未通过', '未执行', '不适用', '错误'])
      for (const [index, item] of details.entries()) {
        expect(item.text()).toContain('原因：来源未就绪')
        expect(item.text()).toContain('严重度：警告')
        if (index < 2) expect(item.text()).toContain(`差额-${canonicalStates[index]}`)
        else expect(item.text()).not.toContain(`差额-${canonicalStates[index]}`)
      }
      expect(wrapper.find('.gt-rv-balance-bar--error').exists()).toBe(true)
    } finally { wrapper.unmount() }
  })
  it('全部通过时仍可展开全部真实三项而非仅失败项', async () => {
    const wrapper = mountBanner([check(true, '甲'), check(true, '乙'), check(true, '丙')])
    try {
      expect(wrapper.text()).toContain('审核明细 3 项：通过 3 项')
      expect(wrapper.text()).toContain('展开明细（3）')
      await wrapper.find('button').trigger('click')
      expect(wrapper.findAll('.gt-rv-balance-detail__row')).toHaveLength(3)
    } finally { wrapper.unmount() }
  })
})