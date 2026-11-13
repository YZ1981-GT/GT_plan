/**
 * 「合并」总览顶部「下属企业」数：不把集团根节点算进去。
 *
 * 后端 group_forest 在集团本身有项目时把根企业放在 children[0]，totalTreeNodes 因此含根节点。
 * 2026-11-09 浏览器实测：两棵树（甲集团 + 1 家下属、乙集团无下属）旧实现显示 3，应为 1。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'

const { state } = vi.hoisted(() => ({ state: { trees: null as any, total: null as any } }))

vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({}), post: vi.fn(), patch: vi.fn() } }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
  ElNotification: vi.fn(),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/components/wizard/BatchImportDialog.vue', () => ({ default: { name: 'BatchImportDialog', render: () => null } }))
vi.mock('@/components/wizard/ConsolScopeConfigDialog.vue', () => ({ default: { name: 'ConsolScopeConfigDialog', render: () => null } }))
vi.mock('@/composables/useGroupTree', async () => {
  const { ref, computed } = await import('vue')
  state.trees = ref<any[]>([])
  state.total = ref(0)
  return {
    useGroupTree: () => ({
      trees: state.trees, independents: ref([]), loading: ref(false), error: ref(null), searchQuery: ref(''),
      hasTrees: computed(() => state.trees.value.length > 0), totalTreeNodes: computed(() => state.total.value),
      hasSearchMatch: computed(() => true), fetchTree: vi.fn().mockResolvedValue(undefined), filterNode: () => true,
    }),
    highlightSegments: () => [], consolMethodLabel: () => '', formatShareholding: () => '', countConsolMethods: () => ({}),
  }
})

import ConsolidationHub from '../ConsolidationHub.vue'

function statOf(wrapper: ReturnType<typeof shallowMount>, label: string): string | undefined {
  const item = wrapper.findAll('.ch-stat-item').find((i) => i.find('.ch-stat-label').text() === label)
  return item?.find('.ch-stat-num').text()
}

async function mountWith(trees: any[], total: number) {
  state.trees.value = trees
  state.total.value = total
  const wrapper = shallowMount(ConsolidationHub, {
    global: { directives: { loading: {} }, stubs: { 'el-tree': { name: 'ElTree', render: () => null } } },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  if (state.trees) state.trees.value = []
})

describe('ConsolidationHub 下属企业数', () => {
  it('有合并根项目的树扣掉根节点（实测形状：2 棵有根树、共 3 个节点 ⇒ 1）', async () => {
    const w = await mountWith([
      { key: 'a', ultimateCode: 'A', rootProjectId: 'p-a', children: [] },
      { key: 'b', ultimateCode: 'B', rootProjectId: 'p-b', children: [] },
    ], 3)
    expect(statOf(w, '下属企业')).toBe('1')
  })

  it('无根树（控制方本年度没有项目）不扣：节点全是下属企业', async () => {
    const w = await mountWith([{ key: 'c', ultimateCode: 'C', rootProjectId: null, children: [] }], 2)
    expect(statOf(w, '下属企业')).toBe('2')
  })
})
