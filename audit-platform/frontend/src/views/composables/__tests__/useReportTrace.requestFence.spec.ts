import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, effectScope, ref, type EffectScope } from 'vue'
import { Blob as NodeBlob } from 'node:buffer'
const mocks = vi.hoisted(() => ({ get: vi.fn(), handleError: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('element-plus', () => ({ ElMessage: { info: mocks.info, success: mocks.success, warning: mocks.warning } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: mocks.get } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: mocks.handleError }))
vi.mock('@/services/openWorkpaperCell', () => ({ openWorkpaperCell: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
import { useReportTrace } from '../useReportTrace'
import { mapReportConsistencyCheck } from '@/services/auditPlatformApi'
import { reportChecksToCsv } from '@/services/reportCheckPresentation'

function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const scopes: EffectScope[] = []
function createState() {
  const project = ref('synthetic-A'), year = ref<number | null>(2025), activeTab = ref('balance_sheet')
  const consistencyResult = ref(mapReportConsistencyCheck({ checks: [{ name: '利润表合理性', status: 'failed', severity: 'warning' }] }))
  const rvCtx = { closeContextMenu: vi.fn(), contextMenu: { rowData: { row_code: 'BS-001' } } }
  const fetchReport = vi.fn().mockResolvedValue(undefined), scope = effectScope()
  scopes.push(scope)
  const trace = scope.run(() => useReportTrace({ projectId: computed(() => project.value), year: computed(() => year.value),
    activeTab, activeTabLabel: computed(() => '资产负债表'), consistencyResult, fetchReport, rvCtx: rvCtx as any }))!
  return { trace, project, year, activeTab, consistencyResult, rvCtx, fetchReport, scope }
}
const lineage = (label: string) => ({ upstream: [{ label }], downstream: [], attachments: [] })
beforeEach(() => {
  mocks.get.mockReset(); mocks.handleError.mockReset(); mocks.info.mockReset(); mocks.success.mockReset(); mocks.warning.mockReset()
})
afterEach(() => {
  scopes.splice(0).forEach(scope => { scope.stop() })
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('真实数字溯源请求围栏', () => {
  it.each(['project', 'year', 'tab'] as const)('%s 切换 ABA 后，旧响应不能重开或回填弹窗', async dimension => {
    const state = createState(), response = deferred<ReturnType<typeof lineage>>()
    mocks.get.mockReturnValueOnce(response.promise)
    const pending = state.trace.onRvCtxCellTrace()
    if (dimension === 'project') { state.project.value = 'synthetic-B'; state.project.value = 'synthetic-A' }
    else if (dimension === 'year') { state.year.value = 2024; state.year.value = 2025 }
    else { state.activeTab.value = 'income_statement'; state.activeTab.value = 'balance_sheet' }
    response.resolve(lineage('旧来源'))
    await pending
    expect(state.trace.rvTraceResult.value).toBeNull()
    expect(state.trace.rvTraceDialogVisible.value).toBe(false)
    expect(state.trace.rvTraceLoading.value).toBe(false)
  })

  it('同上下文逆序请求采用最后一次的冻结行号；旧 finally 不清新 loading', async () => {
    const state = createState(), first = deferred<ReturnType<typeof lineage>>(), second = deferred<ReturnType<typeof lineage>>()
    mocks.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const a = state.trace.onRvCtxCellTrace()
    state.rvCtx.contextMenu.rowData.row_code = 'BS-002'
    const b = state.trace.onRvCtxCellTrace()
    first.resolve(lineage('旧来源'))
    await a
    expect(state.trace.rvTraceLoading.value).toBe(true)
    expect(state.trace.rvTraceResult.value).toBeNull()
    second.resolve(lineage('新来源'))
    await b
    expect(state.trace.rvTraceResult.value).toMatchObject({ objectId: 'BS-002', projectId: 'synthetic-A', upstream: [{ label: '新来源' }] })
    expect(state.trace.rvTraceLoading.value).toBe(false)
    expect(mocks.get).toHaveBeenNthCalledWith(1, '/api/projects/synthetic-A/lineage',
      { params: { object_type: 'report_row', object_id: 'BS-001', direction: 'both' } })
  })

  it('销毁 scope 后拒绝迟到响应，旧上下文错误也不干扰当前弹窗', async () => {
    const state = createState(), response = deferred<ReturnType<typeof lineage>>()
    mocks.get.mockReturnValueOnce(response.promise)
    const pending = state.trace.onRvCtxCellTrace()
    state.scope.stop()
    response.reject(new Error('旧请求失败'))
    await pending
    expect(mocks.handleError).not.toHaveBeenCalled()
    expect(state.trace.rvTraceResult.value).toBeNull()
    expect(state.trace.rvTraceDialogVisible.value).toBe(false)
    expect(state.trace.rvTraceLoading.value).toBe(false)
  })
})

describe('人工审核溯源会话与 CSV 真实入口', () => {
  it('同上下文溯源返回保留原审核，换项目后不能重新打开', () => {
    const state = createState(), original = state.consistencyResult.value
    state.trace.showAuditDialog.value = true
    const location = state.trace.parseTraceLocations(original.checks[0])[0]
    expect(location).toEqual({ label: '利润表', tab: 'income_statement', rowCode: '' })
    state.trace.onTraceJump(location)
    expect(state.trace.isTracing.value).toBe(true)
    expect(state.activeTab.value).toBe('income_statement')
    expect(state.trace.showAuditDialog.value).toBe(false)
    state.trace.onTraceReturn()
    expect(state.trace.showAuditDialog.value).toBe(true)
    expect(state.activeTab.value).toBe('balance_sheet')
    expect(state.consistencyResult.value).toBe(original)
    expect(state.fetchReport).toHaveBeenCalledTimes(2)
    state.trace.onTraceJump(location)
    state.project.value = 'synthetic-B'
    state.project.value = 'synthetic-A'
    state.trace.onTraceReturn()
    expect(state.trace.showAuditDialog.value).toBe(false)
    expect(state.trace.isTracing.value).toBe(false)
  })

  it('替换人工审核结果作废旧溯源会话与选择弹窗', () => {
    const state = createState()
    state.trace.onTraceJump({ label: '利润表', tab: 'income_statement', rowCode: '' })
    state.trace.showTraceSelectDialog.value = true
    state.consistencyResult.value = mapReportConsistencyCheck({ checks: [{ status: 'not_executed' }] })
    state.trace.onTraceReturn()
    expect(state.trace.showAuditDialog.value).toBe(false)
    expect(state.trace.showTraceSelectDialog.value).toBe(false)
    expect(state.trace.traceSelectOptions.value).toEqual([])
    expect(state.trace.isTracing.value).toBe(false)
  })
})

describe('审核报告 CSV 下载入口（全合成，不真实下载）', () => {
  it.each([2025, null])('年度 %s：真实映射、分类过滤和导出保留五态、BOM、0 与缺数', async auditYear => {
    const state = createState()
    state.year.value = auditYear
    state.consistencyResult.value = mapReportConsistencyCheck({ checks: [
      { category: 'balance', name: '不属于当前分类', status: 'passed', expected: 9 },
      { category: 'reasonability', category_label: '合理性', name: '通过, "零值"', status: 'passed', expected: 0, actual: 0, diff: 0 },
      { category: 'reasonability', name: '未通过项', status: 'failed', severity: 'warning', actual: null, reason: '核对, "来源"\n第二行' },
      { category: 'reasonability', name: '未执行项', status: 'not_executed' },
      { category: 'reasonability', name: '不适用项', status: 'not_applicable' },
      { category: 'reasonability', name: '错误项', status: 'running', passed: true, message: '尚未完成' },
    ] })
    state.trace.auditTab.value = 'reasonability'
    const selected = state.trace.filteredAuditChecks.value
    expect(selected).toHaveLength(5)
    const createObjectURL = vi.fn<(blob: NodeBlob) => string>().mockReturnValue('blob:synthetic-report-audit')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('Blob', NodeBlob)
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL = createObjectURL
      static revokeObjectURL = revokeObjectURL
    })
    const downloads: Array<{ href: string; filename: string }> = []
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      downloads.push({ href: this.href, filename: this.download })
    })
    state.trace.onExportAuditExcel()
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    const exported = createObjectURL.mock.calls[0][0]
    expect(exported.type).toBe('text/csv;charset=utf-8')
    // Blob.text() 会消耗 UTF-8 BOM；按字节解码才能验证下载内容确实带 BOM。
    const content = new TextDecoder('utf-8', { ignoreBOM: true }).decode(await exported.arrayBuffer())
    expect(content).toBe('\uFEFF' + reportChecksToCsv(selected))
    expect(content).toContain('"通过, ""零值""","0","0","0"')
    expect(content).toContain('核对, ""来源""\n第二行')
    expect(content).toContain('"—"')
    expect(content).toContain('未知检查状态：running')
    expect(content).not.toContain('不属于当前分类')
    expect(click).toHaveBeenCalledTimes(1)
    expect(downloads).toEqual([{ href: 'blob:synthetic-report-audit',
      filename: `审核报告_资产负债表${auditYear == null ? '' : `_${auditYear}`}.csv` }])
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:synthetic-report-audit')
    expect(mocks.success).toHaveBeenCalledWith('审核报告已导出')
    expect(mocks.get).not.toHaveBeenCalled()
  })

  it('当前分类无明细时只提示，不创建下载内容', () => {
    const state = createState()
    state.trace.auditTab.value = 'synthetic-empty-category'
    const createObjectURL = vi.fn(), revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL = createObjectURL
      static revokeObjectURL = revokeObjectURL
    })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    state.trace.onExportAuditExcel()
    expect(mocks.warning).toHaveBeenCalledWith('无审核数据可导出')
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(revokeObjectURL).not.toHaveBeenCalled()
    expect(click).not.toHaveBeenCalled()
    expect(mocks.success).not.toHaveBeenCalled()
    expect(mocks.get).not.toHaveBeenCalled()
  })
})
