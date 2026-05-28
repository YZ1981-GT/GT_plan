import { describe, test, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { WP_LIST_CONTEXT_KEY, createMockContext } from '@/composables/useWorkpaperListContext'
import type { WorkpaperDetail } from '@/services/workpaperApi'

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

import WorkpaperLifecycleView from '../WorkpaperLifecycleView.vue'

describe('WorkpaperLifecycleView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function mountView(overrides: Parameters<typeof createMockContext>[0] = {}) {
    const ctx = createMockContext({
      viewMode: ref('lifecycle'),
      wpList: ref<WorkpaperDetail[]>([
        { id: 'wp-1', wp_index_id: 'idx-1', wp_code: 'D2-1', wp_name: '应收账款', status: 'draft', audit_cycle: 'D', assigned_to: 'u1', review_status: null, reviewer: null } as any,
      ]),
      wpIndex: ref([
        { id: 'idx-1', wp_code: 'D2-1', wp_name: '应收账款', audit_cycle: 'D' } as any,
      ]),
      loading: ref(false),
      ...overrides,
    })

    return mount(WorkpaperLifecycleView, {
      props: { projectId: 'test-proj', year: 2024 },
      global: {
        provide: { [WP_LIST_CONTEXT_KEY as symbol]: ctx },
        stubs: {
          InnerLifecycle: {
            name: 'InnerLifecycle',
            template: '<div class="inner-lifecycle" />',
            props: ['projectId', 'workpapers', 'loading'],
            emits: ['switch-view', 'open-workpaper', 'refresh'],
          },
        },
      },
    })
  }

  test('默认渲染成功', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.gt-wp-lifecycle-wrapper').exists()).toBe(true)
  })

  test('open-workpaper 触发 navigate emit', async () => {
    const wrapper = mountView()
    await flushPromises()

    const inner = wrapper.findComponent({ name: 'InnerLifecycle' })
    inner.vm.$emit('open-workpaper', 'wp-1')
    await flushPromises()

    const emitted = wrapper.emitted('navigate')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toBe('wp-1')
  })

  test('refresh 触发 refresh emit', async () => {
    const wrapper = mountView()
    await flushPromises()

    const inner = wrapper.findComponent({ name: 'InnerLifecycle' })
    inner.vm.$emit('refresh')
    await flushPromises()

    const emitted = wrapper.emitted('refresh')
    expect(emitted).toBeTruthy()
  })

  test('switch-view 修改 ctx.viewMode', async () => {
    const viewMode = ref('lifecycle')
    const wrapper = mountView({ viewMode })
    await flushPromises()

    const inner = wrapper.findComponent({ name: 'InnerLifecycle' })
    inner.vm.$emit('switch-view', 'kanban')
    await flushPromises()

    expect(viewMode.value).toBe('kanban')
  })
})
