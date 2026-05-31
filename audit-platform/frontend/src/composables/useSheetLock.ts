/**
 * useSheetLock — sheet 级软锁 composable
 *
 * 进入编辑 sheet 时 acquire lock，心跳每 2 分钟续期，
 * 切 tab / 离开时 release。
 * 如果其他用户持有锁，显示 "X 正在编辑此 sheet" 提示。
 *
 * Requirements: 6.1, 6.2, 6.4
 *
 * 后端端点：
 *   POST   /api/workpapers/{wpId}/sheets/{sheetName}/lock           — 获取锁
 *   PATCH  /api/workpapers/{wpId}/sheets/{sheetName}/lock/heartbeat — 续期
 *   DELETE /api/workpapers/{wpId}/sheets/{sheetName}/lock           — 释放锁
 *   GET    /api/workpapers/{wpId}/sheets/{sheetName}/lock           — 查询锁持有者
 */
import { ref, watch, onUnmounted, type Ref } from 'vue'
import { api } from '@/services/apiProxy'

export interface SheetLockState {
  /** 是否有人持有锁 */
  locked: boolean
  /** 锁是否属于当前用户 */
  isMine: boolean
  /** 锁持有者名称（他人持锁时显示） */
  holderName: string | null
}

export interface UseSheetLockOptions {
  /** 底稿 ID */
  wpId: Ref<string>
  /** 当前活跃 sheet 名称 */
  activeSheet: Ref<string>
  /** 心跳间隔（ms），默认 120000（2 分钟） */
  heartbeatMs?: number
  /** 轮询锁状态间隔（ms），默认 10000（10 秒） */
  pollMs?: number
}

export function useSheetLock(options: UseSheetLockOptions) {
  const { wpId, activeSheet } = options
  const heartbeatMs = options.heartbeatMs ?? 120_000
  const pollMs = options.pollMs ?? 10_000

  const state = ref<SheetLockState>({
    locked: false,
    isMine: false,
    holderName: null,
  })

  let heartbeatTimer: ReturnType<typeof setInterval> | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let currentLockedSheet: string | null = null

  // ─── API helpers ──────────────────────────────────────────────────────────

  function buildUrl(sheet: string, suffix = '') {
    return `/api/workpapers/${wpId.value}/sheets/${encodeURIComponent(sheet)}/lock${suffix}`
  }

  async function acquireLock(sheet: string): Promise<boolean> {
    if (!wpId.value || !sheet) return false
    try {
      await api.post(buildUrl(sheet))
      state.value = { locked: true, isMine: true, holderName: null }
      currentLockedSheet = sheet
      startHeartbeat(sheet)
      return true
    } catch (e: any) {
      const status = e?.response?.status ?? e?.status
      if (status === 409) {
        const detail = e?.response?.data?.detail ?? e?.data?.detail ?? {}
        state.value = {
          locked: true,
          isMine: false,
          holderName: detail.locked_by_name ?? '其他用户',
        }
        // 开始轮询锁状态（等待释放）
        startPoll(sheet)
        return false
      }
      // 其他错误静默处理
      return false
    }
  }

  async function releaseLock(sheet: string): Promise<void> {
    if (!wpId.value || !sheet) return
    stopHeartbeat()
    stopPoll()
    try {
      await api.delete(buildUrl(sheet))
    } catch { /* ignore 404 */ }
    currentLockedSheet = null
    state.value = { locked: false, isMine: false, holderName: null }
  }

  async function heartbeat(sheet: string): Promise<void> {
    if (!wpId.value || !sheet) return
    try {
      await api.patch(buildUrl(sheet, '/heartbeat'))
    } catch { /* ignore */ }
  }

  async function pollLockStatus(sheet: string): Promise<void> {
    if (!wpId.value || !sheet) return
    try {
      const data = await api.get(buildUrl(sheet))
      const holder = data?.holder
      if (!holder) {
        // 锁已释放，尝试获取
        stopPoll()
        await acquireLock(sheet)
      } else {
        state.value = {
          locked: true,
          isMine: false,
          holderName: holder.locked_by_name ?? '其他用户',
        }
      }
    } catch { /* ignore */ }
  }

  // ─── Timer management ─────────────────────────────────────────────────────

  function startHeartbeat(sheet: string) {
    stopHeartbeat()
    heartbeatTimer = setInterval(() => heartbeat(sheet), heartbeatMs)
  }

  function stopHeartbeat() {
    if (heartbeatTimer) {
      clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function startPoll(sheet: string) {
    stopPoll()
    pollTimer = setInterval(() => pollLockStatus(sheet), pollMs)
  }

  function stopPoll() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  // ─── Watch active sheet changes ───────────────────────────────────────────

  watch(activeSheet, async (newSheet, oldSheet) => {
    // 释放旧 sheet 锁
    if (oldSheet && currentLockedSheet === oldSheet && state.value.isMine) {
      await releaseLock(oldSheet)
    } else {
      stopHeartbeat()
      stopPoll()
    }

    // 获取新 sheet 锁
    if (newSheet) {
      await acquireLock(newSheet)
    } else {
      state.value = { locked: false, isMine: false, holderName: null }
    }
  })

  // ─── beforeunload release ─────────────────────────────────────────────────

  function onBeforeUnload() {
    if (currentLockedSheet && state.value.isMine) {
      // 使用 sendBeacon 确保页面关闭时释放锁
      const url = buildUrl(currentLockedSheet)
      navigator.sendBeacon?.(url + '?_method=DELETE', '')
      // fallback: 同步 XMLHttpRequest（不推荐但兜底）
    }
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', onBeforeUnload)
  }

  // ─── Cleanup ──────────────────────────────────────────────────────────────

  onUnmounted(async () => {
    stopHeartbeat()
    stopPoll()
    if (currentLockedSheet && state.value.isMine) {
      await releaseLock(currentLockedSheet)
    }
    if (typeof window !== 'undefined') {
      window.removeEventListener('beforeunload', onBeforeUnload)
    }
  })

  return {
    /** 当前 sheet 锁状态 */
    sheetLockState: state,
    /** 手动获取锁 */
    acquireLock,
    /** 手动释放锁 */
    releaseLock,
  }
}
