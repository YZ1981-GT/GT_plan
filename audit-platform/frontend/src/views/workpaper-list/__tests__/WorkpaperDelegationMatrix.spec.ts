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

// ─── Mock commonApi ──────────────────────────────────────────────────────────
vi.mock('@/services/commonApi', () => ({
  listUsers: vi.fn().mockResolvedValue([
    { id: 'u1', username: 'user1', full_name: '用户一', role: 'auditor' },
    { id: 'u2', username: 'user2', full_name: '用户二', role: 'manager' },
  ]),
}))

import WorkpaperDelegationMatrix from '../WorkpaperDelegationMatrix.vue'

describe('WorkpaperDelegationMatrix', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  function mountView(overrides: Parameters<typeof createMockContext>[0] = {}) {
    const ctx = createMockContext({
      viewMode: ref('matrix'),
      wpList: ref<WorkpaperDetail[]>([
        { id: 'wp-1', wp_index_id: 'idx-1', wp_code: 'D2-1', wp_name: '应收账款', status: 'draft', audit_cycle: 'D', assigned_to: 'u1', review_status: null, reviewer: null } as any,
      ]),
      wpIndex: ref([
        { id: 'idx-1', wp_code: 'D2-1', wp_name: '应收账款', audit_cycle: 'D' } as any,
      ]),
      loading: ref(false),
      ...overrides,
    })

    return mount(WorkpaperDelegationMatrix, {
      props: { projectId: 'test-proj', year: 2024 },
      global: {
        provide: { [WP_LIST_CONTEXT_KEY as symbol]: ctx },
        stubs: {
          InnerMatrix: {
            name: 'InnerMatrix',
            template: '<div class="inner-matrix" />',
            props: ['projectId', 'workpapers', 'members'],
            emits: ['cell-click', 'assign'],
          },
        },
      },
    })
  }

  test('默认渲染成功', async () => {
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.gt-wp-matrix-wrapper').exists()).toBe(true)
  })

  test('委派 assign 触发 mutate emit', async () => {
    const wrapper = mountView()
    await flushPromises()

    const inner = wrapper.findComponent({ name: 'InnerMatrix' })
    inner.vm.$emit('assign', { wp_ids: ['wp-1'], member_id: 'u2' })
    await flushPromises()

    const emitted = wrapper.emitted('mutate')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({
      action: 'batchAssign',
      data: { wp_ids: ['wp-1'], member_id: 'u2' },
    })
  })

  test('onMounted 加载成员列表', async () => {
    const wrapper = mountView()
    await flushPromises()

    // listUsers 应该被调用
    const { listUsers } = await import('@/services/commonApi')
    expect(listUsers).toHaveBeenCalledWith('test-proj')
  })
})
