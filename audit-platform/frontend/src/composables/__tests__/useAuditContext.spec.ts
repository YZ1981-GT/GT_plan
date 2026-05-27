/**
 * useAuditContext — 单测
 * 覆盖 Req 5（横切组件 1）：审计上下文 composable
 *
 * 测试点：
 * 1. projectId / year / applicableStandard 响应式读取
 * 2. isArchived 根据 projectStatus 派生
 * 3. canEdit = !isArchived && canEditInProject
 * 4. onContextChange 回调注册 + 取消
 * 5. route 变化触发 audit-context:changed 事件（50ms debounce）
 * 6. irrelevant 选项跳过事件监听
 * 7. year 三级 fallback（projectStore.year || route.query.year || currentYear - 1）
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, reactive } from 'vue'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { useProjectStore } from '@/stores/project'
import { useAuditContext, DEBOUNCE_MS } from '../useAuditContext'
import { eventBus } from '@/utils/eventBus'

// ─── Mock vue-router（reactive 以便 watch 能检测变化） ───
const mockRoute = reactive({
  params: { projectId: 'proj-001' } as Record<string, string>,
  query: { year: '2024' } as Record<string, string>,
})

vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
}))

// ─── Mock roleContext store ───
const mockRoleContext = reactive({
  canEditInProject: true,
})

vi.mock('@/stores/roleContext', () => ({
  useRoleContextStore: () => mockRoleContext,
}))

// ─── Mock services（避免真实 API 调用） ───
vi.mock('@/services/auditPlatformApi', () => ({
  getProject: vi.fn().mockResolvedValue({ id: 'proj-001', client_name: '测试客户' }),
  getProjectAuditYear: vi.fn().mockResolvedValue(2024),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue([]) },
}))

let testPinia: Pinia

/** Helper：在 setup 中调用 composable 并返回结果 */
function withSetup<T>(composable: () => T): { result: T; wrapper: ReturnType<typeof mount> } {
  let result!: T
  const Comp = defineComponent({
    setup() {
      result = composable()
      return {}
    },
    template: '<div />',
  })
  const wrapper = mount(Comp, {
    global: {
      plugins: [testPinia],
    },
  })
  return { result, wrapper }
}

describe('useAuditContext — Req 5 审计上下文 composable', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    testPinia = createPinia()
    setActivePinia(testPinia)
    // 重置 mock route
    mockRoute.params.projectId = 'proj-001'
    mockRoute.query.year = '2024'
    mockRoleContext.canEditInProject = true
  })

  afterEach(() => {
    vi.useRealTimers()
    eventBus.all.clear()
  })

  it('DEBOUNCE_MS 常量等于 50', () => {
    expect(DEBOUNCE_MS).toBe(50)
  })

  describe('响应式状态读取', () => {
    it('projectId 从 projectStore 读取', () => {
      const store = useProjectStore()
      store.projectId = 'proj-abc'

      const { result, wrapper } = withSetup(() => useAuditContext())
      expect(result.projectId.value).toBe('proj-abc')
      wrapper.unmount()
    })

    it('projectId fallback 到 route.params.projectId', () => {
      const store = useProjectStore()
      store.projectId = '' // 空值触发 fallback

      const { result, wrapper } = withSetup(() => useAuditContext())
      expect(result.projectId.value).toBe('proj-001')
      wrapper.unmount()
    })

    it('year 从 projectStore 读取（优先级最高）', () => {
      const store = useProjectStore()
      store.year = 2023

      const { result, wrapper } = withSetup(() => useAuditContext())
      expect(result.year.value).toBe(2023)
      wrapper.unmount()
    })

    it('year fallback 到 route.query.year', () => {
      mockRoute.query.year = '2022'
      const store = useProjectStore()
      store.year = 0 // falsy 触发 fallback

      const { result, wrapper } = withSetup(() => useAuditContext())
      expect(result.year.value).toBe(2022)
      wrapper.unmount()
    })

    it('year 最终 fallback 到 currentYear - 1', () => {
      mockRoute.query.year = ''
      const store = useProjectStore()
      store.year = 0

      const { result, wrapper } = withSetup(() => useAuditContext())
      expect(result.year.value).toBe(new Date().getFullYear() - 1)
      wrapper.unmount()
    })

    it('applicableStandard 从 projectStore.standard 读取', () => {
      const store = useProjectStore()
      store.standard = 'listed'

      const { result, wrapper } = withSetup(() => useAuditContext())
      expect(result.applicableStandard.value).toBe('listed')
      wrapper.unmount()
    })
  })

  describe('isArchived 派生状态', () => {
    it('projectStatus === "archived" 时 isArchived 为 true', () => {
      const store = useProjectStore()
      store.projectStatus = 'archived'

      const { result, wrapper } = withSetup(() => useAuditContext())
      expect(result.isArchived.value).toBe(true)
      wrapper.unmount()
    })

    it('projectStatus !== "archived" 时 isArchived 为 false', () => {
      const store = useProjectStore()
      store.projectStatus = 'execution'

      const { result, wrapper } = withSetup(() => useAuditContext())
      expect(result.isArchived.value).toBe(false)
      wrapper.unmount()
    })

    it('projectStatus 为空字符串时 isArchived 为 false', () => {
      const store = useProjectStore()
      store.projectStatus = ''

      const { result, wrapper } = withSetup(() => useAuditContext())
      expect(result.isArchived.value).toBe(false)
      wrapper.unmount()
    })
  })

  describe('canEdit 派生状态', () => {
    it('非归档 + 有编辑权限 → canEdit = true', () => {
      mockRoleContext.canEditInProject = true
      const store = useProjectStore()
      store.projectStatus = 'execution'

      const { result, wrapper } = withSetup(() => useAuditContext())
      expect(result.canEdit.value).toBe(true)
      wrapper.unmount()
    })

    it('归档项目 → canEdit = false（即使有编辑权限）', () => {
      mockRoleContext.canEditInProject = true
      const store = useProjectStore()
      store.projectStatus = 'archived'

      const { result, wrapper } = withSetup(() => useAuditContext())
      expect(result.canEdit.value).toBe(false)
      wrapper.unmount()
    })

    it('非归档但无编辑权限 → canEdit = false', () => {
      mockRoleContext.canEditInProject = false
      const store = useProjectStore()
      store.projectStatus = 'execution'

      const { result, wrapper } = withSetup(() => useAuditContext())
      expect(result.canEdit.value).toBe(false)
      wrapper.unmount()
    })
  })

  describe('onContextChange 回调', () => {
    it('注册回调后路由变化时被调用（debounce 后）', async () => {
      const store = useProjectStore()
      store.projectId = 'proj-001'
      store.year = 2024

      const cb = vi.fn()
      const { wrapper } = withSetup(() => {
        const ctx = useAuditContext()
        ctx.onContextChange(cb)
        return ctx
      })

      // 模拟路由变化
      mockRoute.params.projectId = 'proj-002'
      await nextTick()
      await nextTick() // flush: 'post' 需要额外 tick
      // debounce 未到，回调不应被调用
      expect(cb).not.toHaveBeenCalled()

      // 推进 debounce 时间
      vi.advanceTimersByTime(DEBOUNCE_MS)
      expect(cb).toHaveBeenCalledWith({
        projectId: expect.any(String),
        year: expect.any(Number),
      })
      wrapper.unmount()
    })

    it('取消注册后不再被调用', async () => {
      const store = useProjectStore()
      store.projectId = 'proj-001'
      store.year = 2024

      const cb = vi.fn()
      const { wrapper } = withSetup(() => {
        const ctx = useAuditContext()
        const unregister = ctx.onContextChange(cb)
        unregister() // 立即取消
        return ctx
      })

      mockRoute.params.projectId = 'proj-003'
      await nextTick()
      await nextTick()
      vi.advanceTimersByTime(DEBOUNCE_MS)
      expect(cb).not.toHaveBeenCalled()
      wrapper.unmount()
    })

    it('多个回调都被调用', async () => {
      const store = useProjectStore()
      store.projectId = 'proj-001'
      store.year = 2024

      const cb1 = vi.fn()
      const cb2 = vi.fn()
      const { wrapper } = withSetup(() => {
        const ctx = useAuditContext()
        ctx.onContextChange(cb1)
        ctx.onContextChange(cb2)
        return ctx
      })

      mockRoute.params.projectId = 'proj-004'
      await nextTick()
      await nextTick()
      vi.advanceTimersByTime(DEBOUNCE_MS)
      expect(cb1).toHaveBeenCalled()
      expect(cb2).toHaveBeenCalled()
      wrapper.unmount()
    })

    it('回调异常不影响其他回调执行', async () => {
      const store = useProjectStore()
      store.projectId = 'proj-001'
      store.year = 2024

      const cb1 = vi.fn(() => { throw new Error('test error') })
      const cb2 = vi.fn()
      const { wrapper } = withSetup(() => {
        const ctx = useAuditContext()
        ctx.onContextChange(cb1)
        ctx.onContextChange(cb2)
        return ctx
      })

      mockRoute.params.projectId = 'proj-005'
      await nextTick()
      await nextTick()
      vi.advanceTimersByTime(DEBOUNCE_MS)
      expect(cb1).toHaveBeenCalled()
      expect(cb2).toHaveBeenCalled()
      wrapper.unmount()
    })
  })

  describe('audit-context:changed 事件', () => {
    it('路由变化后 50ms debounce 触发事件', async () => {
      const store = useProjectStore()
      store.projectId = 'proj-001'
      store.year = 2024
      store.standard = 'soe'

      const handler = vi.fn()
      eventBus.on('audit-context:changed', handler)

      const { wrapper } = withSetup(() => useAuditContext())

      mockRoute.params.projectId = 'proj-new'
      await nextTick()
      await nextTick()

      // debounce 期间不触发
      expect(handler).not.toHaveBeenCalled()

      vi.advanceTimersByTime(DEBOUNCE_MS)
      expect(handler).toHaveBeenCalledTimes(1)
      expect(handler).toHaveBeenCalledWith(
        expect.objectContaining({
          projectId: expect.any(String),
          year: expect.any(Number),
          applicableStandard: expect.any(String),
          before: expect.objectContaining({
            projectId: expect.any(String),
            year: expect.any(Number),
            applicableStandard: expect.any(String),
          }),
        })
      )

      eventBus.off('audit-context:changed', handler)
      wrapper.unmount()
    })

    it('debounce 合并：50ms 内多次变化只触发一次', async () => {
      const store = useProjectStore()
      store.projectId = 'proj-001'
      store.year = 2024

      const handler = vi.fn()
      eventBus.on('audit-context:changed', handler)

      const { wrapper } = withSetup(() => useAuditContext())

      // 快速连续变化
      mockRoute.params.projectId = 'proj-a'
      await nextTick()
      await nextTick()
      vi.advanceTimersByTime(20)

      mockRoute.params.projectId = 'proj-b'
      await nextTick()
      await nextTick()
      vi.advanceTimersByTime(20)

      mockRoute.params.projectId = 'proj-c'
      await nextTick()
      await nextTick()

      // 此时距最后一次变化还不到 50ms
      expect(handler).not.toHaveBeenCalled()

      vi.advanceTimersByTime(DEBOUNCE_MS)
      expect(handler).toHaveBeenCalledTimes(1)

      eventBus.off('audit-context:changed', handler)
      wrapper.unmount()
    })
  })

  describe('irrelevant 选项', () => {
    it('irrelevant: true 时路由变化不触发事件', async () => {
      const store = useProjectStore()
      store.projectId = 'proj-001'
      store.year = 2024

      const handler = vi.fn()
      eventBus.on('audit-context:changed', handler)

      const { result, wrapper } = withSetup(() => useAuditContext({ irrelevant: true }))

      mockRoute.params.projectId = 'proj-new'
      await nextTick()
      await nextTick()
      vi.advanceTimersByTime(DEBOUNCE_MS * 2)

      expect(handler).not.toHaveBeenCalled()

      // 但响应式状态仍然可读
      expect(result.projectId.value).toBeDefined()
      expect(result.year.value).toBeDefined()

      eventBus.off('audit-context:changed', handler)
      wrapper.unmount()
    })

    it('irrelevant: true 时 onContextChange 回调不被触发', async () => {
      const store = useProjectStore()
      store.projectId = 'proj-001'
      store.year = 2024

      const cb = vi.fn()
      const { wrapper } = withSetup(() => {
        const ctx = useAuditContext({ irrelevant: true })
        ctx.onContextChange(cb)
        return ctx
      })

      mockRoute.params.projectId = 'proj-new'
      await nextTick()
      await nextTick()
      vi.advanceTimersByTime(DEBOUNCE_MS * 2)

      expect(cb).not.toHaveBeenCalled()
      wrapper.unmount()
    })
  })
})
