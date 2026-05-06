import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi, notificationApi } from '@/services/collaborationApi'
import { eventBus } from '@/utils/eventBus'

export const useCollaborationStore = defineStore('collaboration', () => {
  // Auth state — 统一使用 'token' 键名（与 auth.ts 一致）
  const user = ref<any>(null)
  const accessToken = ref<string | null>(localStorage.getItem('token'))
  const isAuthenticated = computed(() => !!accessToken.value)

  // Notifications
  const notifications = ref<any[]>([])
  const unreadCount = ref(0)

  // SSE 通知事件订阅状态
  let sseSubscribed = false

  async function login(username: string, password: string) {
    const { data } = await authApi.login(username, password)
    accessToken.value = data.access_token
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('refreshToken', data.refresh_token)
    await fetchMe()
    return data
  }

  async function fetchMe() {
    try {
      const { data } = await authApi.me()
      user.value = data
    } catch { /* silent */ }
  }

  async function logout() {
    try { await authApi.logout() } catch { /* silent */ }
    accessToken.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('refreshToken')
  }

  async function fetchNotifications() {
    try {
      const { data } = await notificationApi.list()
      notifications.value = data
      const count = await notificationApi.unreadCount()
      unreadCount.value = count.data?.count ?? 0
    } catch { /* silent */ }
  }

  async function markNotificationRead(id: string) {
    try {
      await notificationApi.markRead(id)
      await fetchNotifications()
    } catch { /* silent */ }
  }

  /**
   * 订阅 SSE 通知事件，当收到项目内事件时自动刷新未读数
   * 由 DefaultLayout 在 onMounted 时调用一次
   */
  function subscribeSSENotifications() {
    if (sseSubscribed) return
    sseSubscribed = true

    // 监听 SSE 同步事件 — 当有新的复核/工单/底稿事件时，可能产生新通知
    eventBus.on('sse:sync-event', (_payload) => {
      // 收到任何 SSE 事件时刷新未读数（轻量请求）
      refreshUnreadCount()
    })
  }

  /** 仅刷新未读数（轻量，不拉全量列表） */
  async function refreshUnreadCount() {
    try {
      const count = await notificationApi.unreadCount()
      unreadCount.value = count.data?.count ?? 0
    } catch { /* silent */ }
  }

  return {
    user, accessToken, isAuthenticated,
    notifications, unreadCount,
    login, fetchMe, logout,
    fetchNotifications, markNotificationRead,
    subscribeSSENotifications, refreshUnreadCount,
  }
})
