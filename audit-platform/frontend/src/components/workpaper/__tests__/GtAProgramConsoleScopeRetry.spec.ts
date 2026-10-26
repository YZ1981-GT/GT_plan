/**
 * 控制台程序行委派：执行人看不到目标循环（400 out_of_scope）⇒ 填写理由后同一预览凭证带 expand_scope 重试；
 * 预览计数读嵌套 summary、预览里提示可见范围缺口（spec procedure-trim-generation-delegation-chain 任务 13）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as fs from 'node:fs'
import * as path from 'node:path'

/** SFC 里用到的 el-* 一律打桩（未解析的标签会不带参数调用作用域插槽而崩） */
const EL_STUBS = Object.fromEntries([...new Set([...fs.readFileSync(
  path.resolve(__dirname, '../GtAProgramConsole.vue'), 'utf-8').matchAll(/<(el-[a-z-]+)/g)].map((m) => m[1]))]
  .map((tag) => [tag, true]))

const mocks = vi.hoisted(() => ({ apply: vi.fn(), handleApiError: vi.fn() }))

vi.mock('vue-router', () => ({ useRoute: () => ({ params: { projectId: 'proj-001' }, query: {} }) }))
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([]), post: vi.fn().mockResolvedValue({}) },
}))
vi.mock('@/composables/useWpOnboardingGuide', () => ({
  useWpOnboardingGuide: () => ({ showGuide: { value: false }, guideSteps: { value: [] }, triggerGuide: vi.fn() }),
}))
vi.mock('@/components/workpaper/GtAuditFlowGraph.vue', () => ({ default: { name: 'GtAuditFlowGraph', template: '<div />' } }))
vi.mock('@/services/commonApi', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  applyProcedureDelegation: mocks.apply,
  listProjectProcedureRowTasks: vi.fn().mockResolvedValue({ items: [] }),
  getProgramRowAccess: vi.fn().mockResolvedValue({
    full_power: true, can_trim: true, own_program_nos: [], assignees: {}, template_code: 'E1A',
  }),
}))
vi.mock('@/services/staffApi', () => ({ listAssignments: vi.fn().mockResolvedValue([]) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: mocks.handleApiError }))

import GtAProgramConsole from '../GtAProgramConsole.vue'
import { api } from '@/services/apiProxy'

const OUT_OF_SCOPE = { response: { status: 400, data: { detail: {
  error: 'row_delegation_rejected', reason: 'out_of_scope', cycles: ['E'], message: '执行人甲的可见范围不含 E 循环',
} } } }

function mountConsole() {
  const wrapper = shallowMount(GtAProgramConsole, {
    props: { wpId: 'wp-001', sheetName: '货币资金实质性程序表E1A', schema: {}, htmlData: { programs: [], trim_decisions: [] } },
    global: { stubs: EL_STUBS },
  })
  const vm = wrapper.vm as any
  vm.delegateDialog = {
    visible: true, row: { task_id: 't1', lock_version: 0 }, assigneeId: 's1', reviewerId: '',
    previewStats: { status: 'ready', summary: { targets: 1, conflict: 0, already_assigned: 0 },
      scope_gaps: [{ role: 'assignee', name: '甲', cycles: ['E'], is_member: true }] },
    previewId: 'pv-1', reqId: 'req-1', ttl: null, loading: false,
  }
  return { wrapper, vm }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})
afterEach(() => vi.restoreAllMocks()) // 只还原本例 spyOn 的 ElMessageBox / ElMessage（vitest 3 不动 vi.fn）

describe('GtAProgramConsole — 程序行委派扩权重试', () => {
  it('预览：缺口提示来自 scope_gaps', () => {
    const { vm } = mountConsole()
    expect(vm.delegateScopeGapText).toBe('执行人 甲的可见范围不含 E 循环；应用时需填写理由扩大其可见范围')
  })

  it('out_of_scope ⇒ 理由 ⇒ 同一凭证 / 请求号带 expand_scope 重试并关闭弹窗', async () => {
    const prompt = vi.spyOn(ElMessageBox, 'prompt').mockResolvedValue({ value: '支援', action: 'confirm' } as any)
    mocks.apply.mockRejectedValueOnce(OUT_OF_SCOPE).mockResolvedValueOnce({ applied: 1 })
    const { vm } = mountConsole()
    await flushPromises()
    vi.mocked(api.get).mockClear()
    await vm.runDelegateApply()
    await flushPromises()
    expect(prompt).toHaveBeenCalledTimes(1)
    expect(mocks.apply, '填写理由后用同一凭证重试一次').toHaveBeenCalledTimes(2)
    const [first, second] = mocks.apply.mock.calls
    expect(first.slice(1, 3)).toEqual(['pv-1', 'req-1'])
    expect(second.slice(1, 3)).toEqual(['pv-1', 'req-1'])
    expect(first[4]).toEqual({ silent: true })
    expect(second[4]).toEqual({ expand_scope: true, scope_reason: '支援', silent: true })
    expect(vm.delegateDialog.visible).toBe(false)
    expect(vi.mocked(api.get).mock.calls.some(([url]) => String(url).includes('render-config?force_component_type=a-program-console')),
      '委派成功后重新拉取 overlay').toBe(true)
  })

  it('取消理由框 ⇒ 不重试、凭证保留；其他错误交给 handleApiError（不再显示对象）', async () => {
    vi.spyOn(ElMessageBox, 'prompt').mockRejectedValue('cancel')
    const info = vi.spyOn(ElMessage, 'info').mockImplementation((() => undefined) as any)
    mocks.apply.mockRejectedValueOnce(OUT_OF_SCOPE)
    const { vm } = mountConsole()
    await vm.runDelegateApply()
    await flushPromises()
    expect(mocks.apply).toHaveBeenCalledTimes(1)
    expect(vm.delegateDialog.previewId).toBe('pv-1')
    expect(vm.delegateDialog.visible).toBe(true)
    expect(info).toHaveBeenCalled()

    mocks.apply.mockRejectedValueOnce({ response: { status: 400, data: { detail: {
      error: 'row_delegation_rejected', reason: 'not_project_member', cycles: ['E'], message: '执行人甲不是本项目成员' } } } })
    await vm.runDelegateApply()
    await flushPromises()
    expect(mocks.handleApiError).toHaveBeenCalledWith(expect.anything(), '委派')
  })
})
