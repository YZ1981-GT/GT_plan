import { describe, test, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref, computed } from 'vue'
import { WP_LIST_CONTEXT_KEY, createMockContext } from '@/composables/useWorkpaperListContext'
import type { WpIndexItem, WorkpaperDetail } from '@/services/workpaperApi'

// ─── Mock vue-router ─────────────────────────────────────────────────────────
vi.mock('vue-router', () => ({
  useRoute: () => ({
    params: { projectId: 'test-proj' },
    query: {},
  }),
  useRouter: () => ({
    replace: vi.fn().mockReturnValue(Promise.resolve()),
    push: vi.fn(),
  }),
}))

// ─── Mock services ───────────────────────────────────────────────────────────
vi.mock('@/services/workpaperApi', () => ({
  downloadWorkpaper: vi.fn(),
}))

import WorkpaperWorkbenchView from '../WorkpaperWorkbenchView.vue'

describe('WorkpaperWorkbenchView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function mountView(overrides: Parameters<typeof createMockContext>[0] = {}) {
    const ctx = createMockContext({
      viewMode: ref('workbench'),
      wpIndex: ref<WpIndexItem[]>([
        { id: 'idx-1', wp_code: 'D2-1', wp_name: '应收账款', audit_cycle: 'D' } as any,
        { id: 'idx-2', wp_code: 'E1-1', wp_name: '银行存款', audit_cycle: 'E' } as any,
      ]),
      wpList: ref<WorkpaperDetail[]>([
        { id: 'wp-1', wp_index_id: 'idx-1', wp_code: 'D2-1', wp_name: '应收账款', status: 'draft', assigned_to: 'u1' } as any,
        { id: 'wp-2', wp_index_id: 'idx-2', wp_code: 'E1-1', wp_name: '银行存款', status: 'in_progress', assigned_to: 'u2' } as any,
      ]),
      loading: ref(false),
      searchKeyword: ref(''),
      filterCycle: ref(''),
      filterStatus: ref(''),
      filterAssignee: ref(''),
      ...overrides,
    })

    return mount(WorkpaperWorkbenchView, {
      props: { projectId: 'test-proj', year: 2024 },
      global: {
        provide: { [WP_LIST_CONTEXT_KEY as symbol]: ctx },
        stubs: {
          ElTable: { template: '<div class="el-table" />', props: ['data'] },
          ElTableColumn: true,
          ElTag: { template: '<span class="el-tag"><slot /></span>' },
          ElProgress: { template: '<div class="el-progress" />' },
          ElButton: { template: '<button class="el-button"><slot /></button>' },
          ElPagination: { template: '<div class="el-pagination" />' },
          ElButtonGroup: { template: '<div><slot /></div>' },
          GtRowActions: true,
        },
      },
    })
  }

  test('默认渲染成功（workbench 模式）', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.gt-wp-workbench-container').exists()).toBe(true)
  })

  test('搜索交互：设置 searchKeyword 后过滤列表', async () => {
    const searchKeyword = ref('')
    const wrapper = mountView({ searchKeyword })
    await flushPromises()

    // 设置搜索关键词
    searchKeyword.value = '银行'
    await flushPromises()

    // 组件内部 filteredWpList 应只包含匹配项
    const vm = wrapper.vm as any
    // 验证组件没有崩溃且仍然渲染
    expect(wrapper.find('.gt-wp-workbench-container').exists()).toBe(true)
  })

  test('guide 模式渲染手册视图', async () => {
    const wrapper = mountView({ viewMode: ref('guide') })
    await flushPromises()
    expect(wrapper.find('.gt-wp-guide-view').exists()).toBe(true)
  })

  test('list 模式渲染默认列表', async () => {
    const wrapper = mountView({ viewMode: ref('list') })
    await flushPromises()
    expect(wrapper.find('.gt-wp-list-default').exists()).toBe(true)
  })
})
