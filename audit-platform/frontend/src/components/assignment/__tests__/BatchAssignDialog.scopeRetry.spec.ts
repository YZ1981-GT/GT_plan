/**
 * 批量委派弹窗：被委派人看不到目标循环（400 out_of_scope）⇒ 填写理由后带 expand_scope 重试
 * （spec procedure-trim-generation-delegation-chain 任务 13）。首次请求免全局错误提示（_silent），取消则不委派。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import * as fs from 'node:fs'
import * as path from 'node:path'

/** SFC 里用到的 el-* 一律打桩（测试环境不装 element-plus，未解析的标签会不带参数调用作用域插槽而崩） */
const EL_STUBS = Object.fromEntries([...new Set([...fs.readFileSync(
  path.resolve(__dirname, '../BatchAssignDialog.vue'), 'utf-8').matchAll(/<(el-[a-z-]+)/g)].map((m) => m[1]))]
  .map((tag) => [tag, true]))

const mocks = vi.hoisted(() => ({
  post: vi.fn(),
  prompt: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
  handleApiError: vi.fn(),
}))

vi.mock('@/utils/http', () => ({ default: { post: mocks.post, get: vi.fn() } }))
vi.mock('@/services/staffApi', () => ({ listAssignments: vi.fn().mockResolvedValue([]) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: mocks.handleApiError }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('element-plus', () => ({
  ElMessage: { success: mocks.success, info: mocks.info, warning: vi.fn(), error: vi.fn() },
  ElMessageBox: { prompt: mocks.prompt },
}))

import BatchAssignDialog from '../BatchAssignDialog.vue'

const OUT_OF_SCOPE = { response: { status: 400, data: { detail: {
  error: 'lead_delegation_rejected', reason: 'out_of_scope', cycles: ['F'],
  message: '被委派人的可见范围不含 F 循环，填写理由后可扩大其可见范围',
} } } }

function mountDialog() {
  const wrapper = shallowMount(BatchAssignDialog, {
    props: { modelValue: false, projectId: 'p1', wpIds: ['w1', 'w2'], wpList: [] },
    global: { stubs: EL_STUBS },
  })
  const vm = wrapper.vm as any
  vm.form.strategy = 'manual'
  vm.selectedCandidates = [{ user_id: 'u1', staff_id: 's1', staff_name: '甲', role: 'auditor' }]
  vm.previewAssignments = [
    { wp_id: 'w1', wp_code: 'F2', wp_name: '存货', user_id: 'u1' },
    { wp_id: 'w2', wp_code: 'F4', wp_name: '应付账款', user_id: 'u1' },
  ]
  return { wrapper, vm }
}

beforeEach(() => vi.clearAllMocks())

describe('BatchAssignDialog — 可见范围扩权重试', () => {
  it('out_of_scope ⇒ 填写理由 ⇒ 同一载荷带 expand_scope / scope_reason 重试，成功后发出 assigned', async () => {
    mocks.post.mockRejectedValueOnce(OUT_OF_SCOPE)
      .mockResolvedValueOnce({ data: { updated: 2, notifications_sent: 1, message: 'ok' } })
    mocks.prompt.mockResolvedValueOnce({ value: ' 跨循环支援 ' })
    const { wrapper, vm } = mountDialog()
    await vm.onSubmit()
    await flushPromises()

    expect(mocks.post).toHaveBeenCalledTimes(2)
    const [[url1, body1, cfg1], [url2, body2, cfg2]] = mocks.post.mock.calls
    expect(url1).toBe('/api/workpapers/batch-assign-enhanced')
    expect(url2).toBe(url1)
    expect(cfg1).toMatchObject({ _silent: true })
    expect(cfg2).toMatchObject({ _silent: true })
    expect(body1.expand_scope).toBeUndefined()
    expect(body2).toEqual({ ...body1, expand_scope: true, scope_reason: '跨循环支援' })
    expect(wrapper.emitted('assigned')?.[0]?.[0]).toEqual({ updated: 2, notifications_sent: 1, message: 'ok' })
    expect(mocks.handleApiError).not.toHaveBeenCalled()
  })

  it('取消理由框 ⇒ 不重试、不发出 assigned', async () => {
    mocks.post.mockRejectedValueOnce(OUT_OF_SCOPE)
    mocks.prompt.mockRejectedValueOnce('cancel')
    const { wrapper, vm } = mountDialog()
    await vm.onSubmit()
    await flushPromises()
    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('assigned')).toBeUndefined()
    expect(mocks.info).toHaveBeenCalled()
  })

  it('已裁剪 409 不弹理由框，交给 handleApiError 提示', async () => {
    mocks.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: {
      error: 'lead_delegation_rejected', reason: 'trimmed', cycles: [], message: '底稿已在程序裁剪中标为不执行' } } } })
    const { vm } = mountDialog()
    await vm.onSubmit()
    await flushPromises()
    expect(mocks.prompt).not.toHaveBeenCalled()
    expect(mocks.handleApiError).toHaveBeenCalledWith(expect.anything(), '批量委派')
  })
})
