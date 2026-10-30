/**
 * CustomQueryDialog.linkage.spec.ts — 高级查询弹窗改造（advanced-query-linkage-closure 任务 28，design §4.2）
 *
 * - 项目 / 年度（R10.1 / R10.2，AQ-37 / AQ-22）：每次打开以路由项目为准、换路由后跟随；非项目页不自动选项目（原先取
 *   项目列表第一项，变异 B10-b）；年度 = 路由 ?year → 项目审计年度 → 留空要求选择，留空时查询不可用；
 * - 失败（R11.1，AQ-09）：请求带 `_silent`、不带 `validateStatus`（原先 s < 600 把错误体当数据落到「暂无该数据源记录」，
 *   变异 B10-a），结果区显示中文原因与追踪号，不出现「正在重试」；
 * - 翻页与 total（R2.6，AQ-36）、「仅筛选本页」；操作列打开 / 复制引用（不可用时显示原因）、没有回写入口（R7）；
 * - 导出全部走服务端（R8.1）；列名按数据源（R6.6）；金额按列类型格式化；构建器页签按 access 接口；控件 aria-label（N5）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))
const httpMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const downloadMock = vi.hoisted(() => vi.fn())
vi.mock('@/utils/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/http')>()),
  default: httpMocks,
  downloadFile: downloadMock,
}))
const routerMock = vi.hoisted(() => ({
  push: vi.fn(),
  resolve: vi.fn((to: any) => ({ href: `/resolved/${to.name}?${new URLSearchParams(to.query || {}).toString()}` })),
}))
vi.mock('vue-router', () => ({ useRouter: () => routerMock, useRoute: () => ({ params: {}, query: {} }) }))
const projectsMock = vi.hoisted(() => vi.fn())
vi.mock('@/services/commonApi', () => ({ listProjectsWithProgress: (...a: unknown[]) => projectsMock(...a) }))
const accessHolder = vi.hoisted(() => ({ can: true, reason: '' }))
vi.mock('@/composables/useQueryBuilderAccess', async () => {
  const { computed } = await import('vue')
  return {
    useQueryBuilderAccess: () => ({
      canUseBuilder: computed(() => accessHolder.can),
      builderDisabledReason: computed(() => accessHolder.reason),
    }),
  }
})
const builderProps = vi.hoisted(() => ({ value: null as Record<string, unknown> | null }))
vi.mock('@/views/AdvancedQueryBuilder.vue', async () => {
  const { defineComponent: dc, h: hh } = await import('vue')
  return {
    default: dc({
      props: { embedded: Boolean, projectId: String, year: Number },
      setup(p) { builderProps.value = p as Record<string, unknown>; return () => hh('div', { class: 'aqb-stub' }) },
    }),
  }
})
const pickerProps = vi.hoisted(() => ({ value: null as Record<string, unknown> | null }))
vi.mock('@/components/query/SheetCellRangePicker.vue', async () => {
  const { defineComponent: dc, h: hh } = await import('vue')
  return {
    default: dc({
      props: ['modelValue', 'wpCode', 'sheetName', 'projectId', 'year'],
      setup(p) { pickerProps.value = p as Record<string, unknown>; return () => hh('div') },
    }),
  }
})
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() }),
  }
})

import ElementPlus, { ElMessage } from 'element-plus'
import CustomQueryDialog from '../CustomQueryDialog.vue'

const PROJECTS = [
  { id: 'p1', name: '【测试】项目一', audit_year: 2025 },
  { id: 'p2', name: '【测试】项目二', audit_year: 2024 },
  { id: 'p3', name: '【测试】无年度', audit_year: null },
]
const TB_ROWS = [
  { id: 'r1', standard_account_code: '1001', account_name: '库存现金', audited_amount: 100 },
  { id: 'r2', standard_account_code: '1002', account_name: '银行存款', audited_amount: 6473114514.96 },
]
const TB_RESULT = {
  rows: TB_ROWS, columns: ['standard_account_code', 'account_name', 'audited_amount'], total: 812,
  meta: { ref_context: { template_type: 'soe', year: 2025 },
    column_types: { standard_account_code: 'text', account_name: 'text', audited_amount: 'number' } },
}
const executeHolder: { value: unknown } = { value: TB_RESULT }
const validateHolder: { issues: unknown[] } = { issues: [] }

function axiosError(status: number, detail: unknown, headers: Record<string, string> = {}) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true, response: { status, data: { code: status, message: detail, detail }, headers },
  })
}

let wrapper: VueWrapper<any> | null = null
async function mountDialog(props: Record<string, unknown> = {}): Promise<VueWrapper<any>> {
  wrapper = mount(CustomQueryDialog, {
    props: { modelValue: true, projectId: 'p1', year: 2025, ...props },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  }) as unknown as VueWrapper<any>
  await flushPromises()
  return wrapper
}
const $ = (sel: string) => document.body.querySelector(sel) as HTMLElement | null
const $$ = (sel: string) => Array.from(document.body.querySelectorAll(sel)) as HTMLElement[]
const executeCalls = () => apiMocks.post.mock.calls.filter((c) => c[0] === '/api/custom-query/execute')

async function run(w: VueWrapper<any>, source = 'tb_detail') {
  w.vm.selectedSource = source
  await flushPromises()
  await w.vm.executeQuery()
  await flushPromises()
}

let openSpy: any
const clipboard = { writeText: vi.fn().mockResolvedValue(undefined), write: vi.fn() }
beforeEach(() => {
  sessionStorage.clear()
  apiMocks.get.mockReset().mockResolvedValue({ project_ids: [] })
  apiMocks.post.mockReset().mockImplementation((url: string, _body?: unknown, config?: any) => {
    if (url === '/api/custom-query/execute') {
      const value = executeHolder.value
      if (!(value instanceof Error)) return Promise.resolve(value)
      const response = (value as { response?: { status?: number; data?: unknown } }).response
      // 与 axios 同口径：validateStatus 放行的状态码按成功返回、错误体当数据（改造前弹窗正是这样落到「暂无该数据源记录」）
      if (typeof config?.validateStatus === 'function' && config.validateStatus(response?.status)) {
        return Promise.resolve(response?.data)
      }
      return Promise.reject(value)
    }
    if (url === '/api/address-registry/validate') return Promise.resolve({ issues: validateHolder.issues })
    return Promise.resolve({})
  })
  httpMocks.get.mockReset().mockResolvedValue({ data: [], headers: {} })
  downloadMock.mockReset().mockResolvedValue({})
  projectsMock.mockReset().mockResolvedValue(PROJECTS)
  routerMock.resolve.mockClear()
  ;(ElMessage as any).warning.mockClear()
  ;(ElMessage as any).success.mockClear()
  executeHolder.value = TB_RESULT
  validateHolder.issues = []
  accessHolder.can = true
  accessHolder.reason = ''
  builderProps.value = null
  pickerProps.value = null
  clipboard.writeText.mockClear()
  Object.defineProperty(navigator, 'clipboard', { value: clipboard, configurable: true })
  openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  openSpy.mockRestore()
  document.body.innerHTML = ''
})

describe('项目与年度（R10.1 / R10.2）', () => {
  it('非项目页打开：不自动选中任何项目、年度留空并要求选择（原先取项目列表第一项）', async () => {
    const w = await mountDialog({ projectId: '', year: null })
    expect(w.vm.localProjectId).toBe('')
    expect(w.vm.localYear).toBeNull()
    expect($('[data-testid="cq-year-hint"]')?.textContent).toContain('请选择审计年度')
  })

  it('路由项目变了：项目跟随，年度取新项目的审计年度', async () => {
    const w = await mountDialog({ projectId: 'p1', year: 2025 })
    expect([w.vm.localProjectId, w.vm.localYear]).toEqual(['p1', 2025])
    await w.setProps({ projectId: 'p2', year: null })
    await flushPromises()
    expect([w.vm.localProjectId, w.vm.localYear]).toEqual(['p2', 2024])
  })

  it('项目没有审计年度：查询按钮不可用、提示选择年度，不发查询', async () => {
    const w = await mountDialog({ projectId: 'p3', year: null })
    expect(w.vm.localYear).toBeNull()
    expect($('[data-testid="cq-run"]')?.hasAttribute('disabled')).toBe(true)
    expect(w.vm.queryBlockedReason).toBe('请选择审计年度')
    await w.vm.executeQuery()
    expect(executeCalls()).toHaveLength(0)
    expect((ElMessage as any).warning).toHaveBeenCalledWith(expect.stringContaining('请选择审计年度'))
  })

  it('底稿选区器的年度由弹窗传入（未选年度时为空）', async () => {
    const w = await mountDialog({ projectId: 'p1', year: 2025 })
    expect(pickerProps.value?.year).toBe(2025)
    w.vm.localYear = null
    await flushPromises()
    expect(pickerProps.value?.year).toBeNull()
  })
})

describe('查询失败不落空态（R11.1，AQ-09）', () => {
  const cases: [string, unknown, string][] = [
    ['500 带追踪号', axiosError(500, { error_code: 'INTERNAL_ERROR', message: '查询执行失败，请稍后重试', correlation_id: 'c0ffee12' },
      { 'x-correlation-id': 'c0ffee12' }), '查询执行失败，请稍后重试'],
    ['400 中文原因', axiosError(400, { error_code: 'AUX_FILTER_REQUIRED', message: '辅助明细请先按科目或辅助类型筛选' }),
      '辅助明细请先按科目或辅助类型筛选'],
    ['422 参数校验', axiosError(422, [{ type: 'greater_than_equal', loc: ['body', 'limit'], msg: 'x', ctx: { ge: 1 } }]),
      '参数校验失败：每页行数不能小于 1'],
    ['429 导出忙', axiosError(429, { error_code: 'EXPORT_BUSY', message: '已有导出在进行，请稍后再试' }), '已有导出在进行，请稍后再试'],
  ]
  it.each(cases)('%s：结果区显示中文原因，不显示「暂无该数据源记录」、不出现「正在重试」', async (_name, err, text) => {
    executeHolder.value = err
    const w = await mountDialog()
    await run(w)
    const alert = $('[data-testid="cq-query-error"]')
    expect(alert, '应显示失败提示').not.toBeNull()
    expect($('[data-testid="cq-query-error-message"]')?.textContent).toContain(text)
    expect(document.body.textContent).not.toContain('暂无该数据源记录')
    expect((ElMessage as any).warning.mock.calls.flat().join('')).not.toContain('正在重试')
    // 请求自管错误：带 _silent、不带 validateStatus（原先 s < 600 把错误体当数据）
    const config = executeCalls()[0][2]
    expect(config).toMatchObject({ _silent: true })
    expect(config).not.toHaveProperty('validateStatus')
  })

  it('500 的追踪号可复制', async () => {
    executeHolder.value = cases[0][1]
    const w = await mountDialog()
    await run(w)
    expect($('[data-testid="cq-query-error"]')?.textContent).toContain('c0ffee12')
    $('[aria-label="复制追踪号"]')!.click()
    await flushPromises()
    expect(clipboard.writeText).toHaveBeenCalledWith('c0ffee12')
  })
})

describe('翻页、total 与「仅筛选本页」（R2.6）', () => {
  it('显示后端 total，翻页按 offset 重新查询（每页 100 行）', async () => {
    const w = await mountDialog()
    await run(w)
    expect($('[data-testid="cq-footer"]')?.textContent).toContain('共 812 行')
    expect($('[aria-label="查询结果翻页"]')).not.toBeNull()
    expect(executeCalls()[0][1]).toMatchObject({ limit: 100, offset: 0, year: 2025, project_id: 'p1', source: 'tb_detail' })
    w.vm.page = 3
    w.vm.onPageChange()
    await flushPromises()
    expect(executeCalls()[1][1]).toMatchObject({ limit: 100, offset: 200 })
    expect(w.vm.page).toBe(3)
  })

  it('本地文字筛选只筛本页、不重新查询，占位写明「仅筛选本页」', async () => {
    const w = await mountDialog()
    await run(w)
    expect(($('input[placeholder="仅筛选本页"]') as HTMLInputElement | null)).not.toBeNull()
    w.vm.filterText = '银行'
    await flushPromises()
    expect(w.vm.filteredRows.map((r: any) => r.standard_account_code)).toEqual(['1002'])
    expect(executeCalls()).toHaveLength(1)
    expect($('[data-testid="cq-footer"]')?.textContent).toContain('仅筛选本页：1 行')
  })
})

describe('排序（R2.2）', () => {
  it('点表头排序：请求带 sort 并回到第 1 页；导出全部与保存模板带同一排序；换数据源即清除', async () => {
    const w = await mountDialog()
    await run(w)
    w.vm.page = 3
    const th = $$('.el-table__header th').find((el) => el.textContent?.includes('审定数'))
    expect(th, '审定数列可排序').toBeTruthy()
    ;(th!.querySelector('.sort-caret.descending') as HTMLElement).click()
    await flushPromises()
    expect(executeCalls()).toHaveLength(2)
    expect(executeCalls()[1][1]).toMatchObject({ sort: [{ field: 'audited_amount', direction: 'desc' }], offset: 0 })
    expect(w.vm.page).toBe(1)
    await w.vm.exportAll()
    expect(downloadMock.mock.calls[0][1].data.sort).toEqual([{ field: 'audited_amount', direction: 'desc' }])
    expect(w.vm.templateConfig).toMatchObject({ sort_field: 'audited_amount', sort_order: 'desc' })
    w.vm.selectedSource = 'account_balance'
    await flushPromises()
    expect(w.vm.sortState).toBeNull()
    await w.vm.executeQuery()
    await flushPromises()
    expect(executeCalls().at(-1)![1]).not.toHaveProperty('sort')
  })
})

describe('操作列（R7.1~R7.3、R7.5、N5）', () => {
  it('「打开」新标签落到账簿查询；「复制引用」按整页校验结果可用 / 不可用并给原因', async () => {
    validateHolder.issues = [{ ref: "TB('1002','审定数')", status: 'not_found', message: '科目 1002 在本项目试算表中不存在' }]
    const w = await mountDialog()
    await run(w)
    const validate = apiMocks.post.mock.calls.filter((c) => c[0] === '/api/address-registry/validate')
    expect(validate).toHaveLength(1)
    expect(validate[0][1]).toMatchObject({ formula: "TB('1001','审定数')+TB('1002','审定数')", project_id: 'p1', year: 2025,
      template_type: 'soe' })
    const copies = $$('[data-testid="cq-row-copy-ref"]')
    expect(copies).toHaveLength(2)
    expect(copies.map((b) => b.hasAttribute('disabled'))).toEqual([false, true])
    expect(w.vm.rowLinks.refHint(TB_ROWS[1])).toBe('科目 1002 在本项目试算表中不存在')
    copies[0].click()
    await flushPromises()
    expect(clipboard.writeText).toHaveBeenCalledWith("TB('1001','审定数')")
    const open = $$('[data-testid="cq-row-open"]')
    expect(open[0].getAttribute('aria-label')).toBe('在账簿查询中打开')
    open[0].click()
    await flushPromises()
    expect(openSpy).toHaveBeenCalledWith(expect.stringContaining('/resolved/LedgerPenetration'), '_blank')
  })

  it('结果区没有回写入口；操作、翻页、导出控件都有 aria-label', async () => {
    const w = await mountDialog()
    await run(w)
    const text = $('.gt-cq-main')?.textContent ?? ''
    expect(text).not.toMatch(/回写|写回/)
    expect(apiMocks.post.mock.calls.some((c) => String(c[0]).includes('writeback'))).toBe(false)
    expect($('[aria-label="导出查询结果"]')).not.toBeNull()
    expect($('[aria-label="查询结果翻页"]')).not.toBeNull()
    expect($$('[data-testid="cq-row-copy-ref"]')[0].getAttribute('aria-label')).toBe("复制引用 TB('1001','审定数')")
    expect(w.vm.resultColumns).toEqual(['standard_account_code', 'account_name', 'audited_amount'])
  })
})

describe('列名与金额格式（R6.6）', () => {
  it('合并试算的 summary 列显示「汇总数」', async () => {
    executeHolder.value = { rows: [{ company_name: '甲', summary: 1 }], columns: ['company_name', 'summary'], total: 1 }
    const w = await mountDialog()
    await run(w, 'ws_consol_tb')
    const headers = $$('.el-table__header th').map((th) => th.textContent?.trim())
    expect(headers).toContain('汇总数')
    expect(headers).not.toContain('摘要')
  })

  it('金额按列类型格式化：十亿级带两位小数的金额加千分位；文本列的长数字编码原样', async () => {
    executeHolder.value = {
      rows: [{ account_code: '100200300400', closing_balance: 6473114514.96 }],
      columns: ['account_code', 'closing_balance'], total: 1,
      meta: { column_types: { account_code: 'text', closing_balance: 'number' } },
    }
    const w = await mountDialog()
    await run(w, 'account_balance')
    const cells = $$('.el-table__body td').map((td) => td.textContent?.trim())
    expect(cells).toContain('6,473,114,514.96')
    expect(cells).toContain('100200300400')
    expect(w.vm.formatCell('6222021234567890123', 'value')).toBe('6222021234567890123')
  })
})

describe('导出与构建器', () => {
  it('「导出全部」走服务端：带当前查询与中文表头，不带翻页', async () => {
    const w = await mountDialog()
    await run(w)
    await w.vm.exportAll()
    expect(downloadMock).toHaveBeenCalledTimes(1)
    const [url, opts] = downloadMock.mock.calls[0]
    expect(url).toBe('/api/custom-query/export')
    expect(opts).toMatchObject({ method: 'post', silent: true })
    expect(opts.data).toMatchObject({ project_id: 'p1', year: 2025, source: 'tb_detail',
      headers: { standard_account_code: '标准科目编码', account_name: '科目名称', audited_amount: '审定数' } })
    expect(opts.data).not.toHaveProperty('limit')
    expect(opts.data).not.toHaveProperty('offset')
  })

  it('构建器页签按 access 接口：不可用时置灰并给原因；可用时把当前项目与年度传给构建器', async () => {
    accessHolder.can = false
    accessHolder.reason = '高级构建器仅限管理员、合伙人、经理（含任一项目的项目经理）使用'
    await mountDialog()
    const tab = $$('.el-tabs__item').find((el) => el.textContent?.includes('高级构建器'))
    expect(tab?.classList.contains('is-disabled')).toBe(true)
    wrapper!.unmount()
    wrapper = null
    document.body.innerHTML = ''
    accessHolder.can = true
    await mountDialog({ initialTab: 'advanced' })
    expect(builderProps.value).toMatchObject({ embedded: true, projectId: 'p1', year: 2025 })
  })

  it('💾 打开三档保存对话框，配置带当前项目、年度与数据源', async () => {
    const w = await mountDialog()
    w.vm.selectedSource = 'tb_detail'
    await flushPromises()
    w.vm.openSaveDialog()
    await flushPromises()
    expect(w.vm.saveDialogVisible).toBe(true)
    expect(w.vm.templateConfig).toMatchObject({ project_id: 'p1', year: 2025, source: 'tb_detail' })
    expect(apiMocks.get).toHaveBeenCalledWith('/api/custom-query/template-share-targets', expect.anything())
  })
})

