/**
 * useProjectRole — 项目级角色与权限 composable (Phase 6 F4)
 *
 * 从 /api/projects/{id}/my-permissions 获取权限列表。
 * 缓存 5min TTL，项目切换时主动刷新。
 * 暴露 projectCan(permission)、permissions、projectRole、systemRole、loading、refresh。
 *
 * Validates: Requirements F4.4, F4.5, F4.6
 */

import { ref, watch, type Ref } from 'vue'
import http from '@/utils/http'
import { ROLE_PERMISSIONS } from '@/composables/usePermission'

interface PermissionsResponse {
  permissions: string[]
  project_role: string | null
  system_role: string
}

// 缓存结构
interface CacheEntry {
  data: PermissionsResponse
  timestamp: number
}

const CACHE_TTL = 5 * 60 * 1000 // 5 分钟
const cache = new Map<string, CacheEntry>()

export function useProjectRole(projectId: Ref<string>) {
  const permissions = ref<string[]>([])
  const projectRole = ref<string | null>(null)
  const systemRole = ref<string>('')
  const loading = ref(false)

  /**
   * 检查当前用户是否拥有指定权限
   */
  function projectCan(permission: string): boolean {
    // admin 拥有所有权限
    if (systemRole.value === 'admin') return true
    if (permission === 'admin') return systemRole.value === 'admin'
    return permissions.value.includes(permission)
  }

  /**
   * 从后端获取权限列表（带缓存）
   */
  async function refresh(): Promise<void> {
    const pid = projectId.value
    if (!pid) return

    // 检查缓存
    const cached = cache.get(pid)
    if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
      permissions.value = cached.data.permissions
      projectRole.value = cached.data.project_role
      systemRole.value = cached.data.system_role
      return
    }

    loading.value = true
    try {
      const resp = await http.get<PermissionsResponse>(
        `/api/projects/${pid}/my-permissions`
      )
      const data = resp.data
      permissions.value = data.permissions
      projectRole.value = data.project_role
      systemRole.value = data.system_role

      // 写入缓存
      cache.set(pid, { data, timestamp: Date.now() })
    } catch (err: any) {
      // 降级到前端硬编码
      console.warn('[useProjectRole] API 不可用，降级到前端 ROLE_PERMISSIONS', err)
      const fallbackPerms = ROLE_PERMISSIONS[systemRole.value] ?? []
      permissions.value = fallbackPerms
    } finally {
      loading.value = false
    }
  }

  // 项目切换时自动刷新
  watch(
    () => projectId.value,
    (newId) => {
      if (newId) {
        refresh()
      }
    },
    { immediate: true }
  )

  return {
    permissions,
    projectRole,
    systemRole,
    loading,
    projectCan,
    refresh,
  }
}
