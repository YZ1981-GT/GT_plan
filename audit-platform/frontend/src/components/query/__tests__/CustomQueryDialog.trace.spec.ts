/**
 * CustomQueryDialog.trace.spec.ts — 结果行右键「跳模板溯源」（advanced-query-linkage-closure 任务 32；ADR-AQL-17，R7.4，AQ-17）
 *
 * - URI 按本次结果的数据源生成 address-resolve 认的模块前缀（原先注册表源键原样发出，如 `tb_detail` ⇒ 400）；
 * - 登记了的底稿：关闭弹窗、跳到模板库「底稿模板」页签并带编码；调整分录 / 试算类结果：提示「该类结果没有模板定义」不跳；
 *   未登记的底稿编码给中文提示；请求自管错误（`_silent`），失败给一次中文提示。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))
vi.mock('@/utils/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/http')>()),
  default: { get: vi.fn().mockResolvedValue({ data: [], headers: {} }), post: vi.fn() },
  downloadFile: vi.fn(),
}))
const routerMock = vi.hoisted(() => ({ push: vi.fn(), resolve: vi.fn(() => ({ href: '/x' })) }))
vi.mock('vue-router', () => ({ useRouter: () => routerMock, useRoute: () => ({ params: {}, query: {} }) }))
vi.mock('@/services/commonApi', () => ({
  listProjectsWithProgress: vi.fn().mockResolvedValue([{ id: 'p1', name: '【测试】项目一', audit_year: 2025 }]),
}))
vi.mock('@/composables/useQueryBuilderAccess', async () => {
  const { computed } = await import('vue')
  return { useQueryBuilderAccess: () => ({ canUseBuilder: computed(() => true), builderDisabledReason: computed(() => '') }) }
})
vi.mock('@/views/AdvancedQueryBuilder.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ props: { embedded: Boolean, projectId: String, year: Number }, setup: () => () => h('div') }) }
})
vi.mock('@/components/query/SheetCellRangePicker.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({ props: ['modelValue', 'wpCode', 'sheetName', 'projectId', 'year'], setup: () => () => h('div') }) }
})
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return { ...actual, ElMessage: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() }) }
})

import ElementPlus, { ElMessage } from 'element-plus'
import CustomQueryDialog from '../CustomQueryDialog.vue'
import { RESOLVE_FAIL_MSG } from '../querySourceUri'

const resolveHolder: { value: unknown } = { value: {} }
let wrapper: VueWrapper<any> | null = null
async function queried(source: string, rows: Record<string, unknown>[]) {
  apiMocks.post.mockImplementation((url: string) => Promise.resolve(url === '/api/custom-query/execute'
    ? { rows, columns: Object.keys(rows[0] ?? {}), total: rows.length, meta: {} } : { issues: [] }))
  wrapper = mount(CustomQueryDialog, {
    props: { modelValue: true, projectId: 'p1', year: 2025, initialSource: source },
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  }) as unknown as VueWrapper<any>
  await flushPromises()
  await wrapper.vm.executeQuery()
  await flushPromises()
  return wrapper
}
async function trace(w: VueWrapper<any>, row: Record<string, unknown>) {
  w.vm.ctxMenuRow = row
  await w.vm.onTraceToTemplate()
  await flushPromises()
}
const resolveCalls = () => apiMocks.get.mock.calls.filter((c) => c[0] === '/api/custom-query/address-resolve')

beforeEach(() => {
  sessionStorage.clear()
  apiMocks.get.mockReset().mockImplementation((url: string) => (url === '/api/custom-query/address-resolve'
    ? (resolveHolder.value instanceof Error ? Promise.reject(resolveHolder.value) : Promise.resolve(resolveHolder.value))
    : Promise.resolve({})))
  apiMocks.post.mockReset()
  routerMock.push.mockClear()
  ;(ElMessage as any).warning.mockClear()
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

describe('跳模板溯源', () => {
  it('底稿清单行：按 wp_code 发 workpaper URI（_silent），登记了就跳到模板库底稿模板页签', async () => {
    resolveHolder.value = { module: 'workpaper', registered: true, route_path: '/template-library',
      route_query: { tab: 'wp-template', wp_code: 'E1' } }
    const w = await queried('workpaper', [{ wp_code: 'E1', wp_name: '货币资金' }])
    await trace(w, { wp_code: 'E1', wp_name: '货币资金' })
    expect(resolveCalls()[0][1]).toMatchObject({ params: { uri: 'workpaper:E1' }, _silent: true })
    expect(routerMock.push).toHaveBeenCalledWith({ path: '/template-library', query: { tab: 'wp-template', wp_code: 'E1' } })
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('试算类结果：发 tb: URI，后端说没有模板定义 ⇒ 提示且不跳转', async () => {
    resolveHolder.value = { module: 'tb', registered: false, route_path: '', route_query: {} }
    const w = await queried('tb_detail', [{ standard_account_code: '1001', account_name: '库存现金' }])
    await trace(w, { standard_account_code: '1001' })
    expect(resolveCalls()[0][1].params.uri).toBe('tb:tb_detail')
    expect((ElMessage as any).warning).toHaveBeenCalledWith(RESOLVE_FAIL_MSG.noTemplate)
    expect(RESOLVE_FAIL_MSG.noTemplate).toBe('该类结果没有模板定义')
    expect(routerMock.push).not.toHaveBeenCalled()
  })

  it('报表结果按报表类型发 report: URI；未登记的底稿编码给中文提示', async () => {
    resolveHolder.value = { module: 'report', registered: true, route_path: '/template-library',
      route_query: { tab: 'report-config', report_type: 'income_statement' } }
    const w = await queried('report_income_statement', [{ row_code: 'IS-001', row_name: '营业收入' }])
    await trace(w, { row_code: 'IS-001' })
    expect(resolveCalls()[0][1].params.uri).toBe('report:income_statement')
    expect(routerMock.push).toHaveBeenCalledWith({ path: '/template-library',
      query: { tab: 'report-config', report_type: 'income_statement' } })
    resolveHolder.value = { module: 'workpaper', registered: false, route_path: '', route_query: {} }
    routerMock.push.mockClear()
    await trace(w, { wp_code: 'ZZ9' })
    expect((ElMessage as any).warning).toHaveBeenCalledWith(RESOLVE_FAIL_MSG.notRegistered)
    expect(routerMock.push).not.toHaveBeenCalled()
  })
})
