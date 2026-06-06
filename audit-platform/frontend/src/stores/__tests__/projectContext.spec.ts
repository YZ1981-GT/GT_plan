/**
 * Tests for project store — currentProjectContext & setCurrentYear
 *
 * 验证 MVP-1 currentProjectContext computed 和 MVP-2 setCurrentYear 行为。
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

describe('project store - currentProjectContext', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    emitSpy.mockClear()
  })

  describe('currentProjectContext computed', () => {
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

      const ctx = store.currentProjectContext
      expect(ctx.projectId).toBe('proj-123')
      expect(ctx.projectName).toBe('ABC 公司')
      expect(ctx.year).toBe(2025)
      expect(ctx.applicableStandard).toBe('listed')
      expect(ctx.projectStatus).toBe('active')
    })

    it('should have default values for missing fields', () => {
      const store = useProjectStore()
      const ctx = store.currentProjectContext

      expect(ctx.auditScope).toBe('standalone')
      expect(ctx.roleInProject).toBeNull()
      expect(ctx.projectStatus).toBe('draft') // default when empty
    })

    it('should update reactively when store state changes', () => {
      const store = useProjectStore()
      expect(store.currentProjectContext.projectId).toBe('')

      store.projectId = 'new-project'
      expect(store.currentProjectContext.projectId).toBe('new-project')
    })
  })

  describe('setCurrentYear()', () => {
    it('should update year in store', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'
      store.year = 2024

      store.setCurrentYear(2025)
      expect(store.year).toBe(2025)
    })

    it('should emit year:changed event when year changes', () => {
      const store = useProjectStore()
      store.projectId = 'proj-1'
      store.year = 2024

      store.setCurrentYear(2025)
      expect(emitSpy).toHaveBeenCalledWith('year:changed', {
        projectId: 'proj-1',
        year: 2025,
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
})
