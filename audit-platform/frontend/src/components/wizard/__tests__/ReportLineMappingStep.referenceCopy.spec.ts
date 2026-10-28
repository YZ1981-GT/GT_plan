/**
 * 项目向导「报表行次映射」步骤：一键参照（spec consol-autotree-residual-closure R1.4）
 *
 * 按客户名称在「你能查看的项目」里找来源；原先找不到时后端随便拿一个其他项目来复制、前端照报成功。
 * 现在后端回 `source_found: false` ⇒ 提示找不到该客户名称、弹窗不关、不报成功、不重读映射。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'

const { api, message } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))
vi.mock('@/services/apiProxy', () => ({ api }))
vi.mock('@/utils/confirm', () => ({ confirmDelete: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: message }))

import ReportLineMappingStep from '../ReportLineMappingStep.vue'

const COPY_URL = '/api/projects/p-1/report-line-mapping/reference-copy'

// 表格 / 弹窗内容与本文件无关：只占位（全局配置渲染桩的默认插槽，作用域插槽拿不到行数据）
const STUBS = { 'el-dialog': { render: () => null }, 'el-table': { render: () => null } }

async function mountStep() {
  const wrapper = shallowMount(ReportLineMappingStep, { props: { projectId: 'p-1' }, global: { stubs: STUBS } })
  await flushPromises()
  api.get.mockClear() // 挂载时读一次映射，与本文件无关
  const vm = wrapper.vm as any
  vm.showReferenceCopy = true
  vm.sourceCompanyCode = '甲公司'
  return vm
}

beforeEach(() => {
  api.get.mockReset().mockResolvedValue([])
  api.post.mockReset()
  Object.values(message).forEach((m) => m.mockReset())
})

describe('ReportLineMappingStep 一键参照', () => {
  it('找不到该客户名称的可参照项目：提示、弹窗不关、不报成功、不重读', async () => {
    api.post.mockResolvedValueOnce({ copied_count: 0, unmatched_accounts: [], source_found: false })
    const vm = await mountStep()
    await vm.handleReferenceCopy()
    await flushPromises()
    expect(api.post).toHaveBeenCalledWith(COPY_URL, { source_company_code: '甲公司' })
    expect(message.warning).toHaveBeenCalledWith('没有找到客户名称为「甲公司」的可参照项目')
    expect(message.success).not.toHaveBeenCalled()
    expect(vm.showReferenceCopy).toBe(true)
    expect(api.get).not.toHaveBeenCalled()
    expect(vm.referenceCopying).toBe(false)
  })

  it('找到来源：报复制条数并提示未匹配科目，关弹窗、重读映射', async () => {
    api.post.mockResolvedValueOnce({ copied_count: 2, unmatched_accounts: ['1001'], source_found: true })
    const vm = await mountStep()
    await vm.handleReferenceCopy()
    await flushPromises()
    expect(message.success).toHaveBeenCalledWith('已复制 2 条映射')
    expect(message.warning).toHaveBeenCalledWith('1 个科目未匹配: 1001')
    expect(vm.showReferenceCopy).toBe(false)
    expect(api.get).toHaveBeenCalledTimes(1)
  })
})
