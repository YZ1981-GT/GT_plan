/**
 * useWpOfflineCache — 底稿离线暂存 + 弱网恢复 composable
 *
 * 功能：
 * - auto-save 失败时自动暂存到 localStorage
 * - 底稿列表橙色圆点标记有暂存数据的底稿
 * - 恢复网络后自动重试保存
 * - 冲突检测弹窗（服务端版本 > 本地版本时）
 * - localStorage 上限 50MB 超出提示
 *
 * @example
 * const { saveToOffline, loadFromOffline, hasOfflineData, clearOffline } = useWpOfflineCache(wpId, sheetName)
 *
 * Validates: Requirements US-12
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

// ─── 常量 ─────────────────────────────────────────────────────────────────────

const STORAGE_KEY_PREFIX = 'gt_wp_offline_'
const OFFLINE_INDEX_KEY = 'gt_wp_offline_index'
const MAX_OFFLINE_SIZE = 50 * 1024 * 1024  // 50MB

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface OfflineCacheEntry {
  wpId: string
  sheetName: string
  data: Record<string, any>
  timestamp: number
  version?: number
}

export interface OfflineIndexEntry {
  wpId: string
  sheetName: string
  timestamp: number
  size: number
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

/** 计算当前 localStorage 中离线缓存总大小 */
export function getOfflineTotalSize(): number {
  let total = 0
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i)
    if (key && key.startsWith(STORAGE_KEY_PREFIX)) {
      const val = localStorage.getItem(key)
      if (val) total += val.length * 2 // UTF-16 每字符 2 字节
    }
  }
  return total
}

/** 获取所有有离线暂存的底稿 ID 列表（用于列表页橙色圆点标记） */
export function getOfflineWpIds(): string[] {
  try {
    const raw = localStorage.getItem(OFFLINE_INDEX_KEY)
    if (!raw) return []
    const index: OfflineIndexEntry[] = JSON.parse(raw)
    return [...new Set(index.map(e => e.wpId))]
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useWpOfflineCache(wpId: string, sheetName: string) {
  const isOnline = ref(navigator.onLine)
  const hasOfflineData = ref(false)
  const retrying = ref(false)

  let onlineHandler: (() => void) | null = null
  let offlineHandler: (() => void) | null = null

  const storageKey = `${STORAGE_KEY_PREFIX}${wpId}_${sheetName}`

  // ─── 索引管理 ───

  function loadIndex(): OfflineIndexEntry[] {
    try {
      const raw = localStorage.getItem(OFFLINE_INDEX_KEY)
      return raw ? JSON.parse(raw) : []
    } catch {
      return []
    }
  }

  function saveIndex(index: OfflineIndexEntry[]) {
    localStorage.setItem(OFFLINE_INDEX_KEY, JSON.stringify(index))
  }

  function addToIndex(size: number) {
    const index = loadIndex()
    const existing = index.findIndex(e => e.wpId === wpId && e.sheetName === sheetName)
    const entry: OfflineIndexEntry = { wpId, sheetName, timestamp: Date.now(), size }
    if (existing >= 0) {
      index[existing] = entry
    } else {
      index.push(entry)
    }
    saveIndex(index)
  }

  function removeFromIndex() {
    const index = loadIndex().filter(e => !(e.wpId === wpId && e.sheetName === sheetName))
    saveIndex(index)
  }

  // ─── 核心方法 ───

  /**
   * 暂存数据到 localStorage
   */
  function saveToOffline(data: Record<string, any>, version?: number): boolean {
    // 检查总大小限制
    const totalSize = getOfflineTotalSize()
    if (totalSize >= MAX_OFFLINE_SIZE) {
      ElMessage.warning({
        message: '本地暂存空间已满（50MB），请手动导出底稿数据或清理旧暂存',
        duration: 5000,
      })
      return false
    }

    const entry: OfflineCacheEntry = {
      wpId,
      sheetName,
      data,
      timestamp: Date.now(),
      version,
    }

    try {
      const serialized = JSON.stringify(entry)
      localStorage.setItem(storageKey, serialized)
      addToIndex(serialized.length * 2)
      hasOfflineData.value = true
      return true
    } catch (e) {
      // QuotaExceededError
      ElMessage.warning({
        message: '本地存储已满，无法暂存。请检查浏览器存储设置或清理旧数据。',
        duration: 5000,
      })
      return false
    }
  }

  /**
   * 从 localStorage 加载暂存数据
   */
  function loadFromOffline(): OfflineCacheEntry | null {
    try {
      const raw = localStorage.getItem(storageKey)
      if (!raw) return null
      return JSON.parse(raw) as OfflineCacheEntry
    } catch {
      return null
    }
  }

  /**
   * 清除暂存
   */
  function clearOffline() {
    localStorage.removeItem(storageKey)
    removeFromIndex()
    hasOfflineData.value = false
  }

  /**
   * 网络恢复后自动重试保存
   * @param saveFn 实际保存函数（调用方提供）
   * @param getServerVersion 获取服务端当前版本的函数
   */
  async function retryOnReconnect(
    saveFn: (data: Record<string, any>) => Promise<void>,
    getServerVersion?: () => Promise<number>,
  ) {
    const cached = loadFromOffline()
    if (!cached) return

    retrying.value = true
    try {
      // 冲突检测：如果服务端版本比暂存时更新
      if (getServerVersion && cached.version != null) {
        const serverVersion = await getServerVersion()
        if (serverVersion > cached.version) {
          // 冲突弹窗
          const action = await ElMessageBox.confirm(
            '检测到服务端有更新的版本，是否用本地暂存覆盖？',
            '数据冲突',
            {
              confirmButtonText: '覆盖服务端',
              cancelButtonText: '放弃本地暂存',
              type: 'warning',
            },
          ).catch(() => 'cancel')

          if (action === 'cancel') {
            clearOffline()
            return
          }
        }
      }

      await saveFn(cached.data)
      clearOffline()
      ElMessage.success('离线暂存数据已成功同步到服务端')
    } catch {
      ElMessage.error('自动重试保存失败，暂存数据仍保留在本地')
    } finally {
      retrying.value = false
    }
  }

  // ─── 生命周期 ───

  onMounted(() => {
    // 检查是否有暂存数据
    hasOfflineData.value = !!localStorage.getItem(storageKey)

    // 监听网络状态
    onlineHandler = () => {
      isOnline.value = true
    }
    offlineHandler = () => {
      isOnline.value = false
    }
    window.addEventListener('online', onlineHandler)
    window.addEventListener('offline', offlineHandler)
  })

  onBeforeUnmount(() => {
    if (onlineHandler) window.removeEventListener('online', onlineHandler)
    if (offlineHandler) window.removeEventListener('offline', offlineHandler)
  })

  return {
    isOnline,
    hasOfflineData,
    retrying,
    saveToOffline,
    loadFromOffline,
    clearOffline,
    retryOnReconnect,
  }
}
