/**
 * 项目概览「创建下年」被建项授权拒绝（spec batch-project-authorization-and-lock-hardening 6.2 触类旁通）：
 * 原先 403 时拦截器弹「权限不足」、handleApiError 再弹「创建：无权操作」，两条都没有原因。
 * 现在请求带 `_forbiddenHandler` 只显示后端原因；其他错误仍交给 handleApiError。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn() },
  push: vi.fn(),
  handleApiError: vi.fn(),
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.push, resolve: vi.fn(() => ({ href: '' })) }),
  useRoute: () => ({ params: {}, query: {} }),
}))
vi.mock('element-plus', () => ({
  ElMessage: mocks.message,
  ElNotification: vi.fn(),
  ElMessageBox: { confirm: vi.fn() },
}))
vi.mock('@/utils/confirm', () => ({ confirmForceReset: vi.fn(), confirmDangerous: vi.fn().mockResolvedValue(undefined) }))
vi.mock('@/services/apiProxy', () => ({ api: mocks.api }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: mocks.handleApiError }))
vi.mock('@/composables/useNavigationStack', () => ({ useNavigationStack: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/displayPrefs', () => ({ useDisplayPrefsStore: () => ({ fmt: (v: number) => String(v) }) }))
vi.mock('@/utils/openLedgerWindow', () => ({ openLedgerWindow: vi.fn() }))
vi.mock('@/components/layout/PlatformUserGuideDialog.vue', () => ({ default: { name: 'PlatformUserGuideDialog', render: () => null } }))
vi.mock('@/components/wizard/TeamAssignmentStep.vue', () => ({ default: { name: 'TeamAssignmentStep', render: () => null } }))

import DetailProjectPanel from '../DetailProjectPanel.vue'

const DENIED = { error_code: 'COMPANY_CREATION_NOT_AUTHORIZED', message: '有 1 个企业代码暂无建项授权，请联系管理员授权' }

/** 与 http.ts 一致：403 且请求带 _forbiddenHandler ⇒ 先调钩子（不弹通用提示），再把错误抛给调用方 */
function rejectAsInterceptor(status: number, data: unknown) {
  return (_url: string, _body: unknown, config?: any) => {
    const error = { isAxiosError: true, config, response: { status, data } }
    if (status === 403 && typeof config?._forbiddenHandler === 'function') config._forbiddenHandler(error)
    return Promise.reject(error)
  }
}

const mountPanel = () => shallowMount(DetailProjectPanel, {
  props: { project: { id: 'p-prev', name: '【测试】甲_2096', audit_year: 2096 } },
})

beforeEach(() => {
  mocks.api.get.mockReset().mockResolvedValue(null)
  mocks.api.post.mockReset()
  mocks.push.mockReset()
  mocks.handleApiError.mockReset()
  Object.values(mocks.message).forEach((fn) => fn.mockReset())
})

describe('创建下年：建项授权被拒', () => {
  it('403：只显示后端原因，不再叠加「无权操作」，不跳转', async () => {
    mocks.api.post.mockImplementation(rejectAsInterceptor(403, { code: 403, message: DENIED, detail: DENIED }))
    const wrapper = mountPanel()
    await (wrapper.vm as any).onCreateNextYear()
    await flushPromises()
    expect(mocks.api.post).toHaveBeenCalledTimes(1)
    expect(mocks.api.post.mock.calls[0][0]).toBe('/api/projects/p-prev/create-next-year')
    expect(mocks.message.error).toHaveBeenCalledWith('有 1 个企业代码暂无建项授权，请联系管理员授权')
    expect(mocks.handleApiError).not.toHaveBeenCalled()
    expect(mocks.push).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('其他错误仍交给 handleApiError', async () => {
    const wrapper = mountPanel()
    mocks.api.post.mockImplementation(rejectAsInterceptor(409, { code: 409, message: '下年项目已存在' }))
    await (wrapper.vm as any).onCreateNextYear()
    await flushPromises()
    expect(mocks.handleApiError).toHaveBeenCalledWith(expect.objectContaining({ response: expect.objectContaining({ status: 409 }) }), '创建')
    expect(mocks.message.error).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('成功路径不变：提示并进入新项目向导', async () => {
    const wrapper = mountPanel()
    mocks.api.post.mockResolvedValue({ new_project_id: 'p-next-0001', items_copied: {}, notices: [] })
    await (wrapper.vm as any).onCreateNextYear()
    await flushPromises()
    expect(mocks.message.success).toHaveBeenCalled()
    expect(mocks.push).toHaveBeenCalledWith('/projects/new?projectId=p-next-0001')
    wrapper.unmount()
  })
})
