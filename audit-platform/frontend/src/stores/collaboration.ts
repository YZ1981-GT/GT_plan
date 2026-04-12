import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi, notificationApi } from '@/services/collaborationApi'

export const useCollaborationStore = defineStore('collaboration', () => {
  // Auth state
  const user = ref<any>(null)
  const accessToken = ref<string | null>(localStorage.getItem('access_token'))
  const isAuthenticated = computed(() => !!accessToken.value)

  // Notifications
  const notifications = ref<any[]>([])
  const unreadCount = ref(0)

  async function login(username: string, password: string) {
    const { data } = await authApi.login(username, password)
    accessToken.value = data.access_token
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    await fetchMe()
    return data
  }

  async function fetchMe() {
    try {
      const { data } = await authApi.me()
      user.value = data
    } catch (e) {
      console.error(e)
    }
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch (e) {
      console.error(e)
    }
    accessToken.value = null
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  async function fetchNotifications() {
    try {
      const { data } = await notificationApi.list()
      notifications.value = data
      const count = await notificationApi.unreadCount()
      unreadCount.value = count.data?.count ?? 0
    } catch (e) {
      console.error(e)
    }
  }

  async function markNotificationRead(id: string) {
    try {
      await notificationApi.markRead(id)
      await fetchNotifications()
    } catch (e) {
      console.error(e)
    }
  }

  return {
    user, accessToken, isAuthenticated,
    notifications, unreadCount,
    login, fetchMe, logout,
    fetchNotifications, markNotificationRead,
  }
})
