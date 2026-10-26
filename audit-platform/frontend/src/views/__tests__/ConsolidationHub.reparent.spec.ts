/**
 * 「合并」总览页拖拽改上级（spec consol-autotree-linkage-closure R3.3 / 任务 20）
 *
 * - 拖拽确认后 PATCH 上级代码，并把目标企业名称作为「新上级本年度没建项」时的名称提示；请求静默（自己提示错误）；
 * - 成功：提示同步了哪些项目（合并项目 / 单户项目）的哪些字段 + 后端说明（有说明时为警告样式），然后重读树；
 * - 失败（成环 400 / 代码不合法 422 / 无权 403）：统一错误处理只提示一次，并重读树恢复原位；取消则不调接口。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'

const { api, notify, confirm, handleApiError, fetchTree } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
  notify: vi.fn(),
  confirm: vi.fn(),
  handleApiError: vi.fn(),
  fetchTree: vi.fn(),
}))
vi.mock('@/services/apiProxy', () => ({ api }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: (...a: any[]) => handleApiError(...a) }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: (...a: any[]) => confirm(...a) },
  ElNotification: (...a: any[]) => notify(...a),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/components/wizard/BatchImportDialog.vue', () => ({ default: { name: 'BatchImportDialog', render: () => null } }))
vi.mock('@/composables/useGroupTree', async () => {
  const { ref, computed } = await import('vue')
  return {
    useGroupTree: () => ({
      trees: ref([]), independents: ref([]), loading: ref(false), error: ref(null), searchQuery: ref(''),
      hasTrees: computed(() => false), totalTreeNodes: computed(() => 0), hasSearchMatch: computed(() => true),
      fetchTree: (...a: any[]) => fetchTree(...a), filterNode: () => true,
    }),
    highlightSegments: () => [], consolMethodLabel: () => '', formatShareholding: () => '', countConsolMethods: () => ({}),
  }
})

import ConsolidationHub from '../ConsolidationHub.vue'
import { reparentSummary } from '@/components/consolidation/composables/consolReparent'

const DRAG = { data: { id: 'p-a', companyName: '甲公司', label: '甲公司', companyCode: 'A', children: [] } }
const DROP = { data: { id: 'p-n', companyName: '新上级公司', label: '新上级公司', companyCode: 'N', children: [] } }

function mountHub() {
  return shallowMount(ConsolidationHub, { global: { directives: { loading: {} } } })
}

beforeEach(() => {
  api.get.mockReset().mockResolvedValue({})
  api.patch.mockReset()
  notify.mockReset()
  confirm.mockReset().mockResolvedValue('confirm')
  handleApiError.mockReset()
  fetchTree.mockReset().mockResolvedValue(undefined)
})

describe('reparentSummary', () => {
  it('列出有变化的项目与字段（区分合并 / 单户项目），附后端说明；没有变化时如实说明', () => {
    expect(reparentSummary({
      synced: [
        { id: '1', name: '甲公司', report_scope: 'standalone', fields: ['上级企业名称', '上级企业代码'] },
        { id: '2', name: '甲公司', report_scope: 'consolidated', fields: ['上级企业代码'] },
        { id: '3', name: '无变化公司', report_scope: 'standalone', fields: [] },
      ],
      notices: ['上级企业 N 本年度尚未建项，上级企业名称暂未填写'],
    })).toBe('已同步 甲公司（单户项目）的上级企业名称、上级企业代码；甲公司（合并项目）的上级企业代码。上级企业 N 本年度尚未建项，上级企业名称暂未填写。')
    expect(reparentSummary({ synced: [{ id: '1', name: '甲公司', report_scope: 'standalone', fields: [] }] })).toBe('项目信息没有变化。')
    expect(reparentSummary(null)).toBe('项目信息没有变化。')
  })
})

describe('ConsolidationHub 拖拽改上级', () => {
  it('确认后静默 PATCH（带新上级名称提示），成功提示同步了哪些项目与字段并重读树', async () => {
    api.patch.mockResolvedValueOnce({
      parent_company_code: 'N', parent_company_name: '新上级公司', notices: [],
      synced: [{ id: 'p-a', name: '甲公司', report_scope: 'standalone', fields: ['上级企业代码', '上级企业名称'] }],
    })
    const wrapper = mountHub()
    await flushPromises()
    fetchTree.mockClear()
    await (wrapper.vm as any).onNodeDrop(DRAG, DROP, 'inner')
    await flushPromises()
    expect(api.patch).toHaveBeenCalledWith('/api/projects/p-a/parent-code',
      { parent_company_code: 'N', parent_company_name: '新上级公司' }, { _silent: true })
    expect(notify).toHaveBeenCalledWith(expect.objectContaining({
      title: '层级调整成功', type: 'success', message: '已同步 甲公司（单户项目）的上级企业代码、上级企业名称。',
    }))
    expect(fetchTree).toHaveBeenCalledWith('consolidated')
  })

  it('有后端说明 ⇒ 警告样式并带说明', async () => {
    api.patch.mockResolvedValueOnce({ synced: [], notices: ['上级企业 N 本年度尚未建项，上级企业名称暂未填写'] })
    const wrapper = mountHub()
    await flushPromises()
    await (wrapper.vm as any).onNodeDrop(DRAG, DROP, 'inner')
    await flushPromises()
    expect(notify).toHaveBeenCalledWith(expect.objectContaining({ type: 'warning', message: expect.stringContaining('尚未建项') }))
  })

  it('失败走统一错误处理（只提示一次）并重读树；取消确认不调接口', async () => {
    const err = { response: { status: 400, data: { detail: '该调整会形成循环引用（项目成为自己的祖先）' } } }
    api.patch.mockRejectedValueOnce(err)
    const wrapper = mountHub()
    await flushPromises()
    fetchTree.mockClear()
    await (wrapper.vm as any).onNodeDrop(DRAG, DROP, 'inner')
    await flushPromises()
    expect(handleApiError).toHaveBeenCalledWith(err, '层级调整')
    expect(notify).not.toHaveBeenCalled()
    expect(fetchTree).toHaveBeenCalledTimes(1)

    confirm.mockRejectedValueOnce('cancel')
    api.patch.mockClear()
    await (wrapper.vm as any).onNodeDrop(DRAG, DROP, 'inner')
    await flushPromises()
    expect(api.patch).not.toHaveBeenCalled()
    expect(fetchTree).toHaveBeenCalledTimes(2)
  })
})
