/**
 * useConflictGuard — 调整分录冲突守卫 composable [enterprise-linkage 3.3]
 *
 * 管理调整分录编辑锁的获取/释放/心跳续期，
 * 检测版本冲突并自动刷新最新版本。
 *
 * @example
 * ```ts
 * const { acquireLock, releaseLock, isLocked, lockHolder, versionConflict } = useConflictGuard(projectId)
 * await acquireLock(entryGroupId)
 * ```
 */
import { ref, onUnmounted, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { conflictGuard as P } from '@/services/apiPaths'

const LOCK_HEARTBEAT_INTERVAL = 25_000 // 25s (< 60s expiry)

export function useConflictGuard(projectId: Ref<string>) {
  const isLocked = ref(false)
  const lockHolder = ref<string | null>(null)
  const versionConflict = ref(false)
  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let currentEntryGroupId: string | null = null

  // ─── Acquire lock ─────────────────────────────────────────────────────────

  async function acquireLock(entryGroupId: string): Promise<boolean> {
    const pid = projectId.value
    if (!pid || !entryGroupId) return false

    try {
      await api.post(P.lock(pid, entryGroupId))
      isLocked.value = true
      lockHolder.value = null
      currentEntryGroupId = entryGroupId
      startHeartbeat(entryGroupId)
      return true
    } catch (e: any) {
      const status = e?.response?.status ?? e?.status
      if (status === 409) {
        // Someone else holds the lock
        isLocked.value = true
        lockHolder.value =
          e?.response?.data?.detail?.locked_by_name ??
          e?.data?.detail?.locked_by_name ??
          e?.response?.data?.message?.locked_by_name ??
          '其他用户'
        return false
      }
      return false
    }
  }

  // ─── Release lock ─────────────────────────────────────────────────────────

  async function releaseLock(entryGroupId?: string): Promise<void> {
    const pid = projectId.value
    const egId = entryGroupId ?? currentEntryGroupId
    if (!pid || !egId) return

    stopHeartbeat()
    try {
      await api.delete(P.unlock(pid, egId))
    } catch { /* ignore */ }
    isLocked.value = false
    lockHolder.value = null
    currentEntryGroupId = null
  }

  // ─── Heartbeat ────────────────────────────────────────────────────────────

  async function sendLockHeartbeat(entryGroupId: string) {
    const pid = projectId.value
    if (!pid) return
    try {
      await api.patch(P.heartbeat(pid, entryGroupId))
    } catch { /* ignore */ }
  }

  function startHeartbeat(entryGroupId: string) {
    stopHeartbeat()
    heartbeatTimer = setInterval(() => sendLockHeartbeat(entryGroupId), LOCK_HEARTBEAT_INTERVAL)
  }

  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  // ─── Version conflict detection ──────────────────────────────────────────

  /**
   * Call this when an update returns 409 VERSION_CONFLICT.
   * Sets versionConflict flag for the UI to show ConflictDialog.
   */
  function markVersionConflict() {
    versionConflict.value = true
  }

  function clearVersionConflict() {
    versionConflict.value = false
  }

  // ─── Cleanup ──────────────────────────────────────────────────────────────

  onUnmounted(() => {
    stopHeartbeat()
    if (currentEntryGroupId) {
      releaseLock(currentEntryGroupId)
    }
  })

  return {
    acquireLock,
    releaseLock,
    isLocked,
    lockHolder,
    versionConflict,
    markVersionConflict,
    clearVersionConflict,
  }
}
