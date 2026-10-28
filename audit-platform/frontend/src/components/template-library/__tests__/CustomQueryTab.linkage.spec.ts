/**
 * CustomQueryTab.linkage.spec.ts — 高级查询页面版改造（advanced-query-linkage-closure 任务 29，design §4.2）
 *
 * - 条件以结构化 conditions + condition_logic 发送（原先拼成 `{字段}_min` 之类的筛选键，后端不认、条件全被忽略；变异 B10-c）；
 *   后端拒绝（未知字段等）在结果区显示中文原因；不支持条件的数据源禁用条件区并说明原因；字段显示中文列名；
 * - 选了 ACNR 格时请求里仍带 acnr_targets（面板与字段归 acnr D1，用户裁决 Q0，本 spec 不改面板）；
 * - 指标树带项目与年度加载「骨架 + 附注分支」（不拉不带项目的全量树），缓存命中时不再拉分支（R10.4）；
 * - 保存为模板三档：可分享项目取 template-share-targets（AQ-39）；有可编辑项目时三档可选，没有时只能存私有；
 * - 导出全部走服务端；构建器准入说法与 access 接口同口径，内嵌构建器拿到当前项目与年度（B9 浏览器复测交接）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, mount, flushPromises, type VueWrapper } from '@vue/test-utils'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), delete: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))
const httpMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
const downloadMock = vi.hoisted(() => vi.fn())
vi.mock('@/utils/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/http')>()),
  default: httpMocks,
  downloadFile: downloadMock,
}))
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({ buildAddressTree: vi.fn(), loadCellNodes: vi.fn(), resolveIndex: vi.fn(), clearCache: vi.fn() }),
}))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), resolve: (to: any) => ({ href: `/resolved/${to.name}` }) }),
  useRoute: () => ({ params: {}, query: {} }),
}))
vi.mock('@/composables/usePermissionMatrix', () => ({ usePermissionMatrix: () => ({ currentRole: { value: 'auditor' } }) }))
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() }),
    ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
  }
})

import ElementPlus from 'element-plus'
import CustomQueryTab from '@/components/template-library/CustomQueryTab.vue'
import QueryConditionEditor from '@/components/query/QueryConditionEditor.vue'
import QueryResultPager from '@/components/query/QueryResultPager.vue'
import QueryTemplateSaveDialog from '@/components/query/QueryTemplateSaveDialog.vue'
import AdvancedQueryBuilder from '@/views/AdvancedQueryBuilder.vue'

const PID = '5942c12e-65fb-4187-ace3-79d45a90cb53'
const SKELETON = [
  { key: 'trial_balance', label: '📑 试算平衡表', children: [
    { key: 'ledger_entries', label: '序时账明细', columns: ['voucher_date', 'voucher_no', 'account_code', 'debit_amount', 'summary'],
      supports_conditions: true },
  ] },
  { key: 'disclosure', label: '📝 附注（国企）', lazy: true, children: [] },
  { key: 'workpaper', label: '📋 底稿', lazy: true, children: [
    { key: 'workpaper', label: '底稿清单', columns: ['wp_code', 'wp_name'], supports_conditions: true },
  ] },
]
const DISCLOSURE_BRANCH = [
  { key: 'disclosure', label: '附注目录', columns: [], supports_conditions: false },
  { key: 'note_group_八', label: '财务报表主要项目注释', children: [
    { key: 'disclosure_note:八、1', label: '八、1 货币资金', columns: [], supports_conditions: false },
  ] },
]
const LEDGER_RESULT = {
  rows: [{ id: 'l1', voucher_date: '2025-01-02', voucher_no: '记-1', account_code: '1002', debit_amount: 241944666.92, summary: '收款' }],
  columns: ['voucher_date', 'voucher_no', 'account_code', 'debit_amount', 'summary'],
  total: 1,
  meta: { ref_context: { template_type: 'soe', year: 2025 }, column_types: { debit_amount: 'number', summary: 'text' } },
}
const executeHolder: { value: unknown } = { value: LEDGER_RESULT }
const shareHolder: { ids: string[] } = { ids: [] }

function indicatorsResponse(config: any) {
  const params = config?.params ?? {}
  if (params.branch === 'disclosure') return { data: DISCLOSURE_BRANCH, headers: {} }
  if (params.depth === 1) {
    return { data: JSON.parse(JSON.stringify(SKELETON)),
      headers: { 'x-indicators-schema-version': '14', 'x-notes-version': 'nv-1' } }
  }
  return { data: [], headers: {} }
}

async function mountTab(): Promise<VueWrapper<any>> {
  const wrapper = shallowMount(CustomQueryTab, {
    global: {
      directives: { loading: {} },
      stubs: {
        // 对话框渲染插槽（看得到内嵌构建器）；表格列桩掉（浅挂载下作用域插槽会以 undefined 调用）
        'el-dialog': { template: '<div class="el-dialog-stub"><slot /></div>' },
        // 结果表桩：看得到 default-sort，能发 sort-change（排序用例）
        'el-table': { name: 'ElTable', props: ['data', 'defaultSort'], emits: ['sort-change'],
          template: '<div class="el-table-stub"><slot /></div>' },
        'el-table-column': true,
        'el-row': { template: '<div><slot /></div>' },
        'el-col': { template: '<div><slot /></div>' },
        'el-alert': { template: '<div class="el-alert-stub"><slot name="title" /><slot /></div>' },
        QueryErrorAlert: false,
      },
    },
  }) as unknown as VueWrapper<any>
  await flushPromises()
  return wrapper
}

function axiosError(status: number, detail: unknown) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true, response: { status, data: { code: status, message: detail, detail }, headers: {} },
  })
}

const executeBodies = () => apiMocks.post.mock.calls.filter((c) => c[0] === '/api/custom-query/execute').map((c) => c[1])

async function selectLedger(wrapper: VueWrapper<any>) {
  wrapper.vm.formCtx.project_id = PID
  wrapper.vm.formCtx.year = 2025
  await flushPromises()
  wrapper.vm.formCtx.source = 'ledger_entries'
  wrapper.vm.onSourceChange()
  await flushPromises()
}

beforeEach(() => {
  sessionStorage.clear()
  vi.clearAllMocks()
  apiMocks.get.mockReset().mockImplementation((url: string) => {
    if (url === '/api/custom-query/template-share-targets') return Promise.resolve({ project_ids: shareHolder.ids })
    if (String(url).includes('/api/projects')) return Promise.resolve([{ id: PID, name: '【测试】和平药房', audit_year: 2025 }])
    return Promise.resolve([])
  })
  apiMocks.post.mockReset().mockImplementation((url: string) => {
    if (url === '/api/custom-query/execute') {
      return executeHolder.value instanceof Error ? Promise.reject(executeHolder.value) : Promise.resolve(executeHolder.value)
    }
    if (url === '/api/address-registry/validate') return Promise.resolve({ issues: [] })
    return Promise.resolve({})
  })
  httpMocks.get.mockReset().mockImplementation((_url: string, config: any) => Promise.resolve(indicatorsResponse(config)))
  downloadMock.mockReset().mockResolvedValue({})
  executeHolder.value = LEDGER_RESULT
  shareHolder.ids = []
})

describe('结构化条件（R6.1、R6.2）', () => {
  it('条件与 AND / OR 进请求体（不再拼 {字段}_min 筛选键），所选列随请求发送', async () => {
    const wrapper = await mountTab()
    await selectLedger(wrapper)
    wrapper.vm.conditionState = {
      conditions: [{ field: 'debit_amount', op: 'gt', value: '100000000' }, { field: 'summary', op: 'like', value: '冲销' }],
      logic: 'or',
    }
    wrapper.vm.selectedColumns = ['voucher_no', 'debit_amount']
    await wrapper.vm.onExecute()
    await flushPromises()
    const [body] = executeBodies()
    expect(body.conditions).toEqual([
      { field: 'debit_amount', op: 'gt', value: '100000000' }, { field: 'summary', op: 'like', value: '冲销' }])
    expect(body.condition_logic).toBe('or')
    expect(body.columns).toEqual(['voucher_no', 'debit_amount'])
    expect(Object.keys(body.filters)).toEqual([])
    expect(JSON.stringify(body)).not.toMatch(/_min|_max|_from|_to|__is_null/)
    // 调用方自管错误提示：带 _silent（确定性错误不经全局拦截器自动重试）
    const config = apiMocks.post.mock.calls.find((c) => c[0] === '/api/custom-query/execute')?.[2]
    expect(config).toMatchObject({ _silent: true })
    expect(config).not.toHaveProperty('validateStatus')
  })

  it('条件没填完整：执行不可用并说明原因，不发请求', async () => {
    const wrapper = await mountTab()
    await selectLedger(wrapper)
    wrapper.vm.conditionState = { conditions: [{ field: 'debit_amount', op: 'gt', value: '' }], logic: 'and' }
    await flushPromises()
    expect(wrapper.vm.executeBlockedReason).toBe('条件「借方发生额」未填写值')
    await wrapper.vm.onExecute()
    expect(executeBodies()).toHaveLength(0)
  })

  it('后端拒绝（未登记的条件字段）：结果区显示中文原因', async () => {
    executeHolder.value = axiosError(400, { error_code: 'UNKNOWN_CONDITION_FIELD',
      message: '条件字段「foo」不存在，可用：凭证日期、凭证号、科目编码、借方发生额、摘要' })
    const wrapper = await mountTab()
    await selectLedger(wrapper)
    wrapper.vm.conditionState = { conditions: [{ field: 'foo', op: 'eq', value: '1' }], logic: 'and' }
    await wrapper.vm.onExecute()
    await flushPromises()
    const text = wrapper.find('.gt-cqt-result-body').text()
    expect(text).toContain('查询失败')
    expect(text).toContain('条件字段「foo」不存在')
  })

  it('条件编辑器拿到当前数据源的字段与中文列名；不支持条件的数据源禁用并说明原因', async () => {
    const wrapper = await mountTab()
    await selectLedger(wrapper)
    const editor = wrapper.findComponent(QueryConditionEditor)
    expect(editor.props('fields')).toEqual(['voucher_date', 'voucher_no', 'account_code', 'debit_amount', 'summary'])
    expect(editor.props('source')).toBe('ledger_entries')
    expect(editor.props('disabled')).toBe(false)
    expect(wrapper.vm.columnLabel('debit_amount')).toBe('借方发生额')
    wrapper.vm.formCtx.source = 'disclosure_note:八、1'
    wrapper.vm.onSourceChange()
    await flushPromises()
    expect(editor.props('disabled')).toBe(true)
    expect(editor.props('disabledReason')).toContain('不支持条件筛选')
  })

  it('选了 ACNR 格时请求里仍带 acnr_targets（R6.5，归 acnr D1）', async () => {
    const wrapper = await mountTab()
    await selectLedger(wrapper)
    wrapper.vm.acnrFieldIds = ['E1/E1-14/C10']
    await wrapper.vm.onExecute()
    await flushPromises()
    expect(executeBodies()[0].acnr_targets).toEqual(['E1/E1-14/C10'])
  })
})

describe('指标树：带项目与年度加载「骨架 + 附注分支」（R10.4）', () => {
  it('不拉全量树；拍平后附注分支有章节，底稿组只留「底稿清单」', async () => {
    const wrapper = await mountTab()
    await selectLedger(wrapper)
    const calls = httpMocks.get.mock.calls.map((c) => c[1]?.params ?? {})
    const latest = calls.filter((p) => p.project_id === PID && p.year === 2025)
    expect(latest.some((p) => p.depth === 1), '应按项目年度拉骨架').toBe(true)
    expect(latest.some((p) => p.branch === 'disclosure'), '应按项目年度拉附注分支').toBe(true)
    expect(calls.some((p) => p.depth === undefined && p.branch === undefined), '不应拉全量树').toBe(false)
    const groups = wrapper.vm.indicatorTree.map((g: any) => [g.key, g.children.map((c: any) => c.label)])
    expect(groups).toEqual([
      ['trial_balance', ['序时账明细']],
      ['disclosure', ['附注目录', '财务报表主要项目注释 / 八、1 货币资金']],
      ['workpaper', ['底稿清单']],
    ])
  })

  it('同一项目年度、附注版本不变：再次加载命中缓存，不再拉附注分支', async () => {
    const wrapper = await mountTab()
    await selectLedger(wrapper)
    httpMocks.get.mockClear()
    await wrapper.vm.loadIndicators()
    const params = httpMocks.get.mock.calls.map((c) => c[1]?.params ?? {})
    expect(params).toEqual([{ project_id: PID, year: 2025, depth: 1 }])
  })
})

describe('结果、导出与入口', () => {
  it('附注表格行可复制 NOTE 引用（行标签 = 表头第一列，取值列 = 第二列）', async () => {
    executeHolder.value = {
      rows: [{ note_section: '八、1', section_title: '货币资金', table_name: '货币资金', 项目: '库存现金', 期末余额: 100, 期初余额: 50 }],
      columns: ['note_section', 'section_title', 'table_name', '项目', '期末余额', '期初余额'], total: 1,
      meta: { tables: [{ index: 0, name: '货币资金', row_count: 6 }], table_index: 0 },
    }
    const wrapper = await mountTab()
    await selectLedger(wrapper)
    wrapper.vm.formCtx.source = 'disclosure_note:八、1'
    wrapper.vm.onSourceChange()
    await wrapper.vm.onExecute()
    await flushPromises()
    expect(wrapper.vm.rowLinks.refOf(wrapper.vm.result.rows[0])).toBe("NOTE('八、1','库存现金','期末余额')")
    const validate = apiMocks.post.mock.calls.filter((c) => c[0] === '/api/address-registry/validate')
    expect(validate[0][1]).toMatchObject({ formula: "NOTE('八、1','库存现金','期末余额')", project_id: PID, year: 2025 })
  })

  it('「导出全部」按本次查询（含条件）服务端导出，表头为中文列名', async () => {
    const wrapper = await mountTab()
    await selectLedger(wrapper)
    wrapper.vm.conditionState = { conditions: [{ field: 'debit_amount', op: 'gt', value: '100000000' }], logic: 'and' }
    await wrapper.vm.onExecute()
    await flushPromises()
    await wrapper.vm.onExportAll()
    const [url, opts] = downloadMock.mock.calls[0]
    expect(url).toBe('/api/custom-query/export')
    expect(opts.data).toMatchObject({ project_id: PID, year: 2025, source: 'ledger_entries',
      conditions: [{ field: 'debit_amount', op: 'gt', value: '100000000' }], condition_logic: 'and' })
    expect(opts.data.headers).toMatchObject({ debit_amount: '借方发生额', summary: '摘要' })
    expect(opts.data).not.toHaveProperty('offset')
    // N5（与弹窗、构建器同口径）：导出按钮带 aria-label；翻页与行操作是与弹窗共用的组件（其 aria-label 在弹窗用例里全量挂载断言）
    expect(wrapper.find('[aria-label="导出查询结果"]').exists()).toBe(true)
    expect(wrapper.findComponent(QueryResultPager).exists()).toBe(true)
    expect(wrapper.find('[aria-label="执行查询"]').exists()).toBe(true)
  })

  it('点表头排序（R2.2）：请求带 sort 并回到第 1 页，导出全部与保存模板带同一排序；换数据源即清除', async () => {
    const wrapper = await mountTab()
    await selectLedger(wrapper)
    await wrapper.vm.onExecute()
    await flushPromises()
    wrapper.vm.page = 4
    // 表格发出的 sort-change 接到查询上（不是只排本页）
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('sort-change', { prop: 'debit_amount', order: 'descending' })
    await flushPromises()
    const bodies = executeBodies()
    expect(bodies).toHaveLength(2)
    expect(bodies[1]).toMatchObject({ sort: [{ field: 'debit_amount', direction: 'desc' }], offset: 0 })
    expect(wrapper.vm.page).toBe(1)
    // 结果到了表格重新挂载：排序箭头照样显示（default-sort）
    expect(wrapper.findComponent({ name: 'ElTable' }).props('defaultSort')).toEqual({ prop: 'debit_amount', order: 'descending' })
    await wrapper.vm.onExportAll()
    expect(downloadMock.mock.calls[0][1].data.sort).toEqual([{ field: 'debit_amount', direction: 'desc' }])
    expect(wrapper.vm.templateConfig).toMatchObject({ sort_field: 'debit_amount', sort_order: 'desc' })
    wrapper.vm.formCtx.source = 'workpaper'
    wrapper.vm.onSourceChange()
    expect(wrapper.vm.sortState).toBeNull()
    expect(wrapper.vm.templateConfig).not.toHaveProperty('sort_field')
  })

  it('构建器准入说法与 access 接口同口径；内嵌构建器拿到当前项目与年度', async () => {
    const wrapper = await mountTab()
    expect(wrapper.find('.gt-cqt-guidance-body').text()).toContain('管理员、合伙人、经理（含任一项目的项目经理）')
    await selectLedger(wrapper)
    const builder = wrapper.findComponent(AdvancedQueryBuilder)
    expect(builder.props()).toMatchObject({ embedded: true, projectId: PID, year: 2025 })
  })
})

describe('保存为模板三档（AQ-39，R9.1）', () => {
  async function mountSave(ids: string[]) {
    shareHolder.ids = ids
    const wrapper = mount(QueryTemplateSaveDialog, {
      props: { modelValue: true, dataSource: 'ledger_entries', config: { source: 'ledger_entries', year: 2025 },
        projects: [{ id: PID, name: '【测试】和平药房' }] },
      global: { plugins: [ElementPlus] },
      attachTo: document.body,
    })
    await flushPromises()
    return wrapper
  }
  const radio = (scope: string) => document.body.querySelector(`[data-testid="cq-save-scope-${scope}"] input`) as HTMLInputElement

  it('有可编辑项目：三档都可选，按所选项目共享保存', async () => {
    const wrapper = await mountSave([PID])
    expect(['private', 'project', 'public'].map((s) => radio(s).disabled)).toEqual([false, false, false])
    ;(wrapper.vm as any).form.name = '【测试】大额凭证'
    ;(wrapper.vm as any).form.scope = 'project'
    ;(wrapper.vm as any).form.shared_project_ids = [PID]
    await (wrapper.vm as any).onConfirmSaveTemplate()
    const save = apiMocks.post.mock.calls.find((c) => c[0] === '/api/custom-query/templates')
    expect(save?.[1]).toMatchObject({ scope: 'project', shared_project_ids: [PID], data_source: 'ledger_entries' })
    wrapper.unmount()
    document.body.innerHTML = ''
  })

  it('没有可编辑项目：只能存「仅我可见」，并说明原因', async () => {
    const wrapper = await mountSave([])
    expect(['private', 'project', 'public'].map((s) => radio(s).disabled)).toEqual([false, true, true])
    expect(document.body.querySelector('[data-testid="cq-save-share-hint"]')?.textContent)
      .toContain('当前没有可编辑的项目，仅可保存为「仅我可见」')
    wrapper.unmount()
    document.body.innerHTML = ''
  })
})
