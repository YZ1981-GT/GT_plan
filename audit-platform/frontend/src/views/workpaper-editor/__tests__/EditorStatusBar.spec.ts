import { describe, test, expect, vi, beforeEach } from 'vitest'
import { shallowMount, flushPromises } from '@vue/test-utils'
import { ref, computed } from 'vue'
import { EDITOR_CONTEXT_KEY, createMockEditorContext } from '@/composables/useEditorContext'

// ─── Mock services ───────────────────────────────────────────────────────────
vi.mock('@/services/commonApi', () => ({
  listUsers: vi.fn().mockResolvedValue([]),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue({}) },
}))

vi.mock('@/services/apiPaths', () => ({
  workpapers: { wpMappingTsj: vi.fn().mockReturnValue('/api/mock') },
}))

// ─── Import component ────────────────────────────────────────────────────────
import EditorStatusBar from '@/views/workpaper-editor/EditorStatusBar.vue'

describe('EditorStatusBar', () => {
  const mockWpDetail = {
    id: 'wp-1',
    project_id: 'proj-1',
    wp_code: 'D2-1',
    wp_name: '应收账款审定表',
    assigned_to: 'user-1',
    reviewer: 'user-2',
    file_version: 3,
    updated_at: '2026-05-28T10:30:00.000Z',
    status: 'draft',
  }

  function mountComponent(props: Partial<InstanceType<typeof EditorStatusBar>['$props']> = {}) {
    const ctx = createMockEditorContext()
    return shallowMount(EditorStatusBar, {
      props: {
        wpDetail: mockWpDetail as any,
        dirty: false,
        autoSaveMsg: '',
        smartTip: null,
        ...props,
      },
      global: {
        provide: { [EDITOR_CONTEXT_KEY as symbol]: ctx },
        stubs: {
          ElButton: { template: '<button @click="$emit(\'click\')"><slot /></button>' },
        },
      },
    })
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('默认渲染：显示状态栏基本信息', async () => {
    const wrapper = mountComponent()
    await flushPromises()

    const text = wrapper.text()
    // 状态栏应包含版本信息
    expect(text).toContain('v3')
    // 状态栏应包含最后修改时间
    expect(text).toContain('2026-05-28T10:30:00')
  })

  test('智能提示展开/收起交互', async () => {
    const smartTip = {
      summary: '高风险科目',
      warnings: ['应收账款余额异常增长'],
      tips: ['关注账龄分析', '核实大额客户'],
    }

    const wrapper = mountComponent({ smartTip })
    await flushPromises()

    // 智能提示摘要应显示
    expect(wrapper.text()).toContain('高风险科目')

    // 详情区域默认不显示
    expect(wrapper.find('.gt-wp-smart-tip-detail').exists()).toBe(false)

    // 点击智能提示摘要 → 展开详情
    await wrapper.find('.gt-wp-smart-tip').trigger('click')
    expect(wrapper.find('.gt-wp-smart-tip-detail').exists()).toBe(true)
    expect(wrapper.text()).toContain('应收账款余额异常增长')
    expect(wrapper.text()).toContain('关注账龄分析')

    // 再次点击 → 收起详情
    await wrapper.find('.gt-wp-smart-tip').trigger('click')
    expect(wrapper.find('.gt-wp-smart-tip-detail').exists()).toBe(false)
  })
})
