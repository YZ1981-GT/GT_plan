/**
 * 试算表「映射规则」弹窗：参照其他单位复制（spec consol-autotree-residual-closure R1.4）
 *
 * 下拉选的是项目 id ⇒ 按来源项目复制（`source_project_id`）。原先把项目 id 塞进 `source_company_code`
 * 去比客户名称，恒比不上，后端再随便拿一个其他项目来复制；现在找不到来源时后端回 `source_found: false`，
 * 前端提示换一个单位、弹窗不关、不重读映射。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'

const { api, message, handleApiError } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  handleApiError: vi.fn(),
}))
vi.mock('@/services/apiProxy', () => ({ api }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError }))
vi.mock('@/utils/confirm', () => ({ confirmDelete: vi.fn() }))
vi.mock('@/composables/useExcelIO', () => ({ exportMultiSheetData: vi.fn(), readSheetObjects: vi.fn() }))
vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    projectOptions: [{ id: 'p-1', name: '本单位' }, { id: 'p-src', name: '来源单位' }],
    loadProjectOptions: vi.fn(),
  }),
}))
vi.mock('element-plus', () => ({ ElMessage: message, ElMessageBox: { confirm: vi.fn() } }))

import ReportLineMappingDialog from '../ReportLineMappingDialog.vue'

const COPY_URL = '/api/projects/p-1/report-line-mapping/reference-copy'
const LIST_URL = '/api/projects/p-1/report-line-mapping'

// 表格 / 弹窗内容与本文件无关：只占位（全局配置渲染桩的默认插槽，作用域插槽拿不到行数据）
const STUBS = { 'el-dialog': { render: () => null }, 'el-table': { render: () => null } }

function mountDialog() {
  const wrapper = shallowMount(ReportLineMappingDialog, {
    props: { modelValue: false, projectId: 'p-1' },
    global: { stubs: STUBS },
  })
  const vm = wrapper.vm as any
  vm.showRefDialog = true
  vm.refSourceCode = 'p-src'
  return vm
}

beforeEach(() => {
  api.get.mockReset().mockResolvedValue([])
  api.post.mockReset()
  Object.values(message).forEach((m) => m.mockReset())
  handleApiError.mockReset()
})

describe('ReportLineMappingDialog 参照其他单位', () => {
  it('来源单位下拉不列本项目（选了也只会被后端拒绝）', () => {
    const vm = mountDialog()
    expect(vm.projectOptions.map((p: any) => p.id)).toEqual(['p-src'])
  })

  it('按所选来源项目复制：只传 source_project_id；成功后关弹窗并重读映射', async () => {
    api.post.mockResolvedValueOnce({ copied_count: 3, unmatched_accounts: [], source_found: true })
    const vm = mountDialog()
    await vm.onReferenceCopy()
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledWith(COPY_URL, { source_project_id: 'p-src' })
    expect(message.success).toHaveBeenCalledWith('已复制 3 条映射')
    expect(vm.showRefDialog).toBe(false)
    expect(api.get.mock.calls.map((c) => c[0])).toContain(LIST_URL)
    expect(vm.refLoading).toBe(false)
  })

  it('来源找不到（source_found: false）：提示换一个单位，弹窗不关、不报成功、不重读', async () => {
    api.post.mockResolvedValueOnce({ copied_count: 0, unmatched_accounts: [], source_found: false })
    const vm = mountDialog()
    await vm.onReferenceCopy()
    await flushPromises()
    expect(message.warning).toHaveBeenCalledWith('没有找到可参照的来源单位，请换一个单位再试')
    expect(message.success).not.toHaveBeenCalled()
    expect(vm.showRefDialog).toBe(true)
    expect(api.get).not.toHaveBeenCalled()
    expect(vm.refLoading).toBe(false)
  })

  it('请求失败交给统一错误处理，弹窗不关', async () => {
    const err = Object.assign(new Error('forbidden'), { response: { status: 403 } })
    api.post.mockRejectedValueOnce(err)
    const vm = mountDialog()
    await vm.onReferenceCopy()
    await flushPromises()
    expect(handleApiError).toHaveBeenCalledWith(err, '参照复制')
    expect(vm.showRefDialog).toBe(true)
    expect(vm.refLoading).toBe(false)
  })
})
