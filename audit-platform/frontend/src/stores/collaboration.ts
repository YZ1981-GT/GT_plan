import { defineStore } from 'pinia'
import { ref } from 'vue'
import { notificationApi } from '@/services/collaborationApi'
import { eventBus } from '@/utils/eventBus'
import {
  isProcedureTaskSseEvent,
  ingestProcedureTaskEvent,
} from '@/composables/useProcedureTaskSse'

export const useCollaborationStore = defineStore('collaboration', () => {
  // 认证状态唯一真源是 stores/auth.ts（token 存 sessionStorage）。
  // 本 store 旧有的 user/accessToken/login/fetchMe/logout 会把 token 写回 localStorage、
  // 与 auth store 双写，且全仓零调用方（2026-09-29 grep 实证：消费方只用通知字段）——已删除，
  // 防止被误用后把 token 重新落到 localStorage（守卫：authTokenSingleSource.spec.ts）。

  // Notifications
  const notifications = ref<any[]>([])
  const unreadCount = ref(0)

  // SSE 通知事件订阅状态
  let sseSubscribed = false

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
    eventBus.on('sse:sync-event', (payload: any) => {
      // 程序行任务事件（procedure_task.event）：按 event_id LRU 幂等，重复事件不重复刷新
      // （Task 11 / Req 10.6）。新事件才刷新未读数；任务列表由 MyProcedureTasks 订阅刷新。
      if (isProcedureTaskSseEvent(payload)) {
        if (ingestProcedureTaskEvent(payload)) {
          refreshUnreadCount()
        }
        return
      }
      // 其它 SSE 事件：收到即刷新未读数（轻量请求）
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
    notifications, unreadCount,
    fetchNotifications, markNotificationRead,
    subscribeSSENotifications, refreshUnreadCount,
  }
})
