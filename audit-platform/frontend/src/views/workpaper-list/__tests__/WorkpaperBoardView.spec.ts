import { describe, test, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { WP_LIST_CONTEXT_KEY, createMockContext } from '@/composables/useWorkpaperListContext'

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

import WorkpaperBoardView from '../WorkpaperBoardView.vue'

describe('WorkpaperBoardView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function mountView(overrides: Parameters<typeof createMockContext>[0] = {}) {
    const ctx = createMockContext({
      viewMode: ref('kanban'),
      filterCycle: ref(''),
      loading: ref(false),
      ...overrides,
    })

    return mount(WorkpaperBoardView, {
      props: { projectId: 'test-proj', year: 2024 },
      global: {
        provide: { [WP_LIST_CONTEXT_KEY as symbol]: ctx },
        stubs: {
          InnerKanban: {
            name: 'InnerKanban',
            template: '<div class="inner-kanban" />',
            props: ['projectId', 'auditCycle'],
            emits: ['select', 'assign'],
          },
        },
      },
    })
  }

  test('默认渲染成功', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.gt-wp-board-wrapper').exists()).toBe(true)
  })

  test('看板委派触发 mutate emit', async () => {
    const wrapper = mountView()
    await flushPromises()

    // 模拟 InnerKanban 触发 assign 事件
    const kanban = wrapper.findComponent({ name: 'InnerKanban' })
    kanban.vm.$emit('assign', { wp_id: 'wp-1', wp_code: 'D2-1', wp_name: '应收账款' })
    await flushPromises()

    const emitted = wrapper.emitted('mutate')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({
      action: 'assign',
      data: { wp_id: 'wp-1', wp_code: 'D2-1', wp_name: '应收账款' },
    })
  })

  test('看板选择触发 navigate emit', async () => {
    const wrapper = mountView()
    await flushPromises()

    const kanban = wrapper.findComponent({ name: 'InnerKanban' })
    kanban.vm.$emit('select', { wp_id: 'wp-1', id: 'wp-1' })
    await flushPromises()

    const emitted = wrapper.emitted('navigate')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toBe('wp-1')
  })
})
