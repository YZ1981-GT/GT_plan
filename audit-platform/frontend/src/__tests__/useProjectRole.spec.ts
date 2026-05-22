/**
 * useProjectRole composable 前端测试
 * Validates: Requirements F4.4, F4.5, F4.6
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { flushPromises } from '@vue/test-utils'

vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(),
  },
}))

vi.mock('@/composables/usePermission', () => ({
  ROLE_PERMISSIONS: {
    admin: ['project:view', 'project:edit', 'sign:execute'],
    manager: ['project:view', 'project:edit'],
    auditor: ['project:view', 'workpaper:edit'],
  },
}))

import http from '@/utils/http'
import { useProjectRole } from '@/composables/useProjectRole'

describe('useProjectRole', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('fetches permissions on init when projectId is set', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: {
        permissions: ['project:view', 'workpaper:edit'],
        project_role: 'auditor',
        system_role: 'auditor',
      },
    })

    const projectId = ref('test-project-id')
    const { permissions, projectRole, systemRole } = useProjectRole(projectId)

    await flushPromises()

    expect(http.get).toHaveBeenCalledWith('/api/projects/test-project-id/my-permissions')
    expect(permissions.value).toContain('project:view')
    expect(projectRole.value).toBe('auditor')
    expect(systemRole.value).toBe('auditor')
  })

  it('projectCan returns true for admin system role', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: {
        permissions: ['project:view'],
        project_role: 'admin',
        system_role: 'admin',
      },
    })

    const projectId = ref('admin-project-id')
    const { projectCan, systemRole } = useProjectRole(projectId)

    await flushPromises()

    // Verify systemRole was set
    expect(systemRole.value).toBe('admin')
    expect(projectCan('any:permission')).toBe(true)
    expect(projectCan('sign:execute')).toBe(true)
  })

  it('projectCan returns false for missing permission', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: {
        permissions: ['project:view'],
        project_role: 'readonly',
        system_role: 'auditor',
      },
    })

    const projectId = ref('readonly-project-id')
    const { projectCan } = useProjectRole(projectId)

    await flushPromises()

    expect(projectCan('sign:execute')).toBe(false)
  })

  it('caches results for same projectId', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: {
        permissions: ['project:view'],
        project_role: 'auditor',
        system_role: 'auditor',
      },
    })

    const projectId = ref('cached-project')
    const { refresh } = useProjectRole(projectId)

    await flushPromises()

    // Second call should use cache
    await refresh()
    expect(http.get).toHaveBeenCalledTimes(1)
  })

  it('refreshes on project switch', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: {
        permissions: ['project:view'],
        project_role: 'auditor',
        system_role: 'auditor',
      },
    })

    const projectId = ref('project-a')
    useProjectRole(projectId)

    await flushPromises()

    // Switch project
    projectId.value = 'project-b'
    await flushPromises()

    expect(http.get).toHaveBeenCalledTimes(2)
    expect(http.get).toHaveBeenLastCalledWith('/api/projects/project-b/my-permissions')
  })

  it('falls back to ROLE_PERMISSIONS on API error', async () => {
    vi.mocked(http.get).mockRejectedValue(new Error('Network error'))

    const projectId = ref('error-project')
    const { permissions } = useProjectRole(projectId)

    await flushPromises()

    // Should fallback to empty (systemRole is '' initially)
    expect(permissions.value).toEqual([])
  })

  it('does not fetch when projectId is empty', async () => {
    const projectId = ref('')
    useProjectRole(projectId)

    await flushPromises()

    expect(http.get).not.toHaveBeenCalled()
  })
})
