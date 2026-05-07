/**
 * useWorkpaperAutoSave — 底稿/附注自动保存 composable [R7-S2-05]
 *
 * 独立于 useAutoSave（sessionStorage 草稿恢复），本 composable 面向
 * Univer 大型 snapshot 的后端定时保存。
 *
 * @example
 * const { saving, lastSavedAt, isDirty, markDirty, doSave } = useWorkpaperAutoSave(
 *   async () => { await saveToBackend() },
 *   120_000, // 2 分钟
 * )
 */
import { ref, onMounted, onUnmounted } from 'vue'

export function useWorkpaperAutoSave(
  onSave: () => Promise<void>,
  intervalMs = 120_000,
) {
  const saving = ref(false)
  const lastSavedAt = ref<Date | null>(null)
  const lastError = ref<string | null>(null)
  const isDirty = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  /** 标记数据已变更（由编辑器 onChange 调用） */
  function markDirty() { isDirty.value = true }

  /** 清除脏标记（手动保存成功后调用） */
  function clearDirty() { isDirty.value = false }

  /** 执行保存（仅在 dirty 且非 saving 时） */
  async function doSave() {
    if (!isDirty.value || saving.value) return
    saving.value = true
    lastError.value = null
    try {
      await onSave()
      isDirty.value = false
      lastSavedAt.value = new Date()
    } catch (e: any) {
      lastError.value = e?.message || '自动保存失败'
    } finally {
      saving.value = false
    }
  }

  onMounted(() => {
    timer = setInterval(doSave, intervalMs)
  })

  onUnmounted(() => {
    if (timer) { clearInterval(timer); timer = null }
  })

  return { saving, lastSavedAt, lastError, isDirty, markDirty, clearDirty, doSave }
}
