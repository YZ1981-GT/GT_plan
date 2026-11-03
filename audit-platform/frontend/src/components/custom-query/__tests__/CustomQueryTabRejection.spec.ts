/**
 * 业务视图被拒时结果区的持久文案（acnr-foundation-defect-closure T16，评审 RV7.5-02）。
 *
 * 需求 1.6：422 的逐项中文原因要让用户看得到，不出现英文。提示（ElMessage）几秒后消失，结果区「查询失败」里那段文字
 * 一直留着 ⇒ 它也必须是逐项中文原因；识别不出拒绝形状时显示中文兜底，不显示 axios 的「Request failed with status code …」。
 * 错误对象按生产形状构造：后端 http_exception_handler 把 detail 放进 message，拦截器同一函数（normaliseErrorEnvelope）补出 detail。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { normaliseErrorEnvelope } from '@/utils/http'
import CustomQueryTab from '@/components/template-library/CustomQueryTab.vue'

vi.mock('@/composables/usePermissionMatrix', () => ({
  usePermissionMatrix: () => ({ currentRole: { value: 'manager' } }),
}))
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({ buildAddressTree: vi.fn(), loadCellNodes: vi.fn(), resolveIndex: vi.fn(), clearCache: vi.fn() }),
}))
vi.mock('@/utils/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/utils/http')>()),
  default: { get: vi.fn(), post: vi.fn() },
}))
vi.mock('@/utils/eventBus', () => ({ eventBus: { on: vi.fn(), off: vi.fn(), emit: vi.fn() } }))
vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
    ElMessageBox: { confirm: vi.fn(), alert: vi.fn(), prompt: vi.fn() },
    ElNotification: vi.fn(),
  }
})
const apiMocks = vi.hoisted(() => ({
  get: vi.fn().mockResolvedValue([]),
  post: vi.fn().mockResolvedValue({}),
  delete: vi.fn().mockResolvedValue({}),
}))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))

const PID = '00000000-0000-0000-0000-0000000000a1'
const ISSUE_SHEET = '所选为整张表、不是单元格，请细化到具体单元格'
const ISSUE_TB = '该地址不是底稿单元格（tb / 报表 / 附注 / 辅助域），本功能暂不支持取值'

/** axios 风格的错误：message 是英文，response 是生产信封 */
function axiosError(status: number, body: Record<string, unknown>) {
  const response = { status, data: body }
  normaliseErrorEnvelope(response)
  return Object.assign(new Error(`Request failed with status code ${status}`), { isAxiosError: true, response })
}

async function mountAndExecute(rejection: unknown) {
  apiMocks.post.mockRejectedValueOnce(rejection)
  const wrapper = shallowMount(CustomQueryTab, {
    global: {
      directives: { loading: {} },
      stubs: {
        'el-dialog': { template: '<div class="el-dialog-stub" />' },
        'el-row': { template: '<div><slot /></div>' },
        'el-col': { template: '<div><slot /></div>' },
        'el-alert': { template: '<div class="el-alert-stub"><slot name="title" /><slot /></div>' },
        // 结果区的失败提示自 advanced-query-linkage-closure 任务 29 起是共用组件 QueryErrorAlert（弹窗与页面版同一个），
        // 浅挂载时不桩掉它，才看得到它渲染的原因文字
        QueryErrorAlert: false,
      },
    },
  }) as unknown as VueWrapper<any>
  await flushPromises()
  wrapper.vm.formCtx.project_id = PID
  wrapper.vm.formCtx.year = 2025
  wrapper.vm.formCtx.source = 'tb_detail'
  wrapper.vm.acnrFieldIds = ['E1/E1-14', 'tb:1001']
  await wrapper.vm.onExecute()
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMocks.get.mockResolvedValue([])
})

describe('业务视图被拒：结果区持久显示中文原因（RV7.5-02）', () => {
  it('422 ACNR_TARGETS_REJECTED：结果区含逐项原因，不含英文 Request failed', async () => {
    const wrapper = await mountAndExecute(axiosError(422, { code: 422, message: {
      error_code: 'ACNR_TARGETS_REJECTED', message: '所选单元格中有 2 项无法取值，未执行查询',
      issues: [
        { ref: 'E1/E1-14', error_code: 'sheet_level', message: ISSUE_SHEET },
        { ref: 'tb:1001', error_code: 'unsupported_domain', message: ISSUE_TB },
      ] } }))
    // 请求确实带了单元格目标（被拒的正是这一请求）
    expect(apiMocks.post.mock.calls[0][1].acnr_targets).toEqual(['E1/E1-14', 'tb:1001'])
    const body = wrapper.find('.gt-cqt-result-body').text()
    expect(body).toContain('查询失败')
    expect(body).toContain('所选单元格中有 2 项无法取值，未执行查询')
    expect(body).toContain(`E1/E1-14：${ISSUE_SHEET}`)
    expect(body).toContain(`tb:1001：${ISSUE_TB}`)
    expect(body).not.toContain('Request failed')
  })

  it('识别不出拒绝形状（500）：结果区显示中文兜底，不显示英文', async () => {
    const wrapper = await mountAndExecute(axiosError(500, { code: 500, message: 'Internal Server Error' }))
    const body = wrapper.find('.gt-cqt-result-body').text()
    // 失败文案的单一实现是 queryErrorText.describeQueryError（advanced-query-linkage-closure 任务 27 / 29，R11.1）：
    // starlette 的英文缺省文案译成中文，与弹窗、构建器同一口径
    expect(body).toContain('查询失败')
    expect(body).toContain('服务器内部错误，请稍后重试')
    expect(body).not.toContain('Internal Server Error')
    expect(body).not.toContain('Request failed')
  })
})
