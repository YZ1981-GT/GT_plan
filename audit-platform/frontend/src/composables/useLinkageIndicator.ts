/**
 * useLinkageIndicator — 联动指示器 composable [enterprise-linkage 3.5]
 *
 * 查询试算表行关联的调整分录和底稿，缓存结果，
 * SSE 事件触发刷新。
 *
 * @example
 * ```ts
 * const { getAdjustments, getWorkpapers, refresh } = useLinkageIndicator(projectId, year)
 * const adjs = getAdjustments('BS-002')
 * ```
 */
import { ref, onMounted, onUnmounted, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { linkage as P } from '@/services/apiPaths'
import { eventBus, type SyncEventPayload } from '@/utils/eventBus'
import { ROLE_PERMISSIONS } from '@/composables/usePermission'
import { useAuthStore } from '@/stores/auth'

export interface LinkedAdjustment {
  entry_group_id: string
  adjustment_no: string
  account_code: string
  debit_amount?: number
  credit_amount?: number
  summary?: string
}

export interface LinkedWorkpaper {
  wp_id: string
  wp_code: string
  wp_name: string
  status?: string
}

export function useLinkageIndicator(projectId: Ref<string>, year: Ref<number>) {
  // Cache: rowCode → data
  const adjustmentsCache = ref<Record<string, LinkedAdjustment[]>>({})
  const workpapersCache = ref<Record<string, LinkedWorkpaper[]>>({})

  // Role-based permission check: only show workpaper badges if user has workpaper:view
  const authStore = useAuthStore()
  function _canViewWorkpapers(): boolean {
    const role = authStore.user?.role ?? ''
    if (role === 'admin') return true
    const perms = ROLE_PERMISSIONS[role] ?? []
    return perms.includes('workpaper:view')
  }

  async function fetchAdjustments(rowCode: string): Promise<LinkedAdjustment[]> {
    const pid = projectId.value
    if (!pid || !rowCode) return []
    try {
      const data = await api.get(P.tbRowAdjustments(pid, rowCode), { params: { year: year.value } })
      const items = data ?? []
      adjustmentsCache.value = { ...adjustmentsCache.value, [rowCode]: items }
      return items
    } catch {
      return []
    }
  }

  async function fetchWorkpapers(rowCode: string): Promise<LinkedWorkpaper[]> {
    const pid = projectId.value
    if (!pid || !rowCode) return []
    try {
      const data = await api.get(P.tbRowWorkpapers(pid, rowCode), { params: { year: year.value } })
      const items = data ?? []
      workpapersCache.value = { ...workpapersCache.value, [rowCode]: items }
      return items
    } catch {
      return []
    }
  }

  function getAdjustments(rowCode: string): LinkedAdjustment[] {
    if (!adjustmentsCache.value[rowCode]) {
      fetchAdjustments(rowCode)
    }
    return adjustmentsCache.value[rowCode] ?? []
  }

  function getWorkpapers(rowCode: string): LinkedWorkpaper[] {
    // Role-based filtering: hide workpaper badges for users without workpaper:view permission
    if (!_canViewWorkpapers()) return []
    if (!workpapersCache.value[rowCode]) {
      fetchWorkpapers(rowCode)
    }
    return workpapersCache.value[rowCode] ?? []
  }

  function refresh() {
    adjustmentsCache.value = {}
    workpapersCache.value = {}
  }

  // ─── SSE subscription: refresh on adjustment/tb changes ───────────────────

  function handleSSE(payload: SyncEventPayload) {
    if (payload.project_id !== projectId.value) return
    const et = payload.event_type

    // Task 4.6: Cross-year isolation - filter events by current year
    if (payload.year !== undefined && payload.year !== year.value) return

    if (
      et === 'adjustment.created' ||
      et === 'adjustment.updated' ||
      et === 'adjustment.deleted' ||
      et === 'adjustment.batch_committed' ||
      et === 'trial_balance.updated'
    ) {
      refresh()
    }
  }

  onMounted(() => {
    eventBus.on('sse:sync-event', handleSSE)
  })

  onUnmounted(() => {
    eventBus.off('sse:sync-event', handleSSE)
  })

  return {
    getAdjustments,
    getWorkpapers,
    refresh,
    adjustmentsCache,
    workpapersCache,
  }
}
