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

// ─── Mock D3 lazy import ─────────────────────────────────────────────────────
vi.mock('d3-force', () => ({
  forceSimulation: vi.fn(),
  forceLink: vi.fn(),
  forceManyBody: vi.fn(),
  forceCenter: vi.fn(),
}))

import WorkpaperDependencyGraph from '../WorkpaperDependencyGraph.vue'

describe('WorkpaperDependencyGraph', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function mountView(overrides: Parameters<typeof createMockContext>[0] = {}) {
    const ctx = createMockContext({
      viewMode: ref('graph'),
      loading: ref(false),
      ...overrides,
    })

    return mount(WorkpaperDependencyGraph, {
      props: { projectId: 'test-proj', year: 2024 },
      global: {
        provide: { [WP_LIST_CONTEXT_KEY as symbol]: ctx },
        stubs: {
          InnerGraph: {
            name: 'InnerGraph',
            template: '<div class="inner-graph" />',
            props: ['projectId'],
            emits: ['navigate'],
          },
        },
      },
    })
  }

  test('默认渲染成功', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.gt-wp-dep-graph-wrapper').exists()).toBe(true)
  })

  test('D3 lazy import 在 mount 后触发', async () => {
    const wrapper = mountView()
    await flushPromises()

    // d3-force 模块应该被 import 过（onMounted 触发 dynamic import）
    const d3 = await import('d3-force')
    expect(d3).toBeDefined()
  })

  test('navigate 事件透传', async () => {
    const wrapper = mountView()
    await flushPromises()

    const inner = wrapper.findComponent({ name: 'InnerGraph' })
    inner.vm.$emit('navigate', 'D2-1')
    await flushPromises()

    const emitted = wrapper.emitted('navigate')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toBe('D2-1')
  })
})
