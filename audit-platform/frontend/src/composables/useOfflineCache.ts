/**
 * useOfflineCache — 底稿离线缓存 composable
 * Phase 8 Task 5.2: 已缓存底稿查看
 *
 * 功能：
 * - Service Worker 注册
 * - localStorage 缓存底稿元数据
 * - 离线状态检测
 * - 缓存底稿列表管理
 */

import { ref, onMounted, computed } from 'vue'

const CACHE_KEY_PREFIX = 'wp_offline_'
const CACHE_INDEX_KEY = 'wp_offline_index'

export interface CachedWorkpaper {
  id: string
  wp_code: string
  name: string
  cachedAt: string
  size: number
}

/**
 * 注册 Service Worker
 */
export function registerServiceWorker(): void {
  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
      navigator.serviceWorker
        .register('/sw.js')
        .then((registration) => {
          import.meta.env.DEV && console.log('[SW] Registered:', registration.scope) // eslint-disable-line no-console
        })
        .catch((error) => {
          import.meta.env.DEV && console.warn('[SW] Registration failed:', error) // eslint-disable-line no-console
        })
    })
  }
}

/**
 * 离线缓存 composable
 */
export function useOfflineCache() {
  const isOnline = ref(navigator.onLine)
  const cachedWorkpapers = ref<CachedWorkpaper[]>([])

  onMounted(() => {
    // Listen for online/offline events
    window.addEventListener('online', () => {
      isOnline.value = true
    })
    window.addEventListener('offline', () => {
      isOnline.value = false
    })

    // Load cached workpaper index
    loadCacheIndex()
  })

  function loadCacheIndex() {
    try {
      const raw = localStorage.getItem(CACHE_INDEX_KEY)
      cachedWorkpapers.value = raw ? JSON.parse(raw) : []
    } catch {
      cachedWorkpapers.value = []
    }
  }

  function saveCacheIndex() {
    localStorage.setItem(CACHE_INDEX_KEY, JSON.stringify(cachedWorkpapers.value))
  }

  /**
   * 缓存底稿数据到 localStorage
   */
  function cacheWorkpaper(workpaper: { id: string; wp_code: string; name: string; data: unknown }) {
    const key = `${CACHE_KEY_PREFIX}${workpaper.id}`
    const serialized = JSON.stringify(workpaper.data)

    try {
      localStorage.setItem(key, serialized)

      // Update index
      const existing = cachedWorkpapers.value.findIndex((w) => w.id === workpaper.id)
      const entry: CachedWorkpaper = {
        id: workpaper.id,
        wp_code: workpaper.wp_code,
        name: workpaper.name,
        cachedAt: new Date().toISOString(),
        size: serialized.length,
      }

      if (existing >= 0) {
        cachedWorkpapers.value[existing] = entry
      } else {
        cachedWorkpapers.value.push(entry)
      }
      saveCacheIndex()
    } catch (e) {
      // localStorage quota exceeded - remove oldest entries
      if (cachedWorkpapers.value.length > 0) {
        const oldest = cachedWorkpapers.value.shift()
        if (oldest) {
          localStorage.removeItem(`${CACHE_KEY_PREFIX}${oldest.id}`)
        }
        saveCacheIndex()
        // Retry
        cacheWorkpaper(workpaper)
      }
    }
  }

  /**
   * 从缓存获取底稿数据
   */
  function getCachedWorkpaper(id: string): unknown | null {
    const key = `${CACHE_KEY_PREFIX}${id}`
    try {
      const raw = localStorage.getItem(key)
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  }

  /**
   * 移除缓存的底稿
   */
  function removeCachedWorkpaper(id: string) {
    localStorage.removeItem(`${CACHE_KEY_PREFIX}${id}`)
    cachedWorkpapers.value = cachedWorkpapers.value.filter((w) => w.id !== id)
    saveCacheIndex()
  }

  /**
   * 清除所有离线缓存
   */
  function clearAllCache() {
    for (const wp of cachedWorkpapers.value) {
      localStorage.removeItem(`${CACHE_KEY_PREFIX}${wp.id}`)
    }
    cachedWorkpapers.value = []
    localStorage.removeItem(CACHE_INDEX_KEY)
  }

  const cachedCount = computed(() => cachedWorkpapers.value.length)
  const totalCacheSize = computed(() =>
    cachedWorkpapers.value.reduce((sum, w) => sum + w.size, 0)
  )

  return {
    isOnline,
    cachedWorkpapers,
    cachedCount,
    totalCacheSize,
    cacheWorkpaper,
    getCachedWorkpaper,
    removeCachedWorkpaper,
    clearAllCache,
  }
}
