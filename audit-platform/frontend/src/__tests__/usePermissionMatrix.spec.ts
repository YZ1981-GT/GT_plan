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
import { usePermissionMatrix, toMatrixRole, OPERATION_CODES, type OperationCode } from '@/composables/usePermissionMatrix'
import { ALL_ROLES, getAllowedActions as matrixAllowed } from '@/permissions/permission-matrix'

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

  describe('R5.3 只读 / 未知角色最小权限（trim-generation-plan-followup-optimizations）', () => {
    const RESOURCES = ['workpaper', 'adjustment', 'report', 'note', 'template', 'project_settings'] as const

    it('readonly 显式映射为只读矩阵：只能查看，任何资源都不能编辑 / 复核 / 导出 / 导入', () => {
      mockUser.role = 'readonly'
      const pm = usePermissionMatrix()
      expect(pm.matrixRole.value).toBe('readonly')
      for (const resource of RESOURCES) {
        expect(pm.allowedActionsFor(resource)).toEqual(['view'])
        expect(pm.isReadonlyFor(resource)).toBe(true)
        expect(pm.canDo('edit', resource)).toBe(false)
        expect(pm.whyCannotDo('edit', resource)).toContain('只读用户')
      }
      // 操作码级镜像后端 ROLE_OPERATIONS（后端没有 readonly 项）
      for (const code of OPERATION_CODES) expect(pm.can(code)).toBe(false)
    })

    it.each(['', '   ', 'guest', 'superuser', 'constructor', '__proto__', 'toString'])(
      '未登记角色 %j 不兜底成 assistant（不能放大权限）', (role) => {
        mockUser.role = role
        const pm = usePermissionMatrix()
        expect(pm.matrixRole.value).toBe('readonly')
        expect(pm.canDo('edit', 'workpaper')).toBe(false)
        expect(pm.canDo('import', 'adjustment')).toBe(false)
        expect(pm.canDo('view', 'workpaper')).toBe(true)
      },
    )

    it('正向：已登记角色映射不变（不因收紧兜底而误伤）', () => {
      const expected: Record<string, string> = {
        admin: 'partner', partner: 'partner', signing_partner: 'partner', manager: 'manager',
        auditor: 'assistant', assistant: 'assistant', qc: 'qc_partner', quality_control: 'qc_partner',
        qc_partner: 'qc_partner', eqcr: 'eqcr', readonly: 'readonly', ' Auditor ': 'assistant',
      }
      for (const [role, matrix] of Object.entries(expected)) expect(toMatrixRole(role), role).toBe(matrix)
      mockUser.role = 'auditor'
      const pm = usePermissionMatrix()
      expect(pm.canDo('edit', 'workpaper')).toBe(true)
    })

    it('readonly 是所有角色里权限最小的：每个角色的允许动作都包含 readonly 的', () => {
      for (const role of ALL_ROLES) {
        for (const resource of RESOURCES) {
          const allowed = new Set(matrixAllowed(role, resource))
          for (const action of matrixAllowed('readonly', resource)) expect(allowed.has(action), `${role}/${resource}`).toBe(true)
        }
      }
    })
  })
})
