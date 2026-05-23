/**
 * useEditingLock — 编辑软锁 composable [R7-S2-04]
 *
 * 进入编辑模式时 acquire lock，心跳每 2 分钟续期，
 * 页面关闭/路由离开时 release。
 *
 * 后端端点（R4 已建，仅支持 workpaper 类型）：
 *   POST   /api/workpapers/{wpId}/editing-lock          — 获取锁
 *   PATCH  /api/workpapers/{wpId}/editing-lock/heartbeat — 续期
 *   DELETE /api/workpapers/{wpId}/editing-lock           — 释放锁
 *
 * 对于非底稿资源（附注/审计报告），使用 localStorage 轻量锁（无后端支持时降级）。
 *
 * @example
 * // 底稿（有后端锁）
 * const lock = useEditingLock({ resourceId: wpId, resourceType: 'workpaper' })
 * // 附注/报告（降级为前端检测）
 * const lock = useEditingLock({ resourceId: id, resourceType: 'other' })
 */
import { ref, computed, onMounted, onUnmounted, watch, type Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'

/** 锁冲突信息（他人持锁时由 acquire 409 / SSE 推送返回） */
export interface LockConflictInfo {
  locked_by?: string
  locked_by_name?: string
  acquired_at?: string
}

/** force_acquired SSE 事件 payload（被强抢通知） */
export interface EditingLockTakenOverPayload {
  wp_id: string
  new_holder_id: string
  new_holder_name: string
  previous_holder_id?: string
}

export interface EditingLockOptions {
  /** 资源 ID（底稿 UUID / 其他标识） */
  resourceId: Ref<string>
  /** 资源类型：workpaper 走后端锁，其他走前端降级 */
  resourceType?: 'workpaper' | 'other'
  /** 心跳间隔（ms），默认 120000（2 分钟） */
  heartbeatMs?: number
  /** 是否在 mount 时自动 acquire（默认 true） */
  autoAcquire?: boolean
}

export function useEditingLock(options: EditingLockOptions) {
  const locked = ref(false)
  const lockedBy = ref<string | null>(null)
  const isMine = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  const heartbeatMs = options.heartbeatMs ?? 120_000
  const isWorkpaper = (options.resourceType ?? 'workpaper') === 'workpaper'

  async function acquire() {
    const id = options.resourceId.value
    if (!id) return

    if (!isWorkpaper) {
      // 非底稿资源：降级为"始终可编辑"（后端暂无通用锁端点）
      locked.value = true
      isMine.value = true
      return
    }

    try {
      const res = await api.post(`/api/workpapers/${id}/editing-lock`)
      locked.value = true
      isMine.value = res?.acquired ?? true
      lockedBy.value = res?.locked_by_name ?? null
    } catch (e: any) {
      // 409 = 他人持锁
      if (e?.response?.status === 409 || e?.status === 409) {
        locked.value = true
        isMine.value = false
        lockedBy.value = e?.response?.data?.detail?.locked_by_name
          ?? e?.data?.detail?.locked_by_name ?? '其他用户'
      }
    }
  }

  async function release() {
    const id = options.resourceId.value
    if (!id || !isMine.value) return

    if (!isWorkpaper) {
      locked.value = false
      isMine.value = false
      return
    }

    try {
      await api.delete(`/api/workpapers/${id}/editing-lock`)
    } catch { /* ignore */ }
    locked.value = false
    isMine.value = false
  }

  async function heartbeat() {
    const id = options.resourceId.value
    if (!id || !isMine.value || !isWorkpaper) return
    try {
      await api.patch(`/api/workpapers/${id}/editing-lock/heartbeat`)
    } catch { /* ignore */ }
  }

  function startHeartbeat() {
    stopHeartbeat()
    if (isWorkpaper) {
      timer = setInterval(heartbeat, heartbeatMs)
    }
  }

  function stopHeartbeat() {
    if (timer) { clearInterval(timer); timer = null }
  }

  function onBeforeUnload() { release() }

  /** SSE 事件处理：他人通过 force_acquired 强抢了我的锁 */
  function onSSEEvent(payload: any) {
    if (!payload || payload.event_type !== 'editing_lock.force_acquired') return
    if (!isWorkpaper) return
    if (payload.wp_id !== options.resourceId.value) return
    // 仅当本人原本持锁时才反应（避免他人之间互抢的杂讯）
    if (!isMine.value) return
    isMine.value = false
    lockedBy.value = payload.new_holder_name ?? null
    eventBus.emit('editing-lock:taken-over', {
      wp_id: payload.wp_id,
      new_holder_id: payload.new_holder_id,
      new_holder_name: payload.new_holder_name,
      previous_holder_id: payload.previous_holder_id,
    })
  }

  onMounted(async () => {
    if (options.autoAcquire !== false) {
      await acquire()
      if (isMine.value) startHeartbeat()
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    eventBus.on('sse:sync-event', onSSEEvent)
  })

  onUnmounted(() => {
    stopHeartbeat()
    release()
    window.removeEventListener('beforeunload', onBeforeUnload)
    eventBus.off('sse:sync-event', onSSEEvent)
  })

  // 资源 ID 变化时重新获取锁
  watch(options.resourceId, async (newId, oldId) => {
    if (oldId && isMine.value) await release()
    stopHeartbeat()
    if (newId) {
      await acquire()
      if (isMine.value) startHeartbeat()
    }
  })

  return { locked, lockedBy, isMine, acquire, release }
}
