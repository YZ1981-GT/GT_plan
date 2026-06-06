/**
 * Tests for usePermissionMatrix composable
 *
 * 验证 can() / whyCannot() 对 7 个 operation code × 6 角色的正确性。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { usePermissionMatrix, OPERATION_CODES } from '@/composables/usePermissionMatrix'
import { useAuthStore } from '@/stores/auth'

// Mock auth store user
function setupRole(role: string) {
  const authStore = useAuthStore()
  authStore.$patch({
    user: { id: 'u1', username: 'test', email: 'test@test.com', role, office_code: null, is_active: true, created_at: '2024-01-01' },
    token: 'fake-token',
  })
}

describe('usePermissionMatrix', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('OPERATION_CODES', () => {
    it('should have 7 operation codes', () => {
      expect(OPERATION_CODES).toHaveLength(7)
    })

    it('should include all expected codes', () => {
      const expected = ['project:view', 'wp:edit', 'wp:review', 'report:edit', 'report:sign', 'note:edit', 'archive:manage']
      for (const code of expected) {
        expect(OPERATION_CODES).toContain(code)
      }
    })
  })

  describe('can() - admin', () => {
    beforeEach(() => setupRole('admin'))

    it('should allow all operations', () => {
      const { can } = usePermissionMatrix()
      for (const code of OPERATION_CODES) {
        expect(can(code)).toBe(true)
      }
    })
  })

  describe('can() - partner', () => {
    beforeEach(() => setupRole('partner'))

    it('should allow all 7 operations', () => {
      const { can } = usePermissionMatrix()
      for (const code of OPERATION_CODES) {
        expect(can(code)).toBe(true)
      }
    })
  })

  describe('can() - manager', () => {
    beforeEach(() => setupRole('manager'))

    it('should allow project:view, wp:edit, wp:review, report:edit, note:edit', () => {
      const { can } = usePermissionMatrix()
      expect(can('project:view')).toBe(true)
      expect(can('wp:edit')).toBe(true)
      expect(can('wp:review')).toBe(true)
      expect(can('report:edit')).toBe(true)
      expect(can('note:edit')).toBe(true)
    })

    it('should NOT allow report:sign, archive:manage', () => {
      const { can } = usePermissionMatrix()
      expect(can('report:sign')).toBe(false)
      expect(can('archive:manage')).toBe(false)
    })
  })

  describe('can() - auditor', () => {
    beforeEach(() => setupRole('auditor'))

    it('should allow project:view, wp:edit, note:edit', () => {
      const { can } = usePermissionMatrix()
      expect(can('project:view')).toBe(true)
      expect(can('wp:edit')).toBe(true)
      expect(can('note:edit')).toBe(true)
    })

    it('should NOT allow wp:review, report:edit, report:sign, archive:manage', () => {
      const { can } = usePermissionMatrix()
      expect(can('wp:review')).toBe(false)
      expect(can('report:edit')).toBe(false)
      expect(can('report:sign')).toBe(false)
      expect(can('archive:manage')).toBe(false)
    })
  })

  describe('can() - qc', () => {
    beforeEach(() => setupRole('qc'))

    it('should allow project:view, wp:review, report:edit', () => {
      const { can } = usePermissionMatrix()
      expect(can('project:view')).toBe(true)
      expect(can('wp:review')).toBe(true)
      expect(can('report:edit')).toBe(true)
    })

    it('should NOT allow wp:edit, report:sign, note:edit, archive:manage', () => {
      const { can } = usePermissionMatrix()
      expect(can('wp:edit')).toBe(false)
      expect(can('report:sign')).toBe(false)
      expect(can('note:edit')).toBe(false)
      expect(can('archive:manage')).toBe(false)
    })
  })

  describe('can() - eqcr', () => {
    beforeEach(() => setupRole('eqcr'))

    it('should allow project:view, wp:review only', () => {
      const { can } = usePermissionMatrix()
      expect(can('project:view')).toBe(true)
      expect(can('wp:review')).toBe(true)
    })

    it('should NOT allow edit operations', () => {
      const { can } = usePermissionMatrix()
      expect(can('wp:edit')).toBe(false)
      expect(can('report:edit')).toBe(false)
      expect(can('report:sign')).toBe(false)
      expect(can('note:edit')).toBe(false)
      expect(can('archive:manage')).toBe(false)
    })
  })

  describe('can() - role aliases', () => {
    it('should normalize "assistant" to auditor', () => {
      setupRole('assistant')
      const { can } = usePermissionMatrix()
      expect(can('wp:edit')).toBe(true)
      expect(can('wp:review')).toBe(false)
    })

    it('should normalize "quality_control" to qc', () => {
      setupRole('quality_control')
      const { can } = usePermissionMatrix()
      expect(can('wp:review')).toBe(true)
      expect(can('wp:edit')).toBe(false)
    })
  })

  describe('can() - no user', () => {
    it('should deny all when no user logged in', () => {
      const { can } = usePermissionMatrix()
      for (const code of OPERATION_CODES) {
        expect(can(code)).toBe(false)
      }
    })
  })

  describe('whyCannot()', () => {
    it('should return null when operation is allowed', () => {
      setupRole('admin')
      const { whyCannot } = usePermissionMatrix()
      expect(whyCannot('project:view')).toBeNull()
    })

    it('should return reason when operation is denied', () => {
      setupRole('auditor')
      const { whyCannot } = usePermissionMatrix()
      const reason = whyCannot('report:sign')
      expect(reason).not.toBeNull()
      expect(reason).toContain('auditor')
      expect(reason).toContain('report:sign')
    })

    it('should return login hint when no user', () => {
      const { whyCannot } = usePermissionMatrix()
      const reason = whyCannot('project:view')
      expect(reason).toContain('未登录')
    })
  })
})
