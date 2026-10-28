/**
 * 构建器导出被拒时的提示（acnr-foundation-defect-closure T16，评审 RV7.5-03）。
 *
 * `/api/query/export-excel` 带着单元格取值目标发送，被拒时返回 422（T15）。导出是 blob 请求，错误体也是 Blob：
 * 原实现没有 `_silent`、失败走 handleApiError ⇒ 用户看到拦截器与 handleApiError 两条笼统提示，没有逐项原因。
 * 本用例经生产 `utils/http`（拦截器）与 `utils/errorHandler`，只替换 axios adapter 返回真实形状的 422 blob。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ElMessage, ElNotification } from 'element-plus'
import http from '@/utils/http'
import AdvancedQueryBuilder from '@/views/AdvancedQueryBuilder.vue'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 't', refreshToken: null, logout: vi.fn(), setTokens: vi.fn() }),
}))
vi.mock('nprogress', () => ({ default: { start: vi.fn(), done: vi.fn(), inc: vi.fn() } }))
vi.mock('@/composables/useVersionCheck', () => ({ versionBridge: { check: vi.fn() } }))
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() }),
    ElNotification: Object.assign(vi.fn(), { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() }),
  }
})
const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))
vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => ({ params: {}, query: {}, path: '/advanced-query' }),
}))

const SCHEMA = {
  tables: [{ name: 'trial_balance', label: '试算表', fields: ['id', 'year'] }],
  operators: ['eq'], aggregates: ['count'],
}
const ISSUE_SHEET = '所选为整张表、不是单元格，请细化到具体单元格'
const ISSUE_TB = '该地址不是底稿单元格（tb / 报表 / 附注 / 辅助域），本功能暂不支持取值'
/** 生产信封：后端 http_exception_handler 把 detail 放进 message；导出是 blob 请求，错误体同样是 Blob */
const REJECTION_BODY = { code: 422, message: {
  error_code: 'ACNR_TARGETS_REJECTED', message: '所选单元格中有 2 项无法取值，未执行查询',
  issues: [
    { ref: 'E1/E1-14', error_code: 'sheet_level', message: ISSUE_SHEET },
    { ref: 'tb:1001', error_code: 'unsupported_domain', message: ISSUE_TB },
  ] } }

let originalAdapter: any
beforeEach(() => {
  vi.clearAllMocks()
  apiMocks.get.mockResolvedValue(SCHEMA)
  originalAdapter = http.defaults.adapter
  http.defaults.adapter = async (config: any) => {
    const response = {
      data: new Blob([JSON.stringify(REJECTION_BODY)], { type: 'application/json' }),
      status: 422, statusText: 'Unprocessable Entity', headers: {}, config,
    }
    throw Object.assign(new Error('Request failed with status code 422'), { isAxiosError: true, config, response })
  }
})
afterEach(() => { http.defaults.adapter = originalAdapter })

/** 所有可见提示：ElMessage(...) 与其四个方法、ElNotification(...) 与其四个方法 */
function allToasts(): string[] {
  const out: string[] = []
  for (const fn of [ElMessage, ElNotification] as any[]) {
    for (const m of [fn, fn.success, fn.warning, fn.error, fn.info]) {
      for (const call of m.mock.calls) {
        const arg = call[0]
        out.push(typeof arg === 'string' ? arg : String(arg?.message ?? JSON.stringify(arg)))
      }
    }
  }
  return out
}

describe('构建器导出被拒：只弹一条提示且含逐项原因（RV7.5-03）', () => {
  it('422 blob ACNR_TARGETS_REJECTED → 一条「导出 Excel：…」逐项原因', async () => {
    const wrapper = mount(AdvancedQueryBuilder, { global: { stubs: { 'el-table': true, 'el-table-column': true } } })
    await flushPromises()
    const vm: any = wrapper.vm
    vm.dsl.table = 'trial_balance'
    vm.dsl.fields = ['id']
    await vm.doExport()
    await flushPromises()

    const toasts = allToasts()
    expect(toasts).toHaveLength(1)
    expect(toasts[0]).toContain('导出 Excel：所选单元格中有 2 项无法取值，未执行查询')
    expect(toasts[0]).toContain(`E1/E1-14：${ISSUE_SHEET}`)
    expect(toasts[0]).toContain(`tb:1001：${ISSUE_TB}`)
    expect(vm.loadingExport).toBe(false)
  })
})
