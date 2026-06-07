/**
 * Tests for project store — P0-2 ProjectContext & P0-3 年度切换协议
 *
 * 验证:
 * - P0-2.1/2.2: currentProjectContext computed 暴露全部字段
 * - P0-2.4: resetProjectScopedState 清空旧项目状态
 * - P0-2.5: 项目切换后旧 projectId 相关 state 清空
 * - P0-3.1: setCurrentYear(year, { reload: true }) 年度切换协议
 * - P0-3.2: 年度切换时清理缓存
 * - P0-3.3: 停止旧年度 SSE 订阅并重建
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useProjectStore } from '@/stores/project'

// Mock API calls
vi.mock('@/services/auditPlatformApi', () => ({
  getProject: vi.fn().mockResolvedValue({ client_name: 'Test Corp', status: 'active' }),
  getProjectAuditYear: vi.fn().mockResolvedValue(2025),
}))

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue({ items: [] }) },
}))

// Mock eventBus
const emitSpy = vi.fn()
vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: (...args: any[]) => emitSpy(...args) },
}))

describe('project store - P0-2 ProjectContext facade', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    emitSpy.mockClear()
  })

  describe('P0-2.1/2.2: currentProjectContext computed', () => {
    it('should expose all required fields', () => {
      const store = useProjectStore()
      const ctx = store.currentProjectContext

      expect(ctx).toHaveProperty('projectId')
      expect(ctx).toHaveProperty('projectName')
      expect(ctx).toHaveProperty('year')
      expect(ctx).toHaveProperty('applicableStandard')
      expect(ctx).toHaveProperty('auditScope')
      expect(ctx).toHaveProperty('projectStatus')
      expect(ctx).toHaveProperty('roleInProject')
    })

    it('should reflect store state', () => {
      const store = useProjectStore()
      store.projectId = 'proj-123'
      store.clientName = 'ABC 公司'
      store.year = 2025
      store.standard = 'listed'
      store.projectStatus = 'active'
      store.auditScope = 'consolidated'
      store.roleInProject = 'manager'

      const ctx = store.currentProjectContext
      expect(ctx.projectId).toBe('proj-123')
      expect(ctx.projectName).toBe('ABC 公司')
      expect(ctx.year).toBe(2025)
      expect(ctx.applicableStandard).toBe('listed')
      expect(ctx.projectStatus).toBe('active')
      expect(ctx.auditScope).toBe('consolidated')
      expect(ctx.roleInProject).toBe('manager')
    })

    it('should have default values for missing fields', () => {
      const store = useProjectStore()
      const ctx = store.currentProjectContext

      expect(ctx.auditScope).toBe('standalone')
      expect(ctx.roleInProject).toBeNull()
      expect(ctx.projectStatus).toBe('draft')
    })

    it('should update reactively when store state changes', () => {
      const store = useProjectStore()
      expect(store.currentProjectContext.projectId).toBe('')

      store.projectId = 'new-project'
      expect(store.currentProjectContext.projectId).toBe('new-project')
    })
  })

  describe('P0-2.4: resetProjectScopedState(reason)', () => {
    it('should clear all project-scoped state', () => {
      const store = useProjectStore()
      store.projectId = 'proj-old'
      store.clientName = 'Old Corp'
      store.projectStatus = 'active'
      store.auditScope = 'consolidated'
      store.roleInProject = 'manager'
      store.auditYear = 2024

      store.resetProjectScopedState('test-switch')

      expect(store.clientName).toBe('')
      expect(store.projectStatus).toBe('')
      expect(store.auditScope).toBe('standalone')
      expect(store.roleInProject).toBeNull()
      expect(store.auditYear).toBeNull()
    })

    it('should emit project:reset event', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'

      store.resetProjectScopedState('user-switch')

      expect(emitSpy).toHaveBeenCalledWith('project:reset', {
        reason: 'user-switch',
        projectId: 'proj-1',
      })
    })

    it('should emit sse:disconnect event', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'

      store.resetProjectScopedState('route-change')

      expect(emitSpy).toHaveBeenCalledWith('sse:disconnect', {
        reason: 'route-change',
      })
    })
  })

  describe('P0-2.5: 项目切换后旧 projectId 相关 state 清空', () => {
    it('should clear state when switching projects via syncFromRoute', async () => {
      const store = useProjectStore()
      store.projectId = 'proj-A'
      store.clientName = 'Company A'
      store.projectStatus = 'active'
      store.roleInProject = 'preparer'

      // Simulate route change to different project
      await store.syncFromRoute({
        params: { projectId: 'proj-B' },
        query: { year: '2025' },
      } as any)

      // Old state should be cleared and new state loaded
      expect(store.projectId).toBe('proj-B')
      // resetProjectScopedState was called before loading new data
      expect(emitSpy).toHaveBeenCalledWith('project:reset', expect.objectContaining({
        reason: 'route-change',
      }))
    })
  })
})

describe('project store - P0-3 年度切换协议', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    emitSpy.mockClear()
  })

  describe('P0-3.1: setCurrentYear(year, { reload: true })', () => {
    it('should update year in store', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'
      store.year = 2024

      store.setCurrentYear(2025)
      expect(store.year).toBe(2025)
    })

    it('should emit year:changed event with previousYear', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'
      store.year = 2024

      store.setCurrentYear(2025)
      expect(emitSpy).toHaveBeenCalledWith('year:changed', {
        projectId: 'proj-1',
        year: 2025,
        previousYear: 2024,
      })
    })

    it('should NOT emit event when year is same', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'
      store.year = 2025

      store.setCurrentYear(2025)
      expect(emitSpy).not.toHaveBeenCalled()
    })

    it('should NOT emit event when no projectId', () => {
      const store = useProjectStore()
      store.projectId = ''
      store.year = 2024

      store.setCurrentYear(2025)
      expect(emitSpy).not.toHaveBeenCalled()
    })
  })

  describe('P0-3.2: 年度切换时清理缓存', () => {
    it('should update auditYear to match new year', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'
      store.year = 2024
      store.auditYear = 2024

      store.setCurrentYear(2025)
      expect(store.auditYear).toBe(2025)
    })

    it('should reset projectStatus to trigger reload', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'
      store.year = 2024
      store.projectStatus = 'active'

      store.setCurrentYear(2025)
      expect(store.projectStatus).toBe('')
    })
  })

  describe('P0-3.3: 停止旧年度 SSE / stale 订阅并重建', () => {
    it('should emit sse:disconnect on year change', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'
      store.year = 2024

      store.setCurrentYear(2025)

      expect(emitSpy).toHaveBeenCalledWith('sse:disconnect', {
        reason: 'year-change',
      })
    })

    it('should emit sse:reconnect with new year', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'
      store.year = 2024

      store.setCurrentYear(2025)

      expect(emitSpy).toHaveBeenCalledWith('sse:reconnect', {
        projectId: 'proj-1',
        year: 2025,
      })
    })
  })

  describe('P0-3.4: 年度切换回归（TrialBalance/ReportView/DisclosureEditor）', () => {
    it('changeYear should also emit year:changed event', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'
      store.year = 2024

      store.changeYear(2025)
      expect(emitSpy).toHaveBeenCalledWith('year:changed', {
        projectId: 'proj-1',
        year: 2025,
      })
    })

    it('year change should be idempotent (no event on same year)', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'
      store.year = 2025

      store.changeYear(2025)
      expect(emitSpy).not.toHaveBeenCalled()
    })
  })
})
