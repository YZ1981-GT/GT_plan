import { describe, test, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
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
    setActivePinia(createPinia())
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
        plugins: [createPinia()],
        provide: { [WP_LIST_CONTEXT_KEY as symbol]: ctx },
        stubs: {
          InnerMatrix: {
            name: 'InnerMatrix',
            template: '<div class="inner-matrix" />',
            props: ['projectId', 'workpapers', 'members', 'canAssign'],
            emits: ['cell-click', 'open-assign'],
          },
          BatchAssignDialog: {
            name: 'BatchAssignDialog',
            template: '<div class="batch-assign-dialog" />',
            props: ['modelValue', 'projectId', 'wpIds', 'wpList'],
            emits: ['update:modelValue', 'assigned'],
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

  test('open-assign 打开委派弹窗并传入 wp-ids（不再直接 POST）', async () => {
    const wrapper = mountView()
    await flushPromises()

    const dialog = wrapper.findComponent({ name: 'BatchAssignDialog' })
    // 初始隐藏
    expect(dialog.props('modelValue')).toBe(false)

    const inner = wrapper.findComponent({ name: 'InnerMatrix' })
    inner.vm.$emit('open-assign', { wp_ids: ['wp-1'] })
    await flushPromises()

    // 弹窗打开且携带待委派 wp_ids；不应触发直接 batchAssign mutate
    expect(dialog.props('modelValue')).toBe(true)
    expect(dialog.props('wpIds')).toEqual(['wp-1'])
    expect(wrapper.emitted('mutate')).toBeFalsy()
  })

  test('open-assign 传入空 wp_ids 不打开弹窗', async () => {
    const wrapper = mountView()
    await flushPromises()

    const inner = wrapper.findComponent({ name: 'InnerMatrix' })
    inner.vm.$emit('open-assign', { wp_ids: [] })
    await flushPromises()

    const dialog = wrapper.findComponent({ name: 'BatchAssignDialog' })
    expect(dialog.props('modelValue')).toBe(false)
  })

  test('canAssign 依角色计算并传入矩阵（无角色→只读）', async () => {
    const wrapper = mountView()
    await flushPromises()
    // 测试环境无登录角色 → 非 delegator → canAssign=false（只读矩阵）
    const inner = wrapper.findComponent({ name: 'InnerMatrix' })
    expect(inner.props('canAssign')).toBe(false)
  })

  test('assigned 事件触发矩阵刷新', async () => {
    const fetchWpIndex = vi.fn().mockResolvedValue(undefined)
    const wrapper = mountView({ fetchWpIndex })
    await flushPromises()

    const dialog = wrapper.findComponent({ name: 'BatchAssignDialog' })
    dialog.vm.$emit('assigned', { updated: 1, notifications_sent: 1, message: 'ok' })
    await flushPromises()

    expect(fetchWpIndex).toHaveBeenCalled()
  })

  test('onMounted 加载成员列表', async () => {
    const wrapper = mountView()
    await flushPromises()

    // listUsers 应该被调用
    const { listUsers } = await import('@/services/commonApi')
    expect(listUsers).toHaveBeenCalledWith('test-proj')
  })
})
