/**
 * 「合并」总览：企业树有变化提示（spec consol-autotree-residual-closure R5.2）
 *
 * 合并范围以企业树为准：不再拿合并范围表比对（`/scope-diff`、`/sync-scope` 已删）；
 * 对每棵有合并根项目的树读企业树版本预览（静默），与最近记录的版本相比有结构变化时显示「企业树有变化」，
 * 点开即企业树版本弹窗；弹窗里记录新版本后提示随回执更新；读失败不提示、不阻塞；拖拽改上级后重读。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'

const { api, notify, confirm, message, fetchTree, trees } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
  notify: vi.fn(),
  confirm: vi.fn(),
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  fetchTree: vi.fn(),
  trees: { value: [] as any[] },
}))
vi.mock('@/services/apiProxy', () => ({ api }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('element-plus', () => ({
  ElMessage: message,
  ElMessageBox: { confirm: (...a: any[]) => confirm(...a) },
  ElNotification: (...a: any[]) => notify(...a),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/components/wizard/BatchImportDialog.vue', () => ({ default: { name: 'BatchImportDialog', render: () => null } }))
vi.mock('@/components/wizard/ConsolScopeConfigDialog.vue', () => ({
  default: { name: 'ConsolScopeConfigDialog', props: ['modelValue', 'projectId', 'mode'], emits: ['update:modelValue', 'recorded'], render: () => null },
}))
vi.mock('@/composables/useGroupTree', async () => {
  const { ref, computed } = await import('vue')
  const treesRef = ref<any[]>([])
  trees.value = treesRef as any
  return {
    useGroupTree: () => ({
      trees: treesRef, independents: ref([]), loading: ref(false), error: ref(null), searchQuery: ref(''),
      hasTrees: computed(() => treesRef.value.length > 0), totalTreeNodes: computed(() => 0),
      hasSearchMatch: computed(() => true),
      fetchTree: (...a: any[]) => fetchTree(...a), filterNode: () => true,
    }),
    highlightSegments: () => [], consolMethodLabel: () => '', formatShareholding: () => '', countConsolMethods: () => ({}),
  }
})

import ConsolidationHub from '../ConsolidationHub.vue'

const TREES = [
  { key: 't1', ultimateCode: 'G1', ultimateName: '甲集团', year: 2025, rootProjectId: 'p-1', children: [] },
  { key: 't2', ultimateCode: 'G2', ultimateName: '乙集团', year: 2025, rootProjectId: 'p-2', children: [] },
  { key: 't3', ultimateCode: 'G3', ultimateName: '丙集团', year: 2025, rootProjectId: null, children: [] },
]
const previewUrl = (pid: string) => `/api/consolidation/${pid}/scope-confirmation/preview`

function mountHub() {
  // 树节点渲染与本文件无关：el-tree 只占位（其作用域插槽在未注册组件下拿不到节点数据）
  return shallowMount(ConsolidationHub, {
    global: { directives: { loading: {} }, stubs: { 'el-tree': { name: 'ElTree', render: () => null } } },
  })
}

beforeEach(() => {
  ;(trees.value as any).value = TREES
  api.get.mockReset().mockImplementation(async (url: string) => {
    if (url === previewUrl('p-1')) return { structural_change: true }
    if (url === previewUrl('p-2')) return { structural_change: false }
    throw new Error(`unexpected GET ${url}`)
  })
  api.patch.mockReset()
  confirm.mockReset().mockResolvedValue('confirm')
  Object.values(message).forEach((m) => m.mockReset())
  fetchTree.mockReset().mockResolvedValue(undefined)
})

describe('ConsolidationHub 企业树有变化提示', () => {
  it('只为有合并根项目的树静默读预览，不再请求合并范围比对；只有结构变化的树显示提示', async () => {
    const wrapper = mountHub()
    await flushPromises()
    expect(api.get.mock.calls.map((c) => c[0]).sort()).toEqual([previewUrl('p-1'), previewUrl('p-2')])
    for (const call of api.get.mock.calls) expect(call[1]).toEqual({ _silent: true })
    expect(api.get.mock.calls.some((c) => String(c[0]).includes('scope-diff'))).toBe(false)
    const tags = wrapper.findAll('[data-testid="tree-change-tag"]')
    expect(tags).toHaveLength(1)
    expect(tags[0].text()).toContain('企业树有变化')
    expect(wrapper.text()).not.toContain('合并范围差异')
  })

  it('点开提示即企业树版本弹窗（该树的合并根项目）；记录新版本后提示随回执消失', async () => {
    const wrapper = mountHub()
    await flushPromises()
    const dialog = wrapper.findComponent({ name: 'ConsolScopeConfigDialog' })
    expect(dialog.props('modelValue')).toBe(false)

    await wrapper.find('[data-testid="tree-change-tag"]').trigger('click')
    expect(dialog.props('modelValue')).toBe(true)
    expect(dialog.props('projectId')).toBe('p-1')

    dialog.vm.$emit('recorded', { structural_change: false })
    await flushPromises()
    expect(wrapper.findAll('[data-testid="tree-change-tag"]')).toHaveLength(0)
  })

  it('预览读失败：不提示、不报错，其他树照常', async () => {
    api.get.mockImplementation(async (url: string) => {
      if (url === previewUrl('p-1')) throw Object.assign(new Error('forbidden'), { response: { status: 403 } })
      return { structural_change: true }
    })
    const wrapper = mountHub()
    await flushPromises()
    expect(wrapper.findAll('[data-testid="tree-change-tag"]')).toHaveLength(1)
    expect(message.error).not.toHaveBeenCalled()
  })

  it('拖拽改上级成功后重读树与预览', async () => {
    api.patch.mockResolvedValueOnce({ synced: [], notices: [] })
    const wrapper = mountHub()
    await flushPromises()
    api.get.mockClear()
    fetchTree.mockClear()
    const drag = { data: { id: 'p-a', companyName: '甲公司', label: '甲公司', companyCode: 'A', children: [] } }
    const drop = { data: { id: 'p-n', companyName: '新上级', label: '新上级', companyCode: 'N', children: [] } }
    await (wrapper.vm as any).onNodeDrop(drag, drop, 'inner')
    await flushPromises()
    expect(fetchTree).toHaveBeenCalledWith('consolidated')
    expect(api.get.mock.calls.map((c) => c[0]).sort()).toEqual([previewUrl('p-1'), previewUrl('p-2')])
  })
})
