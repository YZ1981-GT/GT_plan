/**
 * useEditingLock — 编辑软锁 composable [R7-S2-04]
 *
 * 进入编辑模式时 acquire lock，心跳每 2 分钟续期，
 * 页面关闭/路由离开时 release。
 *
 * 后端端点（统一通用编辑锁端点）：
 *     POST   /api/editing-locks/{resourceType}/{resourceId}            — 获取锁
 *     PATCH  /api/editing-locks/{resourceType}/{resourceId}/heartbeat  — 续期
 *     DELETE /api/editing-locks/{resourceType}/{resourceId}            — 释放锁
 *     POST   /api/editing-locks/{resourceType}/{resourceId}/force      — 强抢锁
 *
 * @example
 * // 底稿
 * const lock = useEditingLock({ resourceId: wpId, resourceType: 'workpaper' })
 * // 附注
 * const lock = useEditingLock({ resourceId: noteId, resourceType: 'disclosure_note' })
 * // 审计报告
 * const lock = useEditingLock({ resourceId: reportId, resourceType: 'audit_report' })
 */
import { ref, computed, onMounted, onUnmounted, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import { claimClientInstanceId } from '@/utils/clientInstance'

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
  resource_type?: string
  resource_id?: string
}

export interface EditingLockOptions {
  /** 资源 ID（底稿 UUID / 其他标识） */
  resourceId: Ref<string>
  /**
   * 资源类型：
   * - 'workpaper' → 走通用编辑锁端点 /api/editing-locks/workpaper/{id}
   * - 其他字符串（如 'disclosure_note' / 'audit_report'）→ 走通用编辑锁端点
   */
  resourceType?: string
  /** 心跳间隔（ms），默认 120000（2 分钟） */
  heartbeatMs?: number
  /** 是否在 mount 时自动 acquire（默认 true） */
  autoAcquire?: boolean
  /**
   * 能编辑时才取锁（不传 = 恒取锁，兼容旧调用方）。变为 false 时释放已持有的锁。
   * 🔴 只读身份（质控 / EQCR / 未委派的人）打开底稿也去取锁 ⇒ 后端拒绝时每次都留一条拒绝记录，
   *    放行时又把真正要编辑的人挤成只读（spec procedure-chain-hardening-and-java-contracts R2）。
   */
  enabled?: Readonly<Ref<boolean>>
}

/** 取锁 / 续期 / 强制接管的错误由本函数处理，不弹全局提示（拦截器会把 404 / 409 弹成通用错误）。 */
const SILENT = { _silent: true } as any

function statusOf(e: any): number | undefined {
  return e?.response?.status ?? e?.status
}

export function useEditingLock(options: EditingLockOptions) {
  const locked = ref(false)
  const lockedBy = ref<string | null>(null)
  const isMine = ref(false)
  /** 多窗口门禁：acquire 被 409 拒绝时为 true，宿主据此禁用所有保存操作 */
  const forcedReadonly = ref(false)
  /** 取锁被拒（无权编辑 / 看不见该资源，后端 403 / 404）：不显示「他人正在编辑」 */
  const denied = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  const heartbeatMs = options.heartbeatMs ?? 120_000
  const resourceType = options.resourceType ?? 'workpaper'
  const isEnabled = () => options.enabled === undefined || options.enabled.value

  async function acquire() {
    const id = options.resourceId.value
    if (!id) return

    // 窗口编号认领完再取锁：「复制标签页」沿用了原标签页的编号，认领后才换成本页自己的（workpaper-multi-window-lock-gaps R1.3）
    await claimClientInstanceId()
    if (options.resourceId.value !== id) return // 等认领期间换了底稿：由 watch 按新 id 取锁
    const base = `/api/editing-locks/${resourceType}/${id}`
    try {
      const res = await api.post(base, undefined, SILENT)
      locked.value = true
      isMine.value = res?.acquired ?? true
      lockedBy.value = res?.locked_by_name ?? null
      denied.value = false
      // 记下**实际持有**的 id —— release / heartbeat 一律按它发（见 release 注释）
      if (isMine.value) heldId.value = id
    } catch (e: any) {
      const status = statusOf(e)
      if (status === 409) {
        locked.value = true
        isMine.value = false
        // 多窗口门禁：同底稿第二窗口锁冲突 → 强制只读
        // spec: multi-window-ledger-workbench Phase 3 Task 17
        forcedReadonly.value = true
        lockedBy.value = e?.response?.data?.detail?.locked_by_name
          ?? e?.data?.detail?.locked_by_name ?? '其他用户'
      } else if (status === 403 || status === 404) {
        locked.value = false
        isMine.value = false
        lockedBy.value = null
        denied.value = true
      }
    }
  }

  /**
   * 释放 / 续期**实际持有**的那把锁。
   *
   * 🔴 一律按 `heldId` 发，禁止读 `options.resourceId.value`（2026-09-28 真机实测）：
   *
   * `resourceId` 通常是 `computed(() => route.params.wpId)`。切底稿时 Vue Router
   * **先**更新路由参数、**后**卸载旧组件 ⇒ `onUnmounted` 里的 `release()` 读到的
   * 已经是**新** id。实测网络日志（K8 → L4）：
   *     DELETE /api/editing-locks/workpaper/{L4} => 404   ← 本该是 {K8}
   *     POST   /api/editing-locks/workpaper/{L4} => 200
   * 后果不只是 console 噪音：**K8 的锁从未被释放**，要等心跳超时，
   * 期间他人打开 K8 会看到「正在被 admin 编辑」。
   *
   * 🔴 首版只给 `watch` 传了 oldId 就以为修好了 —— 真机仍复现，因为该路径根本不是
   * `watch`（组件被卸载重建，watch 不触发）。**只有「按持有的 id 释放」才覆盖全部
   * 三条路径**（watch / onUnmounted / beforeunload）—— 你只能释放你持有的东西。
   */
  const heldId = ref<string | null>(null)

  async function release() {
    const id = heldId.value
    if (!id || !isMine.value) return

    try {
      await api.delete(`/api/editing-locks/${resourceType}/${id}`, SILENT)
    } catch { /* ignore */ }
    heldId.value = null
    locked.value = false
    isMine.value = false
  }

  async function heartbeat() {
    const id = heldId.value
    if (!id || !isMine.value) return

    try {
      await api.patch(`/api/editing-locks/${resourceType}/${id}/heartbeat`, undefined, SILENT)
    } catch (e: any) {
      const status = statusOf(e)
      if (status !== 403 && status !== 404) return // 网络抖动：下一次再续
      // 锁已过期 / 已被收回（撤权时后端顺手放掉了本人的锁）：不再当作持锁，重新取一次
      // （他人已持锁 ⇒ 409 进只读；无权 ⇒ denied）
      stopHeartbeat()
      heldId.value = null
      isMine.value = false
      locked.value = false
      await acquire()
      if (isMine.value) startHeartbeat()
    }
  }

  /** 强抢锁 */
  async function forceAcquire() {
    const id = options.resourceId.value
    if (!id) return

    await claimClientInstanceId()
    try {
      const res = await api.post(`/api/editing-locks/${resourceType}/${id}/force`, undefined, SILENT)
      locked.value = true
      isMine.value = true
      lockedBy.value = null
      forcedReadonly.value = false
      heldId.value = id
      return res
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? e?.response?.data?.message
      ElMessage.error(
        statusOf(e) === 403
          ? (typeof detail === 'string' && detail) || '只有底稿负责人、主管或管理员可以强制接管编辑锁'
          : '强制接管编辑锁失败，请刷新页面后重试',
      )
    }
  }

  function startHeartbeat() {
    stopHeartbeat()
    timer = setInterval(heartbeat, heartbeatMs)
  }

  function stopHeartbeat() {
    if (timer) { clearInterval(timer); timer = null }
  }

  function onBeforeUnload() {
    // 🔴 复盘 P0-2：beforeunload 中异步 XHR 会被浏览器取消。
    // 用 fetch + keepalive 保证请求在页面卸载后仍能发出。
    const id = heldId.value
    if (!id || !isMine.value) return
    const token = sessionStorage.getItem('token')
    const instanceId = sessionStorage.getItem('gt-client-instance-id')
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    if (instanceId) headers['X-Client-Instance'] = instanceId
    try {
      fetch(`/api/editing-locks/${resourceType}/${id}`, {
        method: 'DELETE',
        keepalive: true,
        headers,
      })
    } catch { /* 静默：keepalive 不可用时退回旧行为，锁等心跳过期 */ }
    heldId.value = null
    isMine.value = false
  }

  /** SSE 事件处理：他人通过 force_acquired 强抢了我的锁 */
  function onSSEEvent(payload: any) {
    if (!payload || payload.event_type !== 'editing_lock.force_acquired') return

    const isWorkpaper = resourceType === 'workpaper'

    if (isWorkpaper) {
      // 底稿锁：匹配 wp_id
      if (payload.wp_id !== options.resourceId.value) return
    } else {
      // 通用锁：匹配 resource_type + resource_id
      if (payload.resource_type !== resourceType) return
      if (payload.resource_id !== options.resourceId.value) return
    }

    // 仅当本人原本持锁时才反应（避免他人之间互抢的杂讯）
    if (!isMine.value) return
    isMine.value = false
    forcedReadonly.value = true
    lockedBy.value = payload.new_holder_name ?? null
    eventBus.emit('editing-lock:taken-over', {
      wp_id: payload.wp_id ?? options.resourceId.value,
      new_holder_id: payload.new_holder_id,
      new_holder_name: payload.new_holder_name,
      previous_holder_id: payload.previous_holder_id,
    })
  }

  onMounted(async () => {
    if (options.autoAcquire !== false && isEnabled()) {
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
    // release() 按 heldId 发，此刻 heldId 仍是旧 id ⇒ 无需也不应传参（见 release 注释）
    if (oldId && isMine.value) await release()
    stopHeartbeat()
    denied.value = false
    if (newId && isEnabled()) {
      await acquire()
      if (isMine.value) startHeartbeat()
    }
  })

  // 可编辑状态变化：变为可编辑时取锁，变为不可编辑时放锁
  if (options.enabled) {
    watch(options.enabled, async (on) => {
      if (on && !isMine.value && options.autoAcquire !== false) {
        await acquire()
        if (isMine.value) startHeartbeat()
      } else if (!on && isMine.value) {
        stopHeartbeat()
        await release()
      }
    })
  }

  return { locked, lockedBy, isMine, forcedReadonly, denied, acquire, release, forceAcquire }
}
