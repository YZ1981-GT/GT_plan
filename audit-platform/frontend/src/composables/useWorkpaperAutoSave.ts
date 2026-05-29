/**
 * useWorkpaperAutoSave — 底稿/附注自动保存 composable [R7-S2-05]
 *
 * 独立于 useAutoSave（sessionStorage 草稿恢复），本 composable 面向
 * Univer 大型 snapshot 的后端定时保存。
 *
 * V3 Req 11.7: 扩展 5 分钟快照触发（与 autoSave 60s/120s 独立计时）
 * V3 Req 12.3: intervalMs 120000→60000 + 大量编辑时缩短到 30s + 失败重试 + beforeunload
 *
 * @example
 * const { saving, lastSavedAt, isDirty, markDirty, doSave, isSaveFailed, recordEdit } = useWorkpaperAutoSave(
 *   async () => { await saveToBackend() },
 *   60_000, // 1 分钟（V3 默认）
 *   { snapshotEnabled: true, module: 'workpaper', instanceId: wpId }
 * )
 */
import { ref, onMounted, onUnmounted, type Ref } from 'vue'
import { api } from '@/services/apiProxy'

export interface SnapshotOptions {
  /** 是否启用时光机快照 */
  snapshotEnabled?: boolean
  /** 快照间隔（毫秒），默认 300_000（5 分钟） */
  snapshotIntervalMs?: number
  /** 业务模块类型 */
  module?: string
  /** 实例 ID（响应式） */
  instanceId?: Ref<string> | string
  /** 序列化当前数据的函数 */
  serialize?: () => any
}

export interface AutoSaveOptions {
  /** 大量编辑时的快速间隔（毫秒），默认 30_000 */
  fastIntervalMs?: number
  /** 触发快速模式的编辑次数阈值，默认 10 */
  fastTriggerThreshold?: number
  /** beforeunload 同步保存的 URL（sendBeacon） */
  saveBeaconUrl?: string
  /** beforeunload 同步保存的 body 序列化函数 */
  serializeForBeacon?: () => string | Blob | null
}

export function useWorkpaperAutoSave(
  onSave: () => Promise<void>,
  intervalMs = 60_000,
  snapshotOpts?: SnapshotOptions,
  autoSaveOpts?: AutoSaveOptions,
) {
  const saving = ref(false)
  const lastSavedAt = ref<Date | null>(null)
  const lastError = ref<string | null>(null)
  const isDirty = ref(false)
  const isSaveFailed = ref(false)
  const editCount = ref(0)
  const currentIntervalMs = ref(intervalMs)
  let timer: ReturnType<typeof setInterval> | null = null
  let snapshotTimer: ReturnType<typeof setInterval> | null = null
  let prevSnapshotData: any = null

  const fastIntervalMs = autoSaveOpts?.fastIntervalMs ?? 30_000
  const fastThreshold = autoSaveOpts?.fastTriggerThreshold ?? 10

  /** 标记数据已变更（由编辑器 onChange 调用） */
  function markDirty() { isDirty.value = true }

  /** 清除脏标记（手动保存成功后调用） */
  function clearDirty() { isDirty.value = false }

  /** V3 Req 12.3.1: 记录编辑操作，大量编辑时缩短间隔到 30s */
  function recordEdit() {
    isDirty.value = true
    editCount.value++
    if (editCount.value >= fastThreshold && currentIntervalMs.value !== fastIntervalMs) {
      currentIntervalMs.value = fastIntervalMs
      resetTimer()
    }
  }

  /** 执行保存（仅在 dirty 且非 saving 时）— V3 Req 12.3.2: 失败立即重试 1 次 */
  async function doSave() {
    if (!isDirty.value || saving.value) return
    saving.value = true
    lastError.value = null
    isSaveFailed.value = false
    try {
      await onSave()
      isDirty.value = false
      lastSavedAt.value = new Date()
      editCount.value = 0
      // 保存成功后恢复正常间隔
      if (currentIntervalMs.value !== intervalMs) {
        currentIntervalMs.value = intervalMs
        resetTimer()
      }
    } catch (e: any) {
      // V3 Req 12.3.2: 立即重试 1 次
      try {
        await onSave()
        isDirty.value = false
        lastSavedAt.value = new Date()
        editCount.value = 0
        isSaveFailed.value = false
        if (currentIntervalMs.value !== intervalMs) {
          currentIntervalMs.value = intervalMs
          resetTimer()
        }
      } catch (retryErr: any) {
        isSaveFailed.value = true
        lastError.value = retryErr?.message || '自动保存失败'
      }
    } finally {
      saving.value = false
    }
  }

  /** V3 Req 11.7: 5 分钟快照触发 */
  async function doSnapshot() {
    if (!isDirty.value) return
    if (!snapshotOpts?.serialize || !snapshotOpts?.module) return

    const instanceId = typeof snapshotOpts.instanceId === 'string'
      ? snapshotOpts.instanceId
      : snapshotOpts.instanceId?.value

    if (!instanceId) return

    try {
      const currentData = snapshotOpts.serialize()
      await api.post(
        `/api/instances/${snapshotOpts.module}/${instanceId}/time-machine/snapshots`,
        {
          current_data: currentData,
          previous_data: prevSnapshotData,
        },
      )
      prevSnapshotData = currentData
    } catch {
      // 快照失败静默不阻断编辑
    }
  }

  /** 重置定时器（间隔变化时调用） */
  function resetTimer() {
    if (timer) { clearInterval(timer); timer = null }
    timer = setInterval(doSave, currentIntervalMs.value)
  }

  /** V3 Req 12.3.3: beforeunload 同步保存 */
  function onBeforeUnload() {
    if (!isDirty.value) return
    if (autoSaveOpts?.saveBeaconUrl && autoSaveOpts?.serializeForBeacon) {
      const body = autoSaveOpts.serializeForBeacon()
      if (body) {
        navigator.sendBeacon(autoSaveOpts.saveBeaconUrl, body)
      }
    }
  }

  onMounted(() => {
    timer = setInterval(doSave, currentIntervalMs.value)

    // V3 Req 11.7: 独立 5 分钟快照计时器
    if (snapshotOpts?.snapshotEnabled) {
      const snapInterval = snapshotOpts.snapshotIntervalMs ?? 300_000
      snapshotTimer = setInterval(doSnapshot, snapInterval)
    }

    // V3 Req 12.3.3: beforeunload 触发同步保存
    window.addEventListener('beforeunload', onBeforeUnload)
  })

  onUnmounted(() => {
    if (timer) { clearInterval(timer); timer = null }
    if (snapshotTimer) { clearInterval(snapshotTimer); snapshotTimer = null }
    window.removeEventListener('beforeunload', onBeforeUnload)
  })

  return {
    saving, lastSavedAt, lastError, isDirty, isSaveFailed,
    markDirty, clearDirty, recordEdit, doSave, doSnapshot,
    /** 当前实际间隔（用于测试验证） */
    currentIntervalMs,
  }
}
