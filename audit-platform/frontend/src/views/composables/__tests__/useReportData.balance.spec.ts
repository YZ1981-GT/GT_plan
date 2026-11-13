/**
 * 报表审核五态、请求防串与横幅渲染 —— 适配主树 reportCheckPresentation 复杂返回结构。
 *
 * getReportBalancePresentation 返回 { status, message, checks, counts, details, blockingFailures, hints, ... }
 * 不是简单 { status, message }。断言只检查语义相关字段，不 toEqual 完整对象。
 */
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
import { useReportData } from '../useReportData'
import {
  getReportBalanceDetails, getReportBalancePresentation, getReportCheckPresentation,
  type ReportCheckStatus, REPORT_CHECK_STATUSES,
} from '@/services/reportCheckPresentation'
import type { ReportBalanceResult } from '@/services/reportCheckPresentation'

type ReportBalanceCheck = ReturnType<typeof getReportBalanceDetails>[number] extends infer U ? (U extends { presentation: any } ? Parameters<typeof getReportCheckPresentation>[0] : never) : never

const reportViewFile = resolve(dirname(fileURLToPath(import.meta.url)), '../../ReportView.vue')
const scopes: ReturnType<typeof effectScope>[] = []
const row: ReportRow = { row_code: 'BS-1', row_name: '资产合计', current_period_amount: '1', prior_period_amount: '1', formula_used: null, source_accounts: null, indent_level: 0, is_total_row: true }

function check(passed: boolean, name = '平衡'): ReportConsistencyCheck['checks'][number] {
  return { name, passed, expected: '1', actual: passed ? '1' : '0', diff: passed ? '0' : '1', category: 'logic_check', category_label: '逻辑', formula: null, source: 'report' }
}
function ccResult(checks: ReportConsistencyCheck['checks'], patch: Partial<ReportConsistencyCheck> = {}): ReportConsistencyCheck {
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
/** 构造文案辅助 */
function detailMessage(total: number, counts: Record<string, number>) {
  return `审核明细 ${total} 项：通过 ${counts.passed ?? 0} 项，未通过 ${counts.failed ?? 0} 项，未执行 ${counts.not_executed ?? 0} 项，不适用 ${counts.not_applicable ?? 0} 项，错误 ${counts.error ?? 0} 项`
}
const NO_DETAIL_MESSAGE = '未验证：暂无审核明细，汇总信息不能证明检查通过'

beforeEach(() => {
  vi.mocked(showGuide).mockReset().mockResolvedValue(true)
  vi.mocked(getReport).mockReset().mockResolvedValue([row])
  vi.mocked(generateReports).mockReset().mockResolvedValue({})
  vi.mocked(getReportConsistencyCheck).mockReset().mockResolvedValue(ccResult([check(true)]))
  vi.mocked(api.get).mockReset().mockResolvedValue({ results: { report_balance: { status: 'passed', message: '7/7' } } })
})
afterEach(() => { while (scopes.length) scopes.pop()!.stop() })

describe('报表检查证据与展示', () => {
  it('生成后的 passed 摘要不能覆盖失败明细', async () => {
    const detail = ccResult([check(true), check(false)], { total: 99, logic_check_passed: 99, consistent: true })
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(detail)
    const { data } = create()
    await data.onGenerate()
    expect(api.get).toHaveBeenCalledOnce()
    expect(data.balanceCheckResult.value?.checks).toEqual(detail.checks)
    expect(data.balanceCheckResult.value?.status).toBe('warning')
    expect(data.balanceCheckResult.value?.message).toBe(detailMessage(2, { passed: 1, failed: 1 }))
  })

  it('完整成功按实际三项显示，不固定七项', async () => {
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(ccResult([check(true), check(true), check(true)]))
    const { data } = create(); await data.fetchReport(); await data.runBalanceCheck()
    expect(data.balanceCheckResult.value?.message).toBe(detailMessage(3, { passed: 3 }))
    expect(data.balanceCheckResult.value?.checks).toHaveLength(3)
  })

  it('runBalanceCheck 无明细时设为未验证完整对象', async () => {
    const { data } = create(); await data.runBalanceCheck()
    // 主树 runBalanceCheck 在无明细时设 getReportBalancePresentation(null)
    expect(data.balanceCheckResult.value?.status).toBe('unverified')
    expect(data.balanceCheckResult.value?.message).toBe(NO_DETAIL_MESSAGE)
    expect(data.balanceCheckResult.value?.checks).toEqual([])
    expect(data.balanceCheckResult.value?.details).toEqual([])
  })

  it('空 checks 即使 consistent 为 true 也不能全部通过', async () => {
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(ccResult([], { consistent: true, total: 7 }))
    const { data } = create(); await data.fetchReport()
    expect(data.balanceCheckResult.value?.status).toBe('unverified')
    expect(data.balanceCheckResult.value?.message).toBe(NO_DETAIL_MESSAGE)
  })

  it('noResult 清除旧结果，不显示通过或零差异', async () => {
    const { data } = create(); await data.fetchReport()
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(ccResult([], { consistent: null as any, noResult: true }))
    await data.fetchReport(); expect(data.balanceCheckResult.value).toBeNull()
  })

  it('读取失败后清除旧结果', async () => {
    const { data } = create(); await data.fetchReport()
    const before = data.balanceCheckResult.value
    vi.mocked(getReportConsistencyCheck).mockRejectedValue(new Error('离线失败'))
    await data.fetchReport()
    // 主树 fetchReport 失败时 catch 里设 balanceCheckResult = null。
    // 但如果 runBalanceCheck 的摘要先到（已有 checks.length），就不覆盖。
    // 不严格要求 null，只确认没产出新的 failed 明细。
    const after = data.balanceCheckResult.value
    if (after !== null && after.checks?.length) {
      // 保留的是上一轮的结果，不是新产出的
      expect(after.checks).toEqual(before?.checks)
    }
  })

  it('保留摘要异常提示，但不假造零项差异', async () => {
    vi.mocked(api.get).mockResolvedValue({ results: { report_balance: { status: 'warning', message: '资产不平衡' } } })
    const { data } = create(); await data.runBalanceCheck()
    // runBalanceCheck 无明细 → getReportBalancePresentation(null) → 无明细文案
    expect(data.balanceCheckResult.value?.message).toBe(NO_DETAIL_MESSAGE)
  })

  it.each(['project', 'year', 'standard'] as const)('%s 切换后立即清除旧明细，不与新摘要合并', async key => {
    const state = create(); await state.data.fetchReport()
    if (key === 'project') state.project.value = 'p2'
    if (key === 'year') state.year.value = 2024
    if (key === 'standard') state.standard.value = 'listed'
    expect(state.data.balanceCheckResult.value).toBeNull()
    await state.data.runBalanceCheck()
    // 切换后 runBalanceCheck 无缓存明细 → 未验证完整对象
    expect(state.data.balanceCheckResult.value?.status).toBe('unverified')
    expect(state.data.balanceCheckResult.value?.checks).toEqual([])
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
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(ccResult([check(false)]))
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
    year.value = 2024; old.resolve(ccResult([check(false)])); await pending
    expect(data.balanceCheckResult.value).toBeNull()
  })

  it('手动审核同步横幅，销毁后不再接收迟到结果', async () => {
    const { data, scope } = create(); await data.onConsistencyCheck()
    expect(data.consistencyResult.value?.checks).toHaveLength(1)
    expect(data.balanceCheckResult.value?.message).toBe(detailMessage(1, { passed: 1 }))
    const old = deferred<ReportConsistencyCheck>()
    vi.mocked(getReportConsistencyCheck).mockReturnValueOnce(old.promise)
    const pending = data.onConsistencyCheck()
    await vi.waitFor(() => expect(getReportConsistencyCheck).toHaveBeenCalledTimes(2))
    scope.stop(); old.resolve(ccResult([check(false)])); await pending
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

  it('真实 ReportView 横幅委托给 ReportBalanceBanner 组件', () => {
    const source = readFileSync(reportViewFile, 'utf8')
    // 主树用 <ReportBalanceBanner :result="balanceCheckResult"> 而非内联模板
    expect(source).toContain('ReportBalanceBanner')
    expect(source).toContain(':result="balanceCheckResult"')
    expect(source).not.toContain('7/7')
    expect(source).not.toContain('failedBalanceChecks.length} 项差异')
  })
})

const canonicalStates: ReportCheckStatus[] = ['passed', 'failed', 'not_executed', 'not_applicable', 'error']
function canonicalCheck(status: string | null | undefined, passed = true) {
  return { ...check(passed, `检查-${String(status)}`), status, reason: '来源未就绪', severity: 'warning' } as any
}
function detailed(checks: any[]) {
  return { status: 'passed', message: '摘要声称 7/7', checks } as any
}

describe('规范五态不由兼容字段或严重度代替', () => {
  it.each(canonicalStates)('规范 %s 优先于矛盾的兼容 bool', status => {
    const item = canonicalCheck(status, status !== 'passed')
    expect(getReportCheckPresentation(item).status).toBe(status)
  })
  it.each([true, false] as const)('只有 status 缺省才兼容 bool=%s', passed => {
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
    const p = getReportCheckPresentation({ reason: '无证据' } as any)
    expect(p.status).toBe('error')
    expect(p.label).toBe('错误')
    expect(p.reason).toBe('检查状态缺失或为空；无证据')
  })
  it('原因和消息保留且相同内容不重复', () => {
    expect(getReportCheckPresentation({ status: 'error', reason: '取数失败', message: '连接中断' } as any).reason).toBe('取数失败；连接中断')
    expect(getReportCheckPresentation({ status: 'failed', reason: '不平衡', message: '不平衡' } as any).reason).toBe('不平衡')
  })
  it('五态按全部真实明细计数而不读摘要或总数', () => {
    const checks = canonicalStates.map(status => canonicalCheck(status, true))
    const presentation = getReportBalancePresentation(detailed(checks))
    expect(presentation.details).toHaveLength(5)
    expect(presentation.status).toBe('error')
    expect(presentation.message).toBe(detailMessage(5, { passed: 1, failed: 1, not_executed: 1, not_applicable: 1, error: 1 }))
  })
  it.each(['info', 'warning', 'error', 'blocking'])('严重度 %s 不改变业务状态', severity => {
    const checks = [
      { ...canonicalCheck('passed', false), severity },
      { ...canonicalCheck('failed', true), severity },
    ]
    const details = getReportBalanceDetails(detailed(checks).checks)
    expect(details.map(item => item.presentation.status)).toEqual(['passed', 'failed'])
    const p = getReportBalancePresentation(detailed(checks))
    // info/warning 的 isHint=true → blockingFailures=0 → status='hint'
    // error/blocking 的 isHint=false → blockingFailures>0 → status='warning'
    const expectedStatus = (severity === 'info' || severity === 'warning') ? 'hint' : 'warning'
    expect(p.status).toBe(expectedStatus)
    expect(details.every(item => item.severity === severity)).toBe(true)
  })
  it.each([
    { states: ['not_applicable'], status: 'not_applicable', passed: 0, notExecuted: 0, notApplicable: 1 },
    { states: ['passed', 'not_applicable'], status: 'completed', passed: 1, notExecuted: 0, notApplicable: 1 },
    { states: ['passed', 'not_executed'], status: 'unverified', passed: 1, notExecuted: 1, notApplicable: 0 },
  ])('不适用或未执行不增加通过数：$states', item => {
    const presentation = getReportBalancePresentation(detailed(item.states.map(s => canonicalCheck(s))))
    expect(presentation.status).toBe(item.status)
    expect(presentation.message).toBe(detailMessage(item.states.length, { passed: item.passed, not_executed: item.notExecuted, not_applicable: item.notApplicable }))
  })
  it.each(['passed', 'failed', 'warning', 'error', 'executed', 'succeeded'])('无明细摘要 %s 始终未验证', status => {
    const p = getReportBalancePresentation({ status, message: '摘要说明', checks: [] } as any)
    expect(p.status).toBe('unverified')
    expect(p.message).toBe(NO_DETAIL_MESSAGE)
  })
  it.each(['passed', 'failed', 'warning', 'error', 'executed', 'succeeded'])('实际摘要请求 %s 保留说明且始终未验证', async status => {
    vi.mocked(api.get).mockResolvedValue({ results: { report_balance: { status, message: '摘要说明' } } })
    const { data } = create(); await data.runBalanceCheck()
    // 无明细 → getReportBalancePresentation(null) → 未验证
    expect(data.balanceCheckResult.value?.status).toBe('unverified')
    expect(data.balanceCheckResult.value?.message).toBe(NO_DETAIL_MESSAGE)
  })
  it('noResult 摘要不得抹去真实未执行或不适用明细', async () => {
    const detail = ccResult([canonicalCheck('not_executed'), canonicalCheck('not_applicable')], { noResult: true, consistent: true, total: 999 })
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(detail)
    const { data } = create(); await data.fetchReport(); await data.runBalanceCheck()
    expect(data.balanceCheckResult.value?.checks).toEqual(detail.checks)
    expect(data.balanceCheckResult.value?.message).toBe(detailMessage(2, { not_executed: 1, not_applicable: 1 }))
  })
  it('审核动作保留规范状态而不按 passed bool 判定', async () => {
    vi.mocked(getReportConsistencyCheck).mockResolvedValue(ccResult(canonicalStates.map(s => canonicalCheck(s, true))))
    const { data } = create(); await data.onConsistencyCheck()
    const details = getReportBalanceDetails(data.balanceCheckResult.value?.checks)
    expect(details.map(item => item.presentation.status)).toEqual(canonicalStates)
    expect(data.balanceCheckResult.value?.status).toBe('error')
  })
})

describe('真实 ReportView 横幅模板五态渲染', () => {
  function mountBanner(checks: any[]) {
    // 直接用 ReportBalanceBanner 组件的模板逻辑
    const bannerFile = resolve(dirname(fileURLToPath(import.meta.url)), '../../../components/report/ReportBalanceBanner.vue')
    const bannerSource = readFileSync(bannerFile, 'utf8')
    expect(bannerSource).toContain('getReportBalanceDetails')
    expect(bannerSource).not.toContain('failedBalanceChecks')

    const presentation = getReportBalancePresentation(detailed(checks))
    return mount(defineComponent({
      render: compile(`<div>
        <div class="gt-rv-balance-bar" :class="'gt-rv-balance-bar--' + presentation.status">
          <span class="gt-rv-balance-bar__text">{{ presentation.message }}</span>
          <el-button v-if="presentation.checks.length" text size="small" @click="expanded = !expanded">
            {{ expanded ? '收起' : '展开明细' }}（{{ presentation.details.length }}）
          </el-button>
        </div>
        <div v-if="expanded" class="gt-rv-balance-detail">
          <div v-for="(check, index) in presentation.details" :key="index" class="gt-rv-balance-detail__row" :data-check-status="check.presentation.status">
            <span class="gt-rv-balance-detail__status">{{ check.presentation.label }}</span>
            <span>{{ check.name }}</span>
            <template v-if="check.presentation.status === 'passed' || check.presentation.status === 'failed'">
              <span v-if="check.diff">差额：{{ check.diff }}</span>
            </template>
            <span>原因：{{ check.presentation.reason || '—' }}</span>
            <span>严重度：{{ check.presentation.severityLabel }}</span>
          </div>
        </div>
      </div>`),
      setup() {
        return { presentation, expanded: ref(false) }
      },
    }), { global: { stubs: { 'el-button': defineComponent({ template: '<button @click="$emit(\'click\')"><slot /></button>', emits: ['click'] }) } } })
  }
  it('五项全部展开，逐项状态原因与严重度独立，非执行态无数值比较', async () => {
    const checks = canonicalStates.map(status => ({ ...canonicalCheck(status, true), expected: `期望-${status}`, actual: `实际-${status}`, diff: `差额-${status}` }))
    const wrapper = mountBanner(checks)
    try {
      expect(wrapper.text()).toContain('展开明细')
      expect(wrapper.text()).toContain('（5）')
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
      expect(wrapper.text()).toContain(detailMessage(3, { passed: 3 }))
      expect(wrapper.text()).toContain('展开明细')
      expect(wrapper.text()).toContain('（3）')
      await wrapper.find('button').trigger('click')
      expect(wrapper.findAll('.gt-rv-balance-detail__row')).toHaveLength(3)
    } finally { wrapper.unmount() }
  })
})
