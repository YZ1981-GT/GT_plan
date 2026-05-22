/**
 * Service Worker — 底稿离线缓存支持
 * Phase 8 Task 5.2: 已缓存底稿查看
 *
 * 策略：
 * - 缓存已查看过的底稿数据（parsed_data）
 * - 离线时从 Cache Storage 返回缓存数据
 * - 在线时优先网络，失败时降级到缓存
 */

const CACHE_NAME = 'workpaper-cache-v1'
const WORKPAPER_API_PATTERN = /\/api\/working-papers\/[^/]+$/

// Install event - pre-cache shell
self.addEventListener('install', (event) => {
  self.skipWaiting()
})

// Activate event - clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  )
  self.clients.claim()
})

// Fetch event - network-first with cache fallback for workpaper API
self.addEventListener('fetch', (event) => {
  const { request } = event

  // Only cache GET requests to workpaper API
  if (request.method !== 'GET') return
  if (!WORKPAPER_API_PATTERN.test(new URL(request.url).pathname)) return

  event.respondWith(
    fetch(request)
      .then((response) => {
        // Clone and cache successful responses
        if (response.ok) {
          const clone = response.clone()
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, clone)
          })
        }
        return response
      })
      .catch(() => {
        // Offline fallback - return cached response
        return caches.match(request)
      })
  )
})
