import { describe, test, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import { ref, computed } from 'vue'
import { EDITOR_CONTEXT_KEY, createMockEditorContext } from '@/composables/useEditorContext'

// ─── Mock services ───────────────────────────────────────────────────────────
const mockGet = vi.fn().mockResolvedValue([])

vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))

vi.mock('@/services/apiPaths', () => ({
  workpapers: { versions: (wpId: string) => `/api/workpapers/${wpId}/versions` },
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

// ─── Mock child components ───────────────────────────────────────────────────
vi.mock('@/components/workpaper/VersionHistorySearch.vue', () => ({
  default: { name: 'VersionHistorySearch', template: '<div class="stub-version-search" />' },
}))

// ─── Import component ────────────────────────────────────────────────────────
import VersionHistoryDrawer from '@/views/workpaper-editor/VersionHistoryDrawer.vue'

describe('VersionHistoryDrawer', () => {
  function mountComponent(props: Partial<InstanceType<typeof VersionHistoryDrawer>['$props']> = {}) {
    const ctx = createMockEditorContext()
    return shallowMount(VersionHistoryDrawer, {
      props: {
        wpId: 'wp-1',
        visible: false,
        ...props,
      },
      global: {
        provide: { [EDITOR_CONTEXT_KEY as symbol]: ctx },
        stubs: {
          ElDrawer: {
            template: '<div class="el-drawer-stub"><slot /></div>',
            props: ['modelValue', 'title'],
          },
          ElDivider: { template: '<hr />' },
          ElEmpty: { template: '<div class="el-empty-stub">{{ description }}</div>', props: ['description'] },
          ElTimeline: { template: '<div class="el-timeline-stub"><slot /></div>' },
          ElTimelineItem: { template: '<div class="el-timeline-item-stub"><slot /></div>' },
        },
        directives: {
          loading: () => { /* noop */ },
        },
      },
    })
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('默认渲染：visible=false 时抽屉渲染但不加载数据', async () => {
    const wrapper = mountComponent({ visible: false })
    await flushPromises()

    // 组件应渲染
    expect(wrapper.find('.el-drawer-stub').exists()).toBe(true)
    // 不应调用版本列表 API（visible=false）
    expect(mockGet).not.toHaveBeenCalled()
  })

  test('visible=true 时触发版本列表加载', async () => {
    const mockVersions = [
      { id: 'v1', version: 1, created_at: '2026-05-20T10:00:00Z', note: '初始版本' },
      { id: 'v2', version: 2, created_at: '2026-05-25T14:00:00Z', note: '更新数据' },
    ]
    mockGet.mockResolvedValueOnce(mockVersions)

    const wrapper = mountComponent({ visible: false })
    await flushPromises()

    // 切换 visible=true → 触发加载
    await wrapper.setProps({ visible: true })
    await flushPromises()

    // 应调用版本列表 API
    expect(mockGet).toHaveBeenCalledWith(
      '/api/workpapers/wp-1/versions',
      expect.any(Object),
    )
  })
})
