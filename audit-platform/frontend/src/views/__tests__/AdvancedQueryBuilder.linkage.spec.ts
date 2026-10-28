/**
 * AdvancedQueryBuilder.linkage.spec.ts — 构建器前端联动（advanced-query-linkage-closure 任务 30）
 *
 * - 准入判据只取 `GET /api/query/access`：无权 / 作用域为空时禁用并显示接口原因；接口取不到时保持不可用、不回落到
 *   任何前端角色清单（变异 B9-c）；
 * - 在项目里打开默认限定当前项目与审计年度、「跨项目」开关（计数 > 1 或 all_projects 才出现，R3.5）；
 * - 翻页发 offset、显示全量 total（R2.6，变异 B9-d）；导出带中文表头（R8.1）；选了 ACNR 格时请求仍带 acnr_targets（R6.5）；
 * - 失败在结果区显示后端原因与追踪号（R11.1 / AQ-29）；单项目结果逐行「打开」与「复制引用」（R7.1~R7.3）；
 * - 操作、翻页、导出控件带 aria-label（N5）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))
const httpMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/utils/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/http')>()),
  default: httpMocks,
}))
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({ resolveIndex: vi.fn(), buildAddressTree: vi.fn(), loadCellNodes: vi.fn(), clearCache: vi.fn() }),
}))
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() }),
    ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
  }
})
const routeHolder = vi.hoisted(() => ({ params: {} as Record<string, string>, query: {} as Record<string, string>, path: '/x' }))
const routerMock = vi.hoisted(() => ({ resolve: vi.fn((to: any) => ({ href: `/resolved/${to.name}` })) }))
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => routeHolder,
  useRouter: () => routerMock,
}))

import ElementPlus, { ElMessage } from 'element-plus'
import AdvancedQueryBuilder from '@/views/AdvancedQueryBuilder.vue'
import { ACCESS_UNAVAILABLE_REASON, resetQueryBuilderAccessCache } from '@/composables/useQueryBuilderAccess'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'

const PID = '005a6f2d-cecd-4e30-bcbd-9fb01236c194'
const FORBIDDEN = '高级构建器仅限管理员、合伙人、经理（含任一项目的项目经理）使用'
const ACCESS = {
  all: { allowed: true, basis: 'system_role', reason: null, all_projects: true, accessible_project_count: null },
  one: { allowed: true, basis: 'project_manager', reason: null, all_projects: false, accessible_project_count: 1 },
  two: { allowed: true, basis: 'project_manager', reason: null, all_projects: false, accessible_project_count: 2 },
  denied: { allowed: false, basis: null, reason: FORBIDDEN, all_projects: false, accessible_project_count: 0 },
  empty: { allowed: true, basis: 'system_role', reason: '您当前没有可访问的项目', all_projects: false, accessible_project_count: 0 },
}
const SCHEMA = {
  tables: [
    { name: 'trial_balance', label: '试算表', fields: ['standard_account_code', 'account_name', 'audited_amount', 'year'] },
    { name: 'tb_ledger', label: '序时账', fields: ['voucher_date', 'voucher_no', 'account_code', 'debit_amount'] },
  ],
  operators: ['eq', 'gt', 'between'],
  aggregates: ['count', 'sum'],
}
const accessHolder: { value: unknown } = { value: ACCESS.all }

function tbResult(extra: Record<string, unknown> = {}) {
  return {
    rows: [{ standard_account_code: '1001', account_name: '库存现金', audited_amount: '100.00' },
      { standard_account_code: '1002', account_name: '银行存款', audited_amount: '200.00' }],
    columns: ['standard_account_code', 'account_name', 'audited_amount'],
    total: 2, table: 'trial_balance', sql: 'SELECT …',
    formula_refs: ["TB('1001','审定数')", "TB('1002','审定数')"],
    scope: { all_projects: false, project_count: 1, unscoped_tables: [], requested_project_id: PID },
    warnings: [],
    ...extra,
  }
}

function axiosError(status: number, detail: unknown, headers: Record<string, string> = {}) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    isAxiosError: true, response: { status, data: { code: status, message: detail, detail }, headers },
  })
}

async function mountBuilder(props: Record<string, unknown> = {}): Promise<VueWrapper<any>> {
  const wrapper = mount(AdvancedQueryBuilder, {
    props: { embedded: true, ...props },
    // 真实 Element Plus（未注册时 el-* 渲染成同名自定义元素：具名插槽丢失、表格列的作用域插槽以 undefined 调用）
    global: { plugins: [ElementPlus], stubs: { GtIndexChip: true, CustomQueryFieldPicker: true, AcnrTargetResults: true } },
  })
  await flushPromises()
  return wrapper as unknown as VueWrapper<any>
}

function button(wrapper: VueWrapper<any>, text: string) {
  const b = wrapper.findAll('button').find((x) => x.text().includes(text))
  if (!b) throw new Error(`没有按钮「${text}」`)
  return b
}

function postsTo(url: string) {
  return apiMocks.post.mock.calls.filter((c) => c[0] === url)
}

let openSpy: any
beforeEach(() => {
  sessionStorage.clear()
  resetQueryBuilderAccessCache()
  apiMocks.get.mockReset()
  apiMocks.post.mockReset()
  httpMocks.post.mockReset()
  routerMock.resolve.mockClear()
  ;(ElMessage as any).warning.mockClear()
  ;(ElMessage as any).success.mockClear()
  accessHolder.value = ACCESS.all
  routeHolder.params = {}
  routeHolder.query = {}
  useAuthStore().token = 'tok'
  apiMocks.get.mockImplementation((url: string) => {
    if (url === '/api/query/access') {
      return accessHolder.value instanceof Error ? Promise.reject(accessHolder.value) : Promise.resolve(accessHolder.value)
    }
    if (url === '/api/query/schema') return Promise.resolve(SCHEMA)
    return Promise.resolve({})
  })
  apiMocks.post.mockImplementation((url: string) => Promise.resolve(
    url === '/api/address-registry/validate' ? { valid: true, issues: [] } : tbResult(),
  ))
  openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn().mockResolvedValue(undefined) }, configurable: true })
})
afterEach(() => { openSpy.mockRestore() })

describe('准入：前端判据只取 access 接口（R3.6、R11.3）', () => {
  it('无权：显示接口原因（含合伙人、项目经理）并禁用预览 / 执行', async () => {
    accessHolder.value = ACCESS.denied
    const wrapper = await mountBuilder()
    expect(wrapper.find('[data-testid="aqb-access-blocked"]').text()).toContain(FORBIDDEN)
    expect(button(wrapper, '执行查询').attributes('disabled')).toBeDefined()
    expect(button(wrapper, '生成 SQL 预览').attributes('disabled')).toBeDefined()
    expect(apiMocks.get.mock.calls.filter((c) => c[0] === '/api/query/access')).toHaveLength(1)
  })

  it('准入通过但作用域为空（accessible_project_count = 0）：禁用并显示接口 reason', async () => {
    accessHolder.value = ACCESS.empty
    const wrapper = await mountBuilder()
    expect(wrapper.find('[data-testid="aqb-access-blocked"]').text()).toContain('您当前没有可访问的项目')
    expect(button(wrapper, '执行查询').attributes('disabled')).toBeDefined()
  })

  it('接口取不到结论：保持不可用并提示，不回落到前端角色清单（系统管理员身份也一样）', async () => {
    useAuthStore().user = { id: 'u-admin', username: 'admin', email: '', role: 'admin' } as any
    accessHolder.value = new Error('Network Error')
    const wrapper = await mountBuilder()
    expect(wrapper.find('[data-testid="aqb-access-blocked"]').text()).toContain(ACCESS_UNAVAILABLE_REASON)
    expect(button(wrapper, '执行查询').attributes('disabled')).toBeDefined()
  })

  it('有权：不显示原因，操作可用', async () => {
    const wrapper = await mountBuilder()
    expect(wrapper.find('[data-testid="aqb-access-blocked"]').exists()).toBe(false)
    expect(button(wrapper, '执行查询').attributes('disabled')).toBeUndefined()
  })
})

describe('查询范围：默认当前项目与审计年度，可切「跨项目」（R3.5，AQ-18）', () => {
  it('在项目里打开：请求带当前项目与审计年度，结果显示「范围：当前项目」', async () => {
    routeHolder.params = { projectId: PID }
    const ps = useProjectStore()
    ps.projectId = PID
    ps.auditYear = 2025
    const wrapper = await mountBuilder()
    expect(wrapper.find('[data-testid="aqb-scope-current"]').text()).toBe('当前项目（2025 年度）')
    wrapper.vm.dsl.table = 'trial_balance'
    await wrapper.vm.doExecute()
    await flushPromises()
    expect(postsTo('/api/query/execute')[0][1]).toMatchObject({ table: 'trial_balance', project_id: PID, year: 2025 })
    expect(wrapper.find('[data-testid="aqb-result-scope"]').text()).toBe('范围：当前项目（2025 年度）')
  })

  it('宿主传入的项目与年度优先于路由；路由 ?year 优先于项目审计年度', async () => {
    routeHolder.params = { projectId: PID }
    routeHolder.query = { year: '2024' }
    const w1 = await mountBuilder()
    w1.vm.dsl.table = 'trial_balance'
    await w1.vm.doExecute()
    expect(postsTo('/api/query/execute')[0][1]).toMatchObject({ project_id: PID, year: 2024 })
    const w2 = await mountBuilder({ projectId: 'p-host', year: 2023 })
    w2.vm.dsl.table = 'trial_balance'
    await w2.vm.doExecute()
    expect(postsTo('/api/query/execute')[1][1]).toMatchObject({ project_id: 'p-host', year: 2023 })
  })

  it('「跨项目」开关：可访问 1 个项目时不出现；2 个或不限项目时出现，打开后请求不带项目与年度', async () => {
    routeHolder.params = { projectId: PID }
    accessHolder.value = ACCESS.one
    expect((await mountBuilder()).find('[data-testid="aqb-cross-project"]').exists()).toBe(false)
    for (const access of [ACCESS.two, ACCESS.all]) {
      resetQueryBuilderAccessCache()
      apiMocks.post.mockClear()
      accessHolder.value = access
      const wrapper = await mountBuilder()
      const sw = wrapper.find('[data-testid="aqb-cross-project"]')
      expect(sw.exists()).toBe(true)
      // el-switch 把 aria-label 放在内部的 role=switch 输入框上
      expect(sw.find('input').attributes('aria-label')).toBe('切换跨项目查询')
      wrapper.vm.crossProject = true
      wrapper.vm.dsl.table = 'trial_balance'
      await wrapper.vm.doExecute()
      const payload = postsTo('/api/query/execute')[0][1]
      expect('project_id' in payload).toBe(false)
      expect('year' in payload).toBe(false)
    }
  })

  it('不在项目里打开：没有范围选项，请求不带项目（作用域 = 可访问的全部项目）', async () => {
    const wrapper = await mountBuilder()
    expect(wrapper.find('[data-testid="aqb-scope-current"]').exists()).toBe(false)
    wrapper.vm.dsl.table = 'trial_balance'
    await wrapper.vm.doExecute()
    expect('project_id' in postsTo('/api/query/execute')[0][1]).toBe(false)
  })

  it('选了 ACNR 格时请求仍带 acnr_targets 与项目（跨项目也一样，R6.5）', async () => {
    routeHolder.params = { projectId: PID }
    const wrapper = await mountBuilder()
    wrapper.vm.crossProject = true
    wrapper.vm.acnrFieldIds = ['E1/E1-18/B20']
    wrapper.vm.dsl.table = 'trial_balance'
    await wrapper.vm.doExecute()
    expect(postsTo('/api/query/execute')[0][1]).toMatchObject({ project_id: PID, acnr_targets: ['E1/E1-18/B20'] })
  })
})

describe('翻页与导出（R2.6、R8.1）', () => {
  it('翻页发 offset，total 是全量行数；翻页条带 aria-label', async () => {
    apiMocks.post.mockImplementation((url: string) => Promise.resolve(
      url === '/api/address-registry/validate' ? { issues: [] } : tbResult({ total: 250, scope: { all_projects: true, project_count: null, unscoped_tables: [] } }),
    ))
    const wrapper = await mountBuilder()
    wrapper.vm.dsl.table = 'trial_balance'
    await wrapper.vm.doExecute()
    await flushPromises()
    expect(wrapper.text()).toContain('共 250 行')
    expect(wrapper.find('nav.gt-aqb-pager').attributes('aria-label')).toBe('查询结果翻页')
    wrapper.vm.onPageChange(2)
    await flushPromises()
    wrapper.vm.onPageChange(3)
    await flushPromises()
    const sent = postsTo('/api/query/execute').map((c) => c[1])
    expect(sent.map((p) => p.offset)).toEqual([undefined, 100, 200])
    expect(sent.every((p) => p.limit === 100)).toBe(true)
    // 重新执行回到第 1 页
    await wrapper.vm.doExecute()
    expect(postsTo('/api/query/execute')[3][1].offset).toBeUndefined()
  })

  it('导出全部：同一查询（不分页）+ 界面所见中文表头；按钮带 aria-label', async () => {
    routeHolder.params = { projectId: PID }
    apiMocks.post.mockImplementation((url: string) => Promise.resolve(url === '/api/address-registry/validate' ? { issues: [] } : {
      rows: [{ voucher_date: '2025-01-02', voucher_no: '记-1', account_code: '1002', debit_amount: '5.00' }],
      columns: ['voucher_date', 'voucher_no', 'account_code', 'debit_amount'], total: 1, table: 'tb_ledger', sql: '',
      scope: { all_projects: false, project_count: 1, unscoped_tables: [], requested_project_id: PID },
    }))
    httpMocks.post.mockResolvedValue({ data: new Blob(['x']) })
    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:x'), configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true })
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const wrapper = await mountBuilder()
    wrapper.vm.dsl.table = 'tb_ledger'
    await wrapper.vm.doExecute()
    wrapper.vm.onPageChange(2)
    await flushPromises()
    expect(button(wrapper, '导出 Excel').attributes('aria-label')).toBe('导出全部结果为 Excel')
    await wrapper.vm.doExport()
    await flushPromises()
    const [url, payload, config] = httpMocks.post.mock.calls[0]
    expect(url).toBe('/api/query/export-excel')
    expect(payload.headers).toEqual({ voucher_date: '凭证日期', voucher_no: '凭证号', account_code: '科目编码', debit_amount: '借方发生额' })
    expect(payload).toMatchObject({ table: 'tb_ledger', project_id: PID })
    expect('offset' in payload).toBe(false)
    expect(config).toMatchObject({ responseType: 'blob', _silent: true })
    clickSpy.mockRestore()
  })
})

describe('失败显示后端原因与追踪号（R11.1、AQ-29）', () => {
  it('403 人员表：结果区显示后端中文原因与可复制的追踪号，不落到「查询返回 0 行」', async () => {
    apiMocks.post.mockRejectedValueOnce(axiosError(403,
      { error_code: 'TABLE_ROLE_FORBIDDEN', message: '表「人员」仅对管理员、合伙人开放' }, { 'x-request-id': 'rid-1' }))
    const wrapper = await mountBuilder()
    wrapper.vm.dsl.table = 'trial_balance'
    await wrapper.vm.doExecute()
    await flushPromises()
    const alert = wrapper.find('[data-testid="aqb-query-error"]')
    expect(alert.text()).toContain('表「人员」仅对管理员、合伙人开放')
    expect(alert.text()).toContain('追踪号：rid-1')
    expect(wrapper.text()).not.toContain('查询返回 0 行')
    expect(wrapper.text()).not.toContain('Request failed')
    const copy = alert.findAll('button').find((b) => b.text().includes('复制追踪号'))!
    expect(copy.attributes('aria-label')).toBe('复制追踪号')
    await copy.trigger('click')
    expect((navigator.clipboard.writeText as any)).toHaveBeenCalledWith('rid-1')
  })

  it('422 参数校验：显示字段中文名 + 规则（不显示 pydantic 英文）', async () => {
    apiMocks.post.mockRejectedValueOnce(Object.assign(new Error('Request failed with status code 422'), { response: { status: 422, headers: {},
      data: { detail: [{ type: 'less_than_equal', loc: ['body', 'limit'], msg: 'Input should be less than or equal to 1000', ctx: { le: 1000 } }] } } }))
    const wrapper = await mountBuilder()
    wrapper.vm.dsl.table = 'trial_balance'
    await wrapper.vm.doExecute()
    await flushPromises()
    expect(wrapper.find('[data-testid="aqb-query-error"]').text()).toContain('参数校验失败：每页行数不能大于 1000')
    expect(wrapper.text()).not.toContain('Input should')
  })
})

describe('单项目结果：逐行「打开」与「复制引用」（R7.1~R7.3）', () => {
  it('打开：按 ADR-AQL-01 下钻到账簿查询，新标签打开（不加 noopener）', async () => {
    routeHolder.params = { projectId: PID }
    const ps = useProjectStore()
    ps.projectId = PID
    ps.auditYear = 2025
    const wrapper = await mountBuilder()
    wrapper.vm.dsl.table = 'trial_balance'
    await wrapper.vm.doExecute()
    await flushPromises()
    const open = wrapper.findAll('[data-testid="aqb-row-open"]')
    expect(open.length).toBeGreaterThan(0)
    expect(open[0].attributes('aria-label')).toBe('在账簿查询中打开')
    await open[0].trigger('click')
    await flushPromises()
    expect(routerMock.resolve).toHaveBeenCalledWith({
      name: 'LedgerPenetration', params: { projectId: PID }, query: { year: '2025', account: '1001' },
    })
    expect(openSpy.mock.calls[0]).toEqual(['/resolved/LedgerPenetration', '_blank'])
  })

  it('复制引用：本页批量校验后才可复制；校验不通过时不可用并显示原因', async () => {
    routeHolder.params = { projectId: PID }
    useProjectStore().auditYear = 2025
    useProjectStore().projectId = PID
    apiMocks.post.mockImplementation((url: string) => Promise.resolve(url === '/api/address-registry/validate'
      ? { valid: false, issues: [{ ref: "TB('1002','审定数')", status: 'not_found', message: '试算表没有科目 1002' }] }
      : tbResult()))
    const wrapper = await mountBuilder()
    wrapper.vm.dsl.table = 'trial_balance'
    await wrapper.vm.doExecute()
    await flushPromises()
    const validate = postsTo('/api/address-registry/validate')
    expect(validate).toHaveLength(1)
    expect(validate[0][1]).toMatchObject({ formula: "TB('1001','审定数')+TB('1002','审定数')", project_id: PID, year: 2025 })
    expect(wrapper.vm.refUsable(0)).toBe(true)
    expect(wrapper.vm.refUsable(1)).toBe(false)
    expect(wrapper.vm.refHint(1)).toBe('试算表没有科目 1002')
    const copies = wrapper.findAll('[data-testid="aqb-row-copy-ref"]')
    expect(copies[0].attributes('aria-label')).toBe("复制引用 TB('1001','审定数')")
    expect(copies[1].attributes('disabled')).toBeDefined()
    await copies[0].trigger('click')
    await flushPromises()
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith("TB('1001','审定数')")
  })

  it('跨项目结果：没有操作列（跨项目结果不下钻、引用无法按单个项目校验）', async () => {
    apiMocks.post.mockImplementation(() => Promise.resolve(tbResult({ scope: { all_projects: true, project_count: null, unscoped_tables: [] } })))
    const wrapper = await mountBuilder()
    wrapper.vm.dsl.table = 'trial_balance'
    await wrapper.vm.doExecute()
    await flushPromises()
    expect(wrapper.vm.rowActionsEnabled).toBe(false)
    expect(wrapper.find('[data-testid="aqb-row-open"]').exists()).toBe(false)
    expect(postsTo('/api/address-registry/validate')).toHaveLength(0)
  })
})
