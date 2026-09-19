/**
 * Tests for usePermissionMatrix — P0-5 权限矩阵前端 facade
 *
 * 验证:
 * - P0-5.1: usePermissionMatrix(projectId) 基本功能
 * - P0-5.2: can(operationCode) / whyCannot(operationCode) 判断逻辑
 * - P0-5.3: 兼容旧 usePermission 调用模式
 * - P0-5.4: operation code 前后端快照一致
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePermissionMatrix, OPERATION_CODES, type OperationCode } from '@/composables/usePermissionMatrix'

// Mock auth store
const mockUser = { role: 'auditor', id: 'user-1', username: 'test' }
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: mockUser }),
}))

// Mock project store
const mockProjectStore = { roleInProject: null as string | null }
vi.mock('@/stores/project', () => ({
  useProjectStore: () => mockProjectStore,
}))

describe('usePermissionMatrix - P0-5', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockUser.role = 'auditor'
    mockProjectStore.roleInProject = null
  })

  describe('P0-5.4: operation code 前后端快照一致', () => {
    it('should have exactly 7 operation codes', () => {
      expect(OPERATION_CODES).toHaveLength(7)
    })

    it('should match backend operation codes snapshot', () => {
      // 这些 code 必须与后端 permission_matrix_service.py 完全一致
      const expectedCodes: OperationCode[] = [
        'project:view',
        'wp:edit',
        'wp:review',
        'report:edit',
        'report:sign',
        'note:edit',
        'archive:manage',
      ]
      expect([...OPERATION_CODES]).toEqual(expectedCodes)
    })
  })

  describe('P0-5.1: usePermissionMatrix() 基本功能', () => {
    it('should return can, whyCannot, currentRole, allowedOperations', () => {
      const pm = usePermissionMatrix()
      expect(pm.can).toBeTypeOf('function')
      expect(pm.whyCannot).toBeTypeOf('function')
      expect(pm.currentRole).toBeDefined()
      expect(pm.allowedOperations).toBeDefined()
    })

    it('should detect currentRole from authStore', () => {
      mockUser.role = 'manager'
      const pm = usePermissionMatrix()
      expect(pm.currentRole.value).toBe('manager')
    })

    it('should normalize role aliases', () => {
      mockUser.role = 'assistant'
      const pm = usePermissionMatrix()
      expect(pm.currentRole.value).toBe('auditor')
    })

    it('should normalize signing_partner to partner', () => {
      mockUser.role = 'signing_partner'
      const pm = usePermissionMatrix()
      expect(pm.currentRole.value).toBe('partner')
    })
  })

  describe('P0-5.2: can(operationCode) / whyCannot(operationCode)', () => {
    it('admin can do everything', () => {
      mockUser.role = 'admin'
      const pm = usePermissionMatrix()
      for (const code of OPERATION_CODES) {
        expect(pm.can(code)).toBe(true)
      }
    })

    it('auditor can edit workpapers and notes', () => {
      mockUser.role = 'auditor'
      const pm = usePermissionMatrix()
      expect(pm.can('project:view')).toBe(true)
      expect(pm.can('wp:edit')).toBe(true)
      expect(pm.can('note:edit')).toBe(true)
    })

    it('auditor cannot review, sign, or manage archive', () => {
      mockUser.role = 'auditor'
      const pm = usePermissionMatrix()
      expect(pm.can('wp:review')).toBe(false)
      expect(pm.can('report:sign')).toBe(false)
      expect(pm.can('archive:manage')).toBe(false)
    })

    it('eqcr can only view and review', () => {
      mockUser.role = 'eqcr'
      const pm = usePermissionMatrix()
      expect(pm.can('project:view')).toBe(true)
      expect(pm.can('wp:review')).toBe(true)
      expect(pm.can('wp:edit')).toBe(false)
      expect(pm.can('report:edit')).toBe(false)
      expect(pm.can('note:edit')).toBe(false)
    })

    it('whyCannot returns null when allowed', () => {
      mockUser.role = 'admin'
      const pm = usePermissionMatrix()
      expect(pm.whyCannot('wp:edit')).toBeNull()
    })

    it('whyCannot returns reason when denied', () => {
      mockUser.role = 'auditor'
      const pm = usePermissionMatrix()
      const reason = pm.whyCannot('report:sign')
      expect(reason).not.toBeNull()
      expect(reason).toContain('auditor')
      expect(reason).toContain('report:sign')
    })

    it('whyCannot includes project role in reason', () => {
      mockUser.role = 'auditor'
      mockProjectStore.roleInProject = 'preparer'
      const pm = usePermissionMatrix()
      const reason = pm.whyCannot('report:sign')
      expect(reason).toContain('preparer')
    })

    it('project role adds additional operations', () => {
      mockUser.role = 'auditor'
      mockProjectStore.roleInProject = 'reviewer'
      const pm = usePermissionMatrix()
      // auditor alone cannot review
      // but with reviewer project role, can review
      expect(pm.can('wp:review')).toBe(true)
      expect(pm.can('report:edit')).toBe(true)
    })
  })

  describe('P0-5.3: 兼容旧 usePermission', () => {
    it('canRole should check if current role matches', () => {
      mockUser.role = 'manager'
      const pm = usePermissionMatrix()
      expect(pm.canRole('manager')).toBe(true)
      expect(pm.canRole('admin')).toBe(false)
    })

    it('admin canRole always returns true', () => {
      mockUser.role = 'admin'
      const pm = usePermissionMatrix()
      expect(pm.canRole('manager')).toBe(true)
      expect(pm.canRole('auditor')).toBe(true)
    })
  })

  describe('角色权限继承验证', () => {
    it('partner superset of manager', () => {
      mockUser.role = 'partner'
      const partnerPm = usePermissionMatrix()
      const partnerOps = new Set(OPERATION_CODES.filter(c => partnerPm.can(c)))

      mockUser.role = 'manager'
      const managerPm = usePermissionMatrix()
      const managerOps = new Set(OPERATION_CODES.filter(c => managerPm.can(c)))

      for (const op of managerOps) {
        expect(partnerOps.has(op)).toBe(true)
      }
    })

    it('all roles can view project', () => {
      for (const role of ['admin', 'partner', 'manager', 'auditor', 'qc', 'eqcr']) {
        mockUser.role = role
        const pm = usePermissionMatrix()
        expect(pm.can('project:view')).toBe(true)
      }
    })
  })
})
