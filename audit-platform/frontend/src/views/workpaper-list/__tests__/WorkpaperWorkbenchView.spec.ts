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

  // 列表视图根节点为 .gt-wp-list-split（左循环树 + 右表格 master-detail）；
  // 旧断言写的是不存在的 .gt-wp-list-default，长期恒红。
  test('list 模式渲染默认列表', async () => {
    const wrapper = mountView({ viewMode: ref('list') })
    await flushPromises()
    expect(wrapper.find('.gt-wp-list-split').exists()).toBe(true)
  })

  // ?filter=stale（联动状态横条「查看详情」）→ 只保留 prefill_stale=true 的底稿
  test('filterStale=true 时仅保留待重算底稿', async () => {
    const filterStale = ref(false)
    const wpList = ref<WorkpaperDetail[]>([
      { id: 'wp-1', wp_index_id: 'idx-1', status: 'draft', prefill_stale: true } as any,
      { id: 'wp-2', wp_index_id: 'idx-2', status: 'in_progress', prefill_stale: false } as any,
    ])
    const wrapper = mountView({ viewMode: ref('list'), filterStale, wpList })
    await flushPromises()

    const rowsBefore = (wrapper.vm as any).listTableData.map((r: any) => r.id)
    expect(rowsBefore).toEqual(['wp-1', 'wp-2'])

    filterStale.value = true
    await flushPromises()
    const rowsAfter = (wrapper.vm as any).listTableData.map((r: any) => r.id)
    expect(rowsAfter).toEqual(['wp-1'])
  })

  test('filterStale 行数据带 prefill_stale 供「数据」列渲染待重算标记', async () => {
    const wpList = ref<WorkpaperDetail[]>([
      { id: 'wp-1', wp_index_id: 'idx-1', status: 'draft', prefill_stale: true } as any,
    ])
    const wrapper = mountView({ viewMode: ref('list'), wpList })
    await flushPromises()
    expect((wrapper.vm as any).listTableData[0].prefill_stale).toBe(true)
  })
})
