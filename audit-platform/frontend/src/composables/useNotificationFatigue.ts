/**
 * useNotificationFatigue — 通知疲劳控制 composable [enterprise-linkage 4.1]
 *
 * - 静默模式开关 + 通知频率配置（实时/5 分钟汇总/仅手动）
 * - 5 分钟窗口 >10 条事件合并为汇总通知
 * - 冲突守卫通知不受静默影响
 * - Store preferences in localStorage key `notification_prefs`
 *
 * Validates: Requirements 15.1, 15.2, 15.3, 15.4, 15.5
 */
import { ref, computed, onUnmounted } from 'vue'

export type NotificationMode = 'realtime' | 'batch_5min' | 'manual'

interface NotificationPrefs {
  isSilent: boolean
  mode: NotificationMode
}

const STORAGE_KEY = 'notification_prefs'
const BATCH_WINDOW_MS = 5 * 60 * 1000 // 5 minutes
const BATCH_THRESHOLD = 10

// Conflict guard event types that bypass silence
const CONFLICT_EVENT_TYPES = [
  'conflict.lock_acquired',
  'conflict.lock_denied',
  'conflict.version_conflict',
]

function loadPrefs(): NotificationPrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return { isSilent: false, mode: 'realtime' }
}

function savePrefs(prefs: NotificationPrefs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  } catch { /* ignore */ }
}

export function useNotificationFatigue() {
  const prefs = loadPrefs()
  const isSilent = ref(prefs.isSilent)
  const mode = ref<NotificationMode>(prefs.mode)

  // Buffer for batch mode
  const buffer: { eventType: string; timestamp: number }[] = []
  let flushTimer: ReturnType<typeof setTimeout> | null = null

  // Persist on change
  function persist() {
    savePrefs({ isSilent: isSilent.value, mode: mode.value })
  }

  /**
   * Determine if a notification should be shown for the given event type.
   * Conflict guard notifications always pass through.
   */
  function shouldNotify(eventType: string): boolean {
    // Conflict guard notifications are never silenced
    if (CONFLICT_EVENT_TYPES.includes(eventType)) {
      return true
    }

    // Silent mode suppresses all non-conflict notifications
    if (isSilent.value) {
      // Still buffer for batch summary
      _addToBuffer(eventType)
      return false
    }

    // Mode-based logic
    if (mode.value === 'manual') {
      _addToBuffer(eventType)
      return false
    }

    if (mode.value === 'batch_5min') {
      _addToBuffer(eventType)
      // Check if we should show a batch summary
      const windowStart = Date.now() - BATCH_WINDOW_MS
      const recentCount = buffer.filter(e => e.timestamp >= windowStart).length
      if (recentCount > BATCH_THRESHOLD) {
        return false // Will be shown as batch summary on flush
      }
      return false // Batched, not shown individually
    }

    // realtime mode: show immediately
    // But still check 5-min window >10 threshold for auto-batching
    _addToBuffer(eventType)
    const windowStart = Date.now() - BATCH_WINDOW_MS
    const recentCount = buffer.filter(e => e.timestamp >= windowStart).length
    if (recentCount > BATCH_THRESHOLD) {
      return false // Too many, will be batched
    }

    return true
  }

  function _addToBuffer(eventType: string) {
    buffer.push({ eventType, timestamp: Date.now() })
    // Clean old entries beyond window
    const cutoff = Date.now() - BATCH_WINDOW_MS
    while (buffer.length > 0 && buffer[0].timestamp < cutoff) {
      buffer.shift()
    }
    // Schedule flush if in batch mode
    if (mode.value === 'batch_5min' && !flushTimer) {
      flushTimer = setTimeout(() => {
        flushTimer = null
      }, BATCH_WINDOW_MS)
    }
  }

  /**
   * Get the number of buffered (unseen) notifications in the current window.
   */
  function getBufferedCount(): number {
    const cutoff = Date.now() - BATCH_WINDOW_MS
    return buffer.filter(e => e.timestamp >= cutoff).length
  }

  /**
   * Flush the buffer (mark all as seen). Returns the count that was flushed.
   */
  function flush(): number {
    const count = buffer.length
    buffer.length = 0
    if (flushTimer) {
      clearTimeout(flushTimer)
      flushTimer = null
    }
    return count
  }

  // Toggle silent mode
  function toggleSilent(value?: boolean) {
    isSilent.value = value !== undefined ? value : !isSilent.value
    persist()
  }

  // Set notification mode
  function setMode(newMode: NotificationMode) {
    mode.value = newMode
    persist()
  }

  onUnmounted(() => {
    if (flushTimer) {
      clearTimeout(flushTimer)
      flushTimer = null
    }
  })

  return {
    isSilent: computed(() => isSilent.value),
    mode: computed(() => mode.value),
    shouldNotify,
    getBufferedCount,
    flush,
    toggleSilent,
    setMode,
  }
}
