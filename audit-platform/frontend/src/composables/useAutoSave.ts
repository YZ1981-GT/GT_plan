/**
 * useAutoSave — 自动保存/草稿恢复 composable
 *
 * 提供统一的自动保存与草稿恢复能力：
 * - 定时将数据保存到 sessionStorage（关闭标签页后自动清除，防止多标签页 key 冲突）
 * - 挂载时检测草稿并提示恢复
 * - 保存成功后清除草稿
 * - 卸载时清除定时器
 *
 * 用法：
 *   const { hasDraft, clearDraft, saveDraft, restoreDraft } = useAutoSave(
 *     'disclosure_note_123_five',
 *     () => currentNote.value,
 *     (data) => { currentNote.value = data },
 *   )
 *
 * @module composables/useAutoSave
 * @see R3.8
 */
import { ref, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useProjectStore } from '@/stores/project'

export interface UseAutoSaveOptions {
  /** 自动保存间隔（毫秒），默认 30000（30秒） */
  interval?: number
  /** 是否启用自动保存，默认 true；可传入 Ref<boolean> 动态控制 */
  enabled?: Ref<boolean> | boolean
}

export function useAutoSave<T = any>(
  key: string,
  getData: () => T | null | undefined,
  setData: (data: T) => void,
  options?: UseAutoSaveOptions,
) {
  const interval = options?.interval ?? 30000
  const enabledRef = options?.enabled
  const hasDraft = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  /** 判断自动保存是否启用 */
  function isEnabled(): boolean {
    if (enabledRef == null) return true
    if (typeof enabledRef === 'boolean') return enabledRef
    return enabledRef.value
  }

  /** 构建完整的 sessionStorage key（含 projectId 前缀，防止多项目间草稿互相覆盖） */
  function storageKey(): string {
    const projectStore = useProjectStore()
    const pid = projectStore.projectId || 'global'
    return `autosave_${pid}_${key}`
  }

  /** 手动保存草稿到 sessionStorage */
  function saveDraft(): boolean {
    try {
      const data = getData()
      if (data == null) return false
      const payload = {
        data,
        savedAt: Date.now(),
      }
      sessionStorage.setItem(storageKey(), JSON.stringify(payload))
      hasDraft.value = true
      return true
    } catch {
      return false
    }
  }

  /** 从 sessionStorage 恢复草稿 */
  function restoreDraft(): boolean {
    try {
      const raw = sessionStorage.getItem(storageKey())
      if (!raw) return false
      const payload = JSON.parse(raw)
      if (payload?.data != null) {
        setData(payload.data)
        return true
      }
      return false
    } catch {
      return false
    }
  }

  /** 清除草稿（保存成功后调用） */
  function clearDraft() {
    sessionStorage.removeItem(storageKey())
    hasDraft.value = false
  }

  /** 检查是否存在草稿 */
  function checkDraft(): boolean {
    try {
      const raw = sessionStorage.getItem(storageKey())
      if (!raw) return false
      const payload = JSON.parse(raw)
      return payload?.data != null
    } catch {
      return false
    }
  }

  /** 获取草稿保存时间的可读字符串 */
  function getDraftTime(): string {
    try {
      const raw = sessionStorage.getItem(storageKey())
      if (!raw) return ''
      const payload = JSON.parse(raw)
      if (!payload?.savedAt) return ''
      return new Date(payload.savedAt).toLocaleString('zh-CN')
    } catch {
      return ''
    }
  }

  /** 启动定时自动保存 */
  function startTimer() {
    stopTimer()
    timer = setInterval(() => {
      if (isEnabled()) {
        saveDraft()
      }
    }, interval)
  }

  /** 停止定时器 */
  function stopTimer() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  // 挂载时：检查草稿并提示恢复，然后启动定时器
  onMounted(async () => {
    if (checkDraft()) {
      hasDraft.value = true
      const draftTime = getDraftTime()
      const timeHint = draftTime ? `（保存于 ${draftTime}）` : ''
      try {
        await ElMessageBox.confirm(
          `检测到未保存的草稿${timeHint}，是否恢复？`,
          '草稿恢复',
          {
            confirmButtonText: '恢复草稿',
            cancelButtonText: '放弃草稿',
            type: 'info',
          },
        )
        restoreDraft()
      } catch {
        // 用户选择放弃草稿
        clearDraft()
      }
    }
    startTimer()
  })

  // 卸载时：清除定时器
  onBeforeUnmount(() => {
    stopTimer()
  })

  return {
    /** 是否存在草稿 */
    hasDraft,
    /** 清除草稿（保存成功后调用） */
    clearDraft,
    /** 手动触发保存草稿 */
    saveDraft,
    /** 手动触发恢复草稿 */
    restoreDraft,
  }
}
